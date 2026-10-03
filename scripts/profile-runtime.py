"""Offline startup/photo smoke and process peak RSS; requires backend dev dependencies."""
import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
parser = argparse.ArgumentParser()
parser.add_argument("--format", choices=("JPEG", "PNG", "WEBP"), default="JPEG")
image_format = parser.parse_args().format
started = time.perf_counter()
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base
from app.main import create_app
from app.orders import seed_mock_orders
from app.photos import compress_image
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
    read_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    read_memory.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_ulong]
    if not read_memory(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize / 1024**2


with tempfile.TemporaryDirectory(prefix="ozon-synthetic-profile-") as folder:
    root = Path(folder)
    app = create_app(Settings(database_url=f"sqlite:///{root / 'synthetic.db'}", app_env="test",
        ozon_mock_mode=True, ozon_webhook_enabled=False, ozon_reconciliation_enabled=False,
        vapid_private_key="", telegram_bot_token="", upload_dir=str(root / "uploads")))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        seed_mock_orders(db)
        db.commit()
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health/ready").status_code == 200
        print(json.dumps({"cold_import_seed_startup_seconds": round(time.perf_counter() - started, 3),
                          "startup_peak_rss_mib": round(peak_rss_mib(), 2)}))
        # Worst accepted dimensions; generated privately, no user/production image.
        source = root / "synthetic-image"
        # Source creation is outside the API process. In particular WebP's
        # encoder peak must not be confused with the upload decoder footprint.
        height = "2500" if image_format == "WEBP" else "5000"
        subprocess.run([sys.executable, "-c", ("import sys; from PIL import Image; "
            "image=Image.new('RGB', (4000,int(sys.argv[3])), 'white'); image.save(sys.argv[1], format=sys.argv[2])"),
            str(source), image_format, height], check=True)
        photo_started = time.perf_counter()
        output, width, height = compress_image(source.read_bytes(), f"image/{image_format.lower()}")
        assert max(width, height) <= 1600
        print(json.dumps({"format": image_format,
                          "synthetic_photo_seconds": round(time.perf_counter() - photo_started, 3),
                          "process_peak_rss_mib": round(peak_rss_mib(), 2), "compressed_bytes": len(output)}))
