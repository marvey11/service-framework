import json
from pathlib import Path
from types import SimpleNamespace

from _pytest.monkeypatch import MonkeyPatch
from click.testing import CliRunner

from service_framework.cli import main


def test_cli_run_success(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--service-name", "cli-test", "--", "echo", "hello"])

    assert result.exit_code == 0

    state_file = tmp_path / "data" / "sfw" / "state" / "cli-test.json"
    assert state_file.exists()
    with open(state_file) as f:
        data = json.load(f)
        assert data["status"] == "SUCCESS"


def test_cli_requires_command(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--service-name", "cli-test"])

    assert result.exit_code == 1
    assert "No command or script specified" in result.output


def test_cli_handles_subprocess_failure(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def fake_run(cmd: list[str]) -> SimpleNamespace:
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr("service_framework.cli.subprocess.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--service-name", "cli-test", "--", "echo", "hello"])

    assert result.exit_code == 7
