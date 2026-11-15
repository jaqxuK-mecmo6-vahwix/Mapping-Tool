"""Cached HTTP downloads. A file is fetched once; later runs reuse it (idempotent).

Every download is recorded (URL, local path, size, sha256, fetch time) in
cache/downloads/_index.json so DATA_SOURCES.md and the build report can cite exact versions.
"""
from __future__ import annotations

import hashlib
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import DOWNLOAD_DIR

USER_AGENT = "RadiusStatsEurope-pipeline/0.1 (non-commercial research build)"
_INDEX = DOWNLOAD_DIR / "_index.json"


def _load_index() -> dict:
    if _INDEX.exists():
        return json.loads(_INDEX.read_text())
    return {}


def _save_index(idx: dict) -> None:
    _INDEX.parent.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(idx, indent=2, sort_keys=True))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, *, refresh: bool = False, retries: int = 3, timeout: int = 600) -> Path:
    """Download `url` to `dest` unless it already exists. Returns `dest`."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        idx = _load_index()
        key = str(dest.relative_to(DOWNLOAD_DIR))
        if key not in idx:  # file placed by hand / earlier run: record it once
            idx[key] = {"url": url, "bytes": dest.stat().st_size, "sha256": sha256(dest),
                        "fetched": datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
            _save_index(idx)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT}) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
            idx = _load_index()
            idx[str(dest.relative_to(DOWNLOAD_DIR))] = {
                "url": url,
                "bytes": dest.stat().st_size,
                "sha256": sha256(dest),
                "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            _save_index(idx)
            return dest
        except Exception as e:  # noqa: BLE001 - retried, then re-raised
            last_err = e
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed after {retries} attempts: {url}: {last_err}")


def extract_member(zip_path: Path, member: str, dest: Path) -> Path:
    """Extract one member of a zip archive to `dest` (cached)."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        tmp = dest.with_suffix(dest.suffix + ".part")
        with z.open(member) as src, open(tmp, "wb") as out:
            while chunk := src.read(1 << 20):
                out.write(chunk)
        tmp.replace(dest)
    return dest


def download_index() -> dict:
    return _load_index()
