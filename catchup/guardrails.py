"""Guardrails written as code.

The system prompt asks the model to behave. These checks make sure it did.
A prompt can be talked around; a check in code cannot.

Input checks run before the model sees the message.
Output checks run on the model's draft before the student sees it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import config
from .retrieval import tokenize

INJECTION_PATTERNS = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"(disregard|forget) (all |any |the |your )?(previous |prior )?(instructions|rules)",
    r"(reveal|show|print|repeat).{0,25}(system prompt|your instructions|key points)",
    r"\byou are now\b",
    r"\b(developer|jailbreak|dan) mode\b",
]

REVEAL_PATTERNS = [
    r"\b(give|tell|show|send|write)\s+(me\s+)?(just\s+)?the\s+(full\s+|final\s+|right\s+|correct\s+|whole\s+)?(answer|solution)",
    r"\bwhat('?s| is) the (right |correct |final )?(answer|solution)",
    r"\b(solve|do|answer) (it|this|that) for me\b",
    r"\bjust (answer|solve)\b",
    r"(скажи|дай|покажи|напиши)\s+(мне\s+)?(просто\s+|уже\s+)?(правильный\s+)?(ответ|решение)",
    r"(dammi|dimmi|dai|scrivi)\s*(mi\s+)?(solo\s+)?la\s+(risposta|soluzione)",
]

GRADED_WORK_PATTERNS = [
    r"(do|solve|write|finish|complete)\s+(my|the|this)\s+(homework|assignment|report|project|exam|midterm)",
    r"(сделай|реши|напиши)\s+(за меня|мою|мне)\s*(домашк|задани|отчет|отчёт|проект)?",
    r"(fai|risolvi|scrivi)\s+(il mio|la mia|i miei)\s+(compito|compiti|progetto|relazione)",
]

CITATION_GROUP = re.compile(r"\[(S\d+(?:\s*[,;]\s*S\d+)*)\]")


@dataclass
class InputVerdict:
    blocked: bool = False
    reply: str = ""
    directive: str = ""
    text: str = ""
    flags: list = field(default_factory=list)


@dataclass
class OutputVerdict:
    ok: bool = True
    text: str = ""
    violation: str = ""
    correction: str = ""
    fallback: str = ""
    flags: list = field(default_factory=list)


def _matches(patterns: list, text: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def check_input(text: str, pending: dict | None) -> InputVerdict:
    verdict = InputVerdict(text=text.strip())
    if len(verdict.text) > config.MAX_INPUT_CHARS:
        verdict.text = verdict.text[: config.MAX_INPUT_CHARS]
        verdict.flags.append("input_truncated")

    if _matches(INJECTION_PATTERNS, verdict.text):
        verdict.blocked = True
        verdict.flags.append("prompt_injection_blocked")
        verdict.reply = (
            "I can't change my rules or show my internal instructions. I'm your CatchUp tutor for "
            "Linear Algebra. What would you like to work on?"
        )
        return verdict

    if pending and _matches(REVEAL_PATTERNS, verdict.text):
        verdict.flags.append("reveal_request")
        verdict.directive = (
            "[APP RULE, enforced in code] The student is asking for the solution to the open question, but "
            f"they have used {pending['attempts']} of {config.REVEAL_AFTER_ATTEMPTS} attempts. Do not state the "
            "solution or any key point. Say kindly that you won't hand it over yet, give ONE small hint, and "
            "ask them to try. Do not call grade_answer for this message."
        )
    elif _matches(GRADED_WORK_PATTERNS, verdict.text):
        verdict.flags.append("graded_work_request")
        verdict.directive = (
            "[APP RULE, enforced in code] This looks like a request to do graded work for the student. Do not "
            "produce a finished solution. Offer to explain the underlying topic from the course material and "
            "guide them step by step instead."
        )
    return verdict


def clean_citations(text: str, valid_ids) -> tuple:
    """Remove citation ids the agent never retrieved. Returns (text, valid ids used, removed ids)."""
    used, removed = [], []

    def fix(match):
        ids = re.findall(r"S\d+", match.group(1))
        keep = [i for i in ids if i in valid_ids]
        used.extend(keep)
        removed.extend(i for i in ids if i not in valid_ids)
        return "[" + ", ".join(keep) + "]" if keep else ""

    cleaned = CITATION_GROUP.sub(fix, text)
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    return cleaned, list(dict.fromkeys(used)), list(dict.fromkeys(removed))


def leaks_solution(text: str, key_points: list, question: str = "") -> bool:
    """True if the draft contains most of the hidden key points of the open question.

    Heuristic: a key point counts as revealed when at least 80% of its content
    words appear in the draft. More than half of the key points revealed = leak.
    Words that are already in the question itself are not secrets, so they are ignored.
    """
    words = set(tokenize(text))
    public = set(tokenize(question))
    revealed, countable = 0, 0
    for point in key_points:
        point_words = set(tokenize(point)) - public
        if not point_words:
            continue
        countable += 1
        if len(point_words & words) / len(point_words) >= 0.8:
            revealed += 1
    if countable == 0:
        return False
    return revealed >= max(1, math.floor(countable / 2) + 1)


def check_output(text: str, pending: dict | None, retrieved: dict, tools_used: list) -> OutputVerdict:
    cleaned, used, removed = clean_citations(text, retrieved)
    verdict = OutputVerdict(text=cleaned.strip())
    if removed:
        verdict.flags.append("removed_unknown_citations:" + ",".join(removed))

    # 1. Do not hand over the answer while the student still has attempts left.
    #    (Skipped in the turn that creates the question: the lesson before it may state the ideas.)
    just_asked = "ask_quiz_question" in tools_used
    if pending and not just_asked and leaks_solution(verdict.text, pending["key_points"], pending["question"]):
        sources = ", ".join(retrieved.get(s, s) for s in pending["source_ids"])
        verdict.ok = False
        verdict.violation = "solution_leak"
        verdict.correction = (
            "[APP CHECK] Your draft was blocked: it reveals the solution to the open question while the "
            "student still has attempts left. Rewrite it with no key points: say what to reconsider, give one "
            "small hint, and ask them to try again."
        )
        verdict.fallback = (
            "I won't hand over the answer yet. You still have an attempt left, and working it out yourself is "
            f"the point. Hint: look again at {sources}, then try to answer in your own words:\n\n"
            f"**{pending['question']}**"
        )
        return verdict

    # 2. Teaching content must come from the course material.
    if len(verdict.text) > 500 and not used and not tools_used:
        verdict.ok = False
        verdict.violation = "ungrounded_answer"
        verdict.correction = (
            "[APP CHECK] Your draft was blocked: it explains content without citing the course material. "
            "Call search_notes and cite the chunk ids like [S3], or say the material does not cover it."
        )
        verdict.fallback = (
            "I couldn't ground that in the approved course material, so I won't guess. I can flag your "
            "question for the lecturer, or we can continue with your plan. Which do you prefer?"
        )
    return verdict
