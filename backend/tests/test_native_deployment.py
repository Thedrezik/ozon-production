"""Native deployment security boundaries without host services or providers."""
import importlib.util
import io
import subprocess
import tarfile
from configparser import ConfigParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize("name,kind", [("../escape", "file"), ("/absolute", "file"),
    ("link", "symlink"), ("hard", "hardlink"), ("dev", "device"), ("a\\b", "file")])
def test_restore_rejects_unsafe_members(name, kind):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.type = {"file": tarfile.REGTYPE, "symlink": tarfile.SYMTYPE,
                       "hardlink": tarfile.LNKTYPE, "device": tarfile.CHRTYPE}[kind]
        archive.addfile(member)
    data.seek(0)
    with tarfile.open(fileobj=data) as archive, pytest.raises(ValueError):
        module("validate-backup").validate(archive)


def test_env_is_data_and_db_secrets_never_in_argv(tmp_path, monkeypatch, capsys):
    helper = module("native-env")
    env = tmp_path / "private.env"
    password = "synthetic'password$(touch forbidden)"
    env.write_text(f"POSTGRES_USER=ozon\nPOSTGRES_DB=ozon\nPOSTGRES_PASSWORD={password}\n")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(helper.subprocess, "run", run)
    monkeypatch.setattr("sys.argv", ["native-env.py", str(env), "provision"])
    helper.main()
    command, kwargs = calls[0]
    assert password not in " ".join(command)
    assert "PASSWORD 'synthetic''password$(touch forbidden)'" in kwargs["input"]
    assert kwargs["capture_output"] and not capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["native-env.py", str(env), "run", "--", "pg_restore", "dump"])
    with pytest.raises(SystemExit) as result:
        helper.main()
    assert result.value.code == 0
    command, kwargs = calls[1]
    assert command == ["pg_restore", "dump", "--dbname", "ozon"]
    assert kwargs["env"]["PGPASSWORD"] == password
    assert kwargs["env"]["PGHOST"] == "127.0.0.1"


def test_no_production_docker_and_unprivileged_unit():
    assert not (ROOT / "docker-compose.production.yml").exists()
    unit = (ROOT / "deployment/ozon-production.service").read_text()
    assert "User=ozon-app" in unit and "--workers 1" in unit
    assert "--host 127.0.0.1" in unit and "KillSignal=SIGTERM" in unit
    assert "ProtectSystem=strict" in unit and "ReadWritePaths=/var/lib/ozon-production/uploads" in unit
    for path in (ROOT / "deployment").glob("*.service"):
        config = ConfigParser(strict=False, interpolation=None)
        config.read(path)
        assert config.has_section("Unit") and config.has_section("Service")
        assert config.get("Service", "ExecStart").startswith("/")
    config = ConfigParser(interpolation=None)
    config.read(ROOT / "deployment/ozon-backup.timer")
    assert config.get("Timer", "OnCalendar") == "*-*-* 02:00:00 UTC"
    for script in ("bootstrap-vps.sh", "native-release.sh", "backup.sh", "restore.sh",
                   "rollback-native.sh", "backup-restore-native-drill.sh"):
        assert "docker " not in (ROOT / "scripts" / script).read_text().lower()


def test_application_and_backup_database_must_match(tmp_path, monkeypatch):
    env = tmp_path / "production.env"
    monkeypatch.setattr("sys.argv", ["init-production-env.py", "--domain", "8.8.8.8",
        "--release", "synthetic", "--output", str(env)])
    module("init-production-env").main()
    monkeypatch.setattr("sys.argv", ["native-env.py", str(env), "check"])
    module("native-env").main()
    env.write_text(env.read_text().replace("POSTGRES_DB=ozon", "POSTGRES_DB=other"))
    with pytest.raises(SystemExit, match="settings must match"):
        module("native-env").main()
