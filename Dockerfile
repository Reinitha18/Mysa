# Image du hub Mysa : API + dashboard + pont caméra, et moteur d'ingestion.
# Une seule image sert les deux services du docker-compose (commandes différentes).
#
# Étape 1 : compiler le dashboard React (Node), pour ne pas embarquer Node dans l'image finale.
FROM node:20-bookworm-slim AS dashboard
WORKDIR /dash
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build          # produit /dash/dist

# Étape 2 : image Python finale.
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Code du hub (le firmware, les tests et le lab d'attaque ne sont pas nécessaires au runtime).
COPY engine/ engine/
COPY api/ api/
COPY scripts/ scripts/
COPY camera/ camera/
COPY --from=dashboard /dash/dist dashboard/dist

# Dossiers montés en volumes par docker-compose (base + modèles appris).
RUN mkdir -p /app/data /app/engine/models

EXPOSE 8000
# Commande par défaut (API HTTPS) ; le service « engine » la remplace dans docker-compose.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ssl-keyfile", "/app/broker/certs/server.key", \
     "--ssl-certfile", "/app/broker/certs/server.crt"]
