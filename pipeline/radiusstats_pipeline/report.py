"""Collects gaps, fallbacks, NUTS mappings and checks; written as build_report.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Report:
    def __init__(self) -> None:
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.entries: list[dict] = []
        self.checks: list[dict] = []

    def _add(self, level: str, kind: str, **kw) -> None:
        e = {"level": level, "kind": kind, **kw}
        self.entries.append(e)
        tag = {"info": " ", "fallback": "~", "gap": "!", "mapping": ">"}.get(level, "?")
        print(f"[{tag}] {kind}: " + ", ".join(f"{k}={v}" for k, v in kw.items() if k != "detail"))

    def note(self, kind: str, **kw) -> None:
        self._add("info", kind, **kw)

    def fallback(self, kind: str, **kw) -> None:
        self._add("fallback", kind, **kw)

    def gap(self, kind: str, **kw) -> None:
        self._add("gap", kind, **kw)

    def mapping(self, kind: str, **kw) -> None:
        self._add("mapping", kind, **kw)

    def check(self, name: str, ok: bool, **kw) -> None:
        self.checks.append({"name": name, "ok": bool(ok), **kw})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} " + ", ".join(f"{k}={v}" for k, v in kw.items()))

    def write(self, path: Path, extra: dict | None = None) -> None:
        out = {
            "started": self.started,
            "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": {
                "gaps": sum(e["level"] == "gap" for e in self.entries),
                "fallbacks": sum(e["level"] == "fallback" for e in self.entries),
                "mappings": sum(e["level"] == "mapping" for e in self.entries),
                "checks_failed": sum(not c["ok"] for c in self.checks),
            },
            **(extra or {}),
            "entries": self.entries,
            "checks": self.checks,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, default=float))
