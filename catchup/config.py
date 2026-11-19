"""Paths, constants and tiny helpers shared by the whole prototype."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATERIALS_DIR = ROOT / "materials"
MEMORY_DIR = ROOT / "memory"
LOGS_DIR = ROOT / "logs"
COURSE_MAP_PATH = ROOT / "data" / "course_map.json"
SYSTEM_PROMPT_PATH = ROOT / "prompts" / "system_prompt.md"
TRACE_PATH = LOGS_DIR / "trace.jsonl"
INBOX_PATH = MEMORY_DIR / "lecturer_inbox.json"

# Any OpenRouter model that supports tool calling works. Change it in .env.
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"

STEP_BUDGET = 6            # max plan->act->observe steps per student message
MASTERY_CORRECT = 2        # correct answers needed before a topic counts as mastered
REVEAL_AFTER_ATTEMPTS = 2  # wrong attempts before the tutor may show a solution
HISTORY_MESSAGES = 10      # how much chat history is sent back to the model
MAX_INPUT_CHARS = 2000


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=value per line) so we need no extra dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_course_map(path: Path = COURSE_MAP_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_system_prompt(path: Path = SYSTEM_PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def materials_signature(directory: Path = MATERIALS_DIR) -> str:
    """Changes whenever a file in materials/ changes, so the index is rebuilt."""
    parts = []
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            parts.append(f"{p.name}:{p.stat().st_mtime_ns}:{p.stat().st_size}")
    return "|".join(parts)
