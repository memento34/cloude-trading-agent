from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class StateStore:
    """
    Persistent key-value store backed by flat files.

    FIX: write_json now uses an atomic temp-file + os.replace() pattern.
    If the process crashes mid-write, the old file is preserved intact
    and the corrupt temporary is cleaned up automatically.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path(self, *parts: str) -> Path:
        path = self.base_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def read_json(self, *parts: str, default: Any = None) -> Any:
        path = self.path(*parts)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text())
        except Exception:
            return default

    def write_json(self, *parts: str, payload: Any) -> Path:
        """
        Atomically write JSON to *parts using a temp file + os.replace().

        This guarantees that readers always see either the old complete file
        or the new complete file – never a partially written state.
        """
        target = self.path(*parts)
        text = json.dumps(payload, indent=2, default=str)
        # Write to a sibling temp file in the same directory (same filesystem
        # → os.replace is guaranteed atomic on POSIX)
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp_path, target)   # atomic on POSIX; near-atomic on Windows
        except Exception:
            # Clean up the temp file on error to avoid littering the state dir
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return target

    def append_jsonl(self, *parts: str, payload: Dict) -> Path:
        path = self.path(*parts)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
        return path

    def read_jsonl(self, *parts: str, limit: int | None = None) -> List[Dict[str, Any]]:
        path = self.path(*parts)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            if limit is not None and limit > 0:
                return rows[-limit:]
            return rows
        except Exception:
            return []

    def ensure_default(self, *parts: str, payload: Any) -> Any:
        current = self.read_json(*parts)
        if current is None:
            self.write_json(*parts, payload=payload)
            return payload
        return current


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
