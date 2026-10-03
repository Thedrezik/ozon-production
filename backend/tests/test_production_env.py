"""Exercise the private env generator without a VPS or real credentials."""
import importlib.util
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import Settings


@pytest.fixture
def generator():
    path = Path(__file__).resolve().parents[2] / "scripts/init-production-env.py"
    spec = importlib.util.spec_from_file_location("production_env", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments(monkeypatch, output, host):
    monkeypatch.setattr(sys, "argv", ["init-production-env.py", "--domain", host,
        "--proxy-subnet", "172.29.40.0/28", "--database-subnet", "172.29.41.0/28",
        "--release", "a" * 40, "--output", str(output)])


@pytest.mark.parametrize("host", ["8.8.8.8", "factory.example.org"])
def test_private_env_valid_and_never_overwritten(generator, tmp_path, monkeypatch, capsys, host):
    path = tmp_path / "private.env"
    arguments(monkeypatch, path, host)
    generator.main()
    values = dict(line.split("=", 1) for line in path.read_text().splitlines()
                  if line and not line.startswith("#"))
    settings = Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})
    assert settings.domain == host and settings.app_public_url == f"https://{host}"
    assert settings.ozon_api_key == "" and settings.enabled_optional_features == ""
    Fernet(settings.ozon_credentials_master_key.encode())
    stdout = capsys.readouterr().out
    assert all(values[key] not in stdout for key in (
        "APP_SECRET", "POSTGRES_PASSWORD", "OZON_CREDENTIALS_MASTER_KEY"))
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        generator.main()
    assert path.read_bytes() == before


@pytest.mark.parametrize("host", ["127.0.0.1", "192.168.0.1", "203.0.113.1", "::1",
    "999.1.2.3", "https://8.8.8.8", "factory..example.org", "example.com"])
def test_invalid_origin_creates_no_file(generator, tmp_path, monkeypatch, host):
    path = tmp_path / "private.env"
    arguments(monkeypatch, path, host)
    with pytest.raises(SystemExit):
        generator.main()
    assert not path.exists()
