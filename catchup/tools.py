"""Tools the agent can call.

The model decides WHEN to use a tool; this file decides WHAT each tool can do.
Every tool validates its input and returns a small JSON result. Errors are
returned as {"error": ...} so the model can observe them and react.
"""
from __future__ import annotations

from datetime import date, datetime

from . import config, memory as memory_module, planner

MISTAKE_TYPES = ["none", "conceptual", "computational", "misread_question", "incomplete"]

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "Search the lecturer-approved Linear Algebra course material. Call this before explaining "
                "any course content or writing a quiz question. Returns chunks with ids like S12 to cite."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Short English keyword query, e.g. 'eigenvalue definition'."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_study_plan",
            "description": (
                "Build and save the personal catch-up plan: Linear Algebra topics ordered so each one is ready "
                "before the ML lecture that needs it, then the rest before the LA exam. Also produces a calendar "
                "file. Call when the student gives or changes their exam date or weekly hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_date": {"type": "string", "description": "LA exam date, YYYY-MM-DD."},
                    "hours_per_week": {"type": "number", "description": "Hours per week the student can study LA."},
                },
                "required": ["exam_date", "hours_per_week"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_quiz_question",
            "description": (
                "Register ONE open 'explain why' question on a topic so the app can track attempts and mastery. "
                "The topic must be unlocked, and the question must be based on chunks returned by search_notes. "
                "After calling it, show the question to the student."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "question": {"type": "string"},
                    "key_points": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "2-4 short key points a correct answer must contain. Hidden from the student.",
                    },
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Ids of the search_notes chunks the question is based on, e.g. ['S12'].",
                    },
                },
                "required": ["topic_id", "question", "key_points", "source_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grade_answer",
            "description": (
                "Record your judgement of the student's answer to the OPEN QUESTION. Call it every time the "
                "student attempts an answer, before you reply. The app then updates mastery, unlocks topics, "
                "tracks repeated mistakes and schedules reviews."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "correct": {"type": "boolean", "description": "True only if the key points are covered."},
                    "mistake_type": {"type": "string", "enum": MISTAKE_TYPES},
                    "note": {"type": "string", "description": "One sentence: what exactly was wrong or missing."},
                },
                "required": ["correct", "mistake_type", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_for_lecturer",
            "description": (
                "Send a question to the lecturer's inbox. Use it when the course material does not cover the "
                "question, when the material seems wrong or contradictory, or when you are unsure."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["question", "reason"],
            },
        },
    },
]


