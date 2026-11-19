"""Logs: every step of every turn goes to logs/trace.jsonl.

This is the debugging tool and the testing evidence. The UI also shows the
steps of each turn so the jury can see the agent act, not just talk.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config


def _short(value, limit: int = 600):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " …"


class Tracer:
    def __init__(self, path: Path = config.TRACE_PATH):
        self.path = Path(path)
        self.turn_id = ""
        self.events = []

    def start_turn(self) -> None:
        self.turn_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.events = []

    def log(self, kind: str, **data) -> None:
        event = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "turn": self.turn_id,
            "step": len(self.events) + 1,
            "type": kind,
        }
        event.update({k: _short(v) if isinstance(v, (str, dict, list)) else v for k, v in data.items()})
        self.events.append(event)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass  # logging must never break the demo


def read_trace(path: Path = config.TRACE_PATH, last: int = 300) -> list:
    if not Path(path).exists():
        return []
    lines = Path(path).read_text(encoding="utf-8").splitlines()[-last:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
