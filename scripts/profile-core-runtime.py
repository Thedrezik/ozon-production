"""Isolated mock core: idle CPU/RSS and SQL per read. Never use a deployment DB."""
import ctypes
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.cli import create_admin
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.orders import seed_mock_orders
from app.ozon import MockOzonClient
from app.rbac import seed_rbac


def peak_rss_mib():
    if sys.platform != "win32":
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == "darwin" else 1024)

    class Memory(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage")]
    counters = Memory()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    read = ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_ulong]
    if not read(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize / 1024**2


with tempfile.TemporaryDirectory(prefix="ozon-core-profile-") as folder:
    config = Settings(app_env="test", database_url=f"sqlite:///{Path(folder) / 'synthetic.db'}",
        ozon_mock_mode=True, enabled_optional_features="", ozon_webhook_enabled=True,
        ozon_reconciliation_enabled=True, telegram_bot_token="synthetic-token",
        telegram_bot_username="synthetic_bot", telegram_webhook_secret="synthetic-secret",
        upload_dir=str(Path(folder) / "uploads"))
    app = create_app(config)
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        db.commit()
        create_admin("admin", "Synthetic admin", "synthetic-password-123", db)
        seed_mock_orders(db)
        db.commit()
    sql = []
    event.listen(app.state.engine, "before_cursor_execute", lambda *args: sql.append(args[2]))
    with patch("app.main.ManagedOzonClient", return_value=MockOzonClient()), patch("app.telegram._telegram_request"), TestClient(app) as client:
        # Wait until the initial reconciliation has finished, before idle measurement.
        assert client.post("/api/auth/login", json={"username": "admin", "password": "synthetic-password-123"}).status_code == 200
        deadline = time.monotonic() + 10
        while client.get("/api/ozon/sync-state").json()["status"] != "SUCCESS":
            if time.monotonic() > deadline:
                raise RuntimeError("Mock reconciliation failed")
            time.sleep(.1)
        sql.clear()
        wall, cpu = time.perf_counter(), time.process_time()
        time.sleep(20)
        elapsed, used = time.perf_counter() - wall, time.process_time() - cpu
        print(json.dumps({"idle_seconds": round(elapsed, 2), "idle_cpu_seconds": round(used, 4),
            "one_cpu_percent": round(used / elapsed * 100, 3), "idle_sql": len(sql),
            "process_peak_rss_mib": round(peak_rss_mib(), 2),
            "loops": ["webhook inbox", "reconciliation", "Telegram delivery"]}))
        for path in ("/api/dashboard", "/api/orders", "/api/orders/feed", "/api/orders?problems=true", "/api/blockers/summary", "/api/ozon/sync-state"):
            sql.clear()
            started = time.perf_counter()
            response = client.get(path)
            assert response.status_code == 200, path
            print(json.dumps({"path": path, "sql": len(sql), "ms": round((time.perf_counter() - started) * 1000, 2)}))
