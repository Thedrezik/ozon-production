"""Safety boundaries for generated env and isolated destructive drill config."""
import importlib.util
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("drill_guard", ROOT / "scripts/check-drill-config.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def drill_config():
    prefix = "ozon-backup-drill-synthetic"
    config = {"name": prefix, "volumes": {key: {"name": f"{prefix}_{key}"} for key in
              ("postgres_data", "uploads", "backups", "caddy_data", "caddy_config")}, "services": {
        "backend": {"environment": {"APP_ENV": "test", "OZON_MOCK_MODE": "true",
                    "OZON_RECONCILIATION_ENABLED": "false", "OZON_WEBHOOK_ENABLED": "false"},
                    "volumes": [{"type": "volume", "source": "uploads", "target": "/data/uploads"}]},
        "postgres": {"volumes": [{"type": "volume", "source": "postgres_data"}]}}}
    return config, prefix


def test_drill_guards_resolved_volumes_and_mounts():
    config, prefix = drill_config()
    assert len(guard.validate(config, prefix)) == 5
    variants = []
    wrong = deepcopy(config); wrong["volumes"]["uploads"]["name"] = "ozon-production_uploads"; variants.append(wrong)
    wrong = deepcopy(config); wrong["volumes"]["uploads"]["external"] = True; variants.append(wrong)
    wrong = deepcopy(config); wrong["services"]["backend"]["volumes"][0]["type"] = "bind"; variants.append(wrong)
    wrong = deepcopy(config); wrong["services"]["backend"]["environment"]["OZON_API_KEY"] = "sentinel"; variants.append(wrong)
    wrong = deepcopy(config); wrong["services"]["backend"]["environment"]["OZON_RECONCILIATION_ENABLED"] = "true"; variants.append(wrong)
    wrong = deepcopy(config); wrong["services"]["postgres"]["ports"] = [5432]; variants.append(wrong)
    for variant in variants:
        with pytest.raises(ValueError):
            guard.validate(variant, prefix)
    with pytest.raises(ValueError):
        guard.validate(config, "ozon-production")


def test_generated_production_env_is_valid_private_and_never_overwritten(tmp_path):
    target = tmp_path / "production.env"
    command = [sys.executable, str(ROOT / "scripts/init-production-env.py"), "--domain", "factory.example.org",
               "--proxy-subnet", "172.29.40.0/28", "--database-subnet", "172.29.41.0/28",
               "--release", "synthetic-release", "--output", str(target)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    # Explicit env values override any existing host secrets without logging them.
    values = dict(line.split("=", 1) for line in target.read_text().splitlines() if line and not line.startswith("#"))
    settings = Settings(_env_file=None, **{key.lower(): value for key, value in values.items()})
    assert settings.app_env == "production" and not settings.ozon_mock_mode
    assert len(values["POSTGRES_PASSWORD"]) == 48
    assert settings.ozon_webhook_trusted_proxies == "172.29.40.2/32"
    assert all(values[key] not in result.stdout for key in ("APP_SECRET", "POSTGRES_PASSWORD", "OZON_CREDENTIALS_MASTER_KEY"))
    original = target.read_bytes()
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0
    assert target.read_bytes() == original
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    overlapping = command.copy()
    overlapping[overlapping.index("--database-subnet") + 1] = "172.29.40.0/28"
    assert subprocess.run(overlapping, capture_output=True, check=False).returncode != 0
