import threading
import json
from datetime import datetime
from typing import List, Dict, Optional


class InterceptLogger:
    """
    A thread-safe fake logger compatible with Python's logging.Logger interface.
    It captures log output as structured dicts but preserves multi-line messages
    as single logical entries (joining lines without breaking formatting).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: List[Dict[str, str]] = []
        self._buffer = ""

    def _record(self, level: str, msg: str):
        timestamp = datetime.now().isoformat(sep=" ", timespec="microseconds")
        entry = {
            "timestamp": timestamp,
            "level": level,
            "msg": msg,
        }
        with self._lock:
            self._entries.append(entry)

    # These mimic standard logging.Logger methods
    def info(self, msg: str):
        self._append("INFO", msg)

    def error(self, msg: str):
        self._append("ERROR", msg)

    def _append(self, level: str, msg: str):
        """Append message, preserving multi-line structure as one entry."""
        # If msg contains embedded newlines, split but store each as full block
        if "\n" in msg:
            parts = msg.splitlines()
            for part in parts:
                if part.strip() == "":
                    continue
                self._record(level, part)
        else:
            self._record(level, msg)

    def entries(self) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._entries)

    def as_string(self) -> str:
        """
        Return logs formatted similarly to the standard logging output.
        """
        with self._lock:
            lines = []
            for e in self._entries:
                lines.append(
                    f"[{e['timestamp']}] {e['level']:<7} : {e['msg']}"
                )
            return "\n".join(lines)

    def as_json(self) -> str:
        """Return logs as a JSON string."""
        with self._lock:
            return json.dumps(self._entries, ensure_ascii=False, indent=2)
