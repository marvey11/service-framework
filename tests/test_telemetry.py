import json
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from service_framework.telemetry.daemon import app

client = TestClient(app)


def test_telemetry_routes(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    state_dir = tmp_path / "data" / "sfw" / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "demo.json"
    state_file.write_text(json.dumps({"service_name": "demo", "status": "RUNNING", "pid": 1234}))

    response = client.get("/api/v1/services")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get("/api/v1/services/demo")
    assert response.status_code == 200
    assert response.json()["service_name"] == "demo"

    # Test Config Put and Get
    cfg_data = {"retries": 3}
    put_resp = client.put("/api/v1/config/demo", json=cfg_data)
    assert put_resp.status_code == 200

    get_cfg = client.get("/api/v1/config/demo")
    assert get_cfg.status_code == 200
    assert get_cfg.json()["retries"] == 3
