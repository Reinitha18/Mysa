import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En développement, l'API (port 8000) est jointe via le proxy : pas de problème de CORS.
// Compilé (npm run build), le dashboard est servi par l'API sur /dashboard/.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/dashboard/" : "/",
  // Recharts pèse ~525 ko (150 ko compressé) : acceptable pour un dashboard servi sur le réseau local du hub.
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: { output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom"] } } },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
}));
