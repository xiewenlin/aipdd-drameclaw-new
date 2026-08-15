"""Vercel Services entrypoint for the FastAPI data plane."""

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

work_root = Path(tempfile.gettempdir()) / "dramaclaw"
os.environ.setdefault("ST_EDITION", "ce")
os.environ.setdefault("ST_COOKIE_SECURE", "1")
os.environ.setdefault("DRAMACLAW_WORK_ROOT", str(work_root))
os.environ.setdefault("NOVELVIDEO_DATA_ROOT", str(work_root / "legacy"))
os.environ.setdefault("DOWNLOAD_VIA_OSS", "0")
os.environ.setdefault("STATIC_VIA_OSS", "0")

from novelvideo.api.app import app  # noqa: E402


__all__ = ["app"]
