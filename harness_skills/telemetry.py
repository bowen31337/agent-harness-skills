"""Harness telemetry singleton."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional


class HarnessTelemetry:
    _shared: Optional["HarnessTelemetry"] = None

    def __init__(self, output_path: str = "docs/harness-telemetry.json") -> None:
        self.output_path = output_path
        self._session_id: Optional[str] = None
        self._session_gates: dict[str, int] = {}
        self._data: dict[str, Any] = {"sessions": []}

    @classmethod
    def _get_shared(cls) -> "HarnessTelemetry":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def _start_session(self, session_id: str) -> None:
        self._session_id = session_id
        self._session_gates = {}

    def flush(self) -> None:
        try:
            path = Path(self.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass
