"""Desktop launcher for the packaged Translayer web app."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


def packaged_root() -> Path:
    """Return the application root for source and PyInstaller builds."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[1]


def configure_packaged_tools() -> None:
    """Expose bundled third-party command-line tools when present."""
    root = packaged_root()
    candidates = [
        root / "tools" / "tesseract",
        root / "tools" / "tesseract" / "bin",
        root / "tools" / "poppler" / "Library" / "bin",
        root / "tools" / "poppler" / "bin",
        root / "tools" / "LibreOffice" / "program",
    ]
    existing = [str(path) for path in candidates if path.exists()]
    if existing:
        os.environ["PATH"] = os.pathsep.join([*existing, os.environ.get("PATH", "")])

    tessdata = root / "tools" / "tesseract" / "tessdata"
    if tessdata.exists() and "TESSDATA_PREFIX" not in os.environ:
        os.environ["TESSDATA_PREFIX"] = str(tessdata)


def pick_port(preferred: int = 8000) -> int:
    for port in [preferred, *range(8001, 8021)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No available local port found in range 8000-8020")


def open_browser_later(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    configure_packaged_tools()
    port = pick_port()
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()
    print(f"Translayer is running at {url}")
    print("Keep this window open while using Translayer.")
    uvicorn.run("translayer.api.app:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
