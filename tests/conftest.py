"""Chaque test travaille dans une base et un dossier de modèles temporaires :
la base et les modèles du prototype ne sont jamais touchés."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


@pytest.fixture(autouse=True)
def isolated_engine(tmp_path, monkeypatch):
    from engine import analyzer, model, reference, storage
    from api import auth
    from api.routes import camera
    # .env réel : accès libre en test. Vide plutôt que supprimée : load_dotenv() (import de
    # engine.ingest) la recréerait, mais n'écrase jamais une variable existante.
    monkeypatch.setenv("MYSA_DASHBOARD_PASSWORD", "")
    auth.reset()
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(camera, "CAPTURE_DIR", str(tmp_path / "captures"))
    camera._frames.clear()
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setattr(model, "MODELS_DIR", str(models))
    model._cache.clear()
    reference._cache.clear()
    analyzer.reset()
    storage.init_db()
    yield tmp_path
    analyzer.reset()