class Toolbox:
    def __init__(self, index, memory, course_map: dict, today: date, retrieved: dict | None = None,
                 inbox_path=config.INBOX_PATH):
        self.index = index
        self.memory = memory
        self.course_map = course_map
        self.today = today
        self.inbox_path = inbox_path
        # chunks the agent has really seen in this session: id -> source label
        self.retrieved = retrieved if retrieved is not None else {}

    def call(self, name: str, args: dict) -> dict:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool '{name}'."}
        if "_invalid_arguments" in args:
            return {"error": "Arguments were not valid JSON. Call the tool again with a JSON object."}
        try:
            return handler(**args)
        except TypeError as exc:
            return {"error": f"Wrong arguments for {name}: {exc}"}

    # ---------- tools ----------
    def _tool_search_notes(self, query: str) -> dict:
        outcome = self.index.search(str(query))
        if not outcome["found"]:
            return {
                "found": False,
                "message": (
                    "Nothing relevant in the approved course material. Do NOT answer from general knowledge. "
                    "Tell the student it is not covered and offer to flag it for the lecturer."
                ),
            }
        for chunk in outcome["results"]:
            self.retrieved[chunk["id"]] = chunk["source"]
        return outcome

    def _tool_create_study_plan(self, exam_date: str, hours_per_week: float) -> dict:
        try:
            exam = date.fromisoformat(str(exam_date))
        except ValueError:
            return {"error": "exam_date must be YYYY-MM-DD."}
        try:
            hours = float(hours_per_week)
        except (TypeError, ValueError):
            return {"error": "hours_per_week must be a number."}
        if exam <= self.today:
            return {"error": f"exam_date must be after today ({self.today.isoformat()})."}
        if not 1 <= hours <= 40:
            return {"error": "hours_per_week must be between 1 and 40."}

        plan = planner.build_plan(self.course_map, self.memory.mastered(), self.today, exam, hours)
        self.memory.profile["student"]["exam_date"] = exam.isoformat()
        self.memory.profile["student"]["hours_per_week"] = hours
        self.memory.profile["plan"] = plan
        self.memory.save()
        return {
            "saved": True,
            "fits": plan["fits"],
            "warnings": plan["warnings"],
            "min_hours_per_week_to_be_on_time": plan["min_hours_per_week"],
            "items": [
                {k: item[k] for k in ("title", "start", "finish", "needed_for", "on_time")}
                for item in plan["items"]
            ],
            "exam_simulation": plan["exam_simulation"],
            "note": "The plan and a calendar file (.ics) are now on the student's 'Study plan' page. "
                    "If fits is false, say so honestly and give the options from the warning.",
        }

    def _tool_ask_quiz_question(self, topic_id: str, question: str, key_points: list, source_ids: list) -> dict:
        if topic_id not in self.memory.topics:
            return {"error": f"Unknown topic_id. Valid ids: {', '.join(self.memory.topics)}."}
        status = self.memory.status(topic_id)
        if status == "locked":
            missing = [self.memory.topics[t]["title"] for t in self.memory.missing_prereqs(topic_id)]
            return {
                "error": "TOPIC_LOCKED",
                "message": (
                    f"'{self.memory.topics[topic_id]['title']}' is locked. The student must first master: "
                    f"{', '.join(missing)}. Explain this and offer the first missing topic instead."
                ),
            }
        if not isinstance(key_points, list) or len(key_points) < 2:
            return {"error": "Give at least 2 key_points."}
        valid = [s for s in (source_ids or []) if s in self.retrieved]
        if not valid:
            return {
                "error": "NOT_GROUNDED",
                "message": "source_ids must be chunk ids returned by search_notes in this session. "
                           "Call search_notes first and base the question on its results.",
            }
        self.memory.open_question(topic_id, str(question), [str(k) for k in key_points], valid)
        return {
            "registered": True,
            "topic_status": status,
            "instruction": "Now show this exact question to the student. Do not include the key points or any hint.",
        }

    def _tool_grade_answer(self, correct: bool, mistake_type: str, note: str) -> dict:
        if not self.memory.profile.get("pending_question"):
            return {"error": "There is no open question to grade. Use ask_quiz_question first."}
        if mistake_type not in MISTAKE_TYPES:
            mistake_type = "conceptual"
        result = self.memory.record_answer(bool(correct), mistake_type, str(note), self.today)
        if correct:
            instruction = "Confirm briefly what was right. Then offer the next step."
        elif result["question_closed"]:
            instruction = ("Attempts are used up. You may now walk through the solution step by step, citing "
                           "sources, then suggest trying a new question on this topic.")
        else:
            instruction = ("Do NOT reveal the solution or the key points. Point to what is wrong, give one "
                           "small hint, and ask the student to try again.")
        if result["repeated_mistake"]:
            instruction += " This is a repeated mistake: explain the idea in a different way than before."
        result["recorded"] = True
        result["needed_for_mastery"] = config.MASTERY_CORRECT
        result["instruction"] = instruction
        return result

    def _tool_flag_for_lecturer(self, question: str, reason: str) -> dict:
        memory_module.add_to_inbox({
            "when": datetime.now().isoformat(timespec="seconds"),
            "student": self.memory.profile["student"]["name"],
            "question": str(question)[:500],
            "reason": str(reason)[:300],
        }, self.inbox_path)
        return {"flagged": True, "instruction": "Tell the student the question was sent to the lecturer."}
