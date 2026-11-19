"""Structured memory: the learner profile that persists between sessions.

One small JSON file per student. It holds facts, not chat history: which topics
are mastered, which mistakes keep coming back, the open quiz question, the plan.
Mastery is computed here, in code. The model can report a graded answer but it
cannot mark a topic as mastered or unlock the next one by itself.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config


class LearnerMemory:
    def __init__(self, path: Path, course_map: dict):
        self.path = Path(path)
        self.course_map = course_map
        self.topics = {t["id"]: t for t in course_map["topics"]}
        self.profile = self._load()

    # ---------- persistence ----------
    def _blank(self) -> dict:
        return {
            "student": {"name": "Luca", "exam_date": None, "hours_per_week": None},
            "topics": {tid: {"correct": 0, "wrong": 0} for tid in self.topics},
            "mistakes": [],
            "reviews": [],
            "pending_question": None,
            "plan": None,
        }

    def _load(self) -> dict:
        if self.path.exists():
            profile = json.loads(self.path.read_text(encoding="utf-8"))
            for tid in self.topics:  # course map may have gained topics
                profile["topics"].setdefault(tid, {"correct": 0, "wrong": 0})
            return profile
        return self._blank()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.profile, indent=2, ensure_ascii=False), encoding="utf-8")

    def reset(self) -> None:
        self.profile = self._blank()
        self.save()

    def seed_demo(self) -> None:
        """A student a few sessions in, so the live demo does not start from zero."""
        self.profile = self._blank()
        first, second = list(self.topics)[:2]
        self.profile["topics"][first] = {"correct": 2, "wrong": 0}
        self.profile["topics"][second] = {"correct": 1, "wrong": 1}
        self.profile["mistakes"].append({
            "when": datetime.now().isoformat(timespec="seconds"),
            "topic_id": second,
            "type": "computational",
            "note": "Mixed up rows and columns when multiplying a matrix by a vector.",
        })
        self.save()

    # ---------- mastery ----------
    def status(self, tid: str) -> str:
        if self.profile["topics"][tid]["correct"] >= config.MASTERY_CORRECT:
            return "mastered"
        if all(self.status(pre) == "mastered" for pre in self.topics[tid].get("prereqs", [])):
            return "available"
        return "locked"

    def mastered(self) -> set:
        return {tid for tid in self.topics if self.status(tid) == "mastered"}

    def missing_prereqs(self, tid: str) -> list:
        return [pre for pre in self.topics[tid].get("prereqs", []) if self.status(pre) != "mastered"]

    # ---------- quiz ----------
    def open_question(self, topic_id: str, question: str, key_points: list, source_ids: list) -> None:
        self.profile["pending_question"] = {
            "topic_id": topic_id,
            "question": question,
            "key_points": key_points,
            "source_ids": source_ids,
            "attempts": 0,
        }
        self.save()

    def record_answer(self, correct: bool, mistake_type: str, note: str, today: date) -> dict:
        pending = self.profile["pending_question"]
        tid = pending["topic_id"]
        before = {t: self.status(t) for t in self.topics}
        pending["attempts"] += 1
        result = {"repeated_mistake": False, "review_scheduled": None, "question_closed": False}

        if correct:
            self.profile["topics"][tid]["correct"] += 1
            self.profile["pending_question"] = None
            result["question_closed"] = True
        else:
            self.profile["topics"][tid]["wrong"] += 1
            self.profile["mistakes"].append({
                "when": datetime.now().isoformat(timespec="seconds"),
                "topic_id": tid,
                "type": mistake_type,
                "note": note,
            })
            same = [m for m in self.profile["mistakes"] if m["topic_id"] == tid and m["type"] == mistake_type]
            if len(same) >= 2:
                result["repeated_mistake"] = True
                already = any(r["topic_id"] == tid and not r.get("done") for r in self.profile["reviews"])
                if not already:
                    due = (today + timedelta(days=2)).isoformat()
                    self.profile["reviews"].append({
                        "topic_id": tid,
                        "due": due,
                        "reason": f"Repeated {mistake_type} mistake",
                        "done": False,
                    })
                    result["review_scheduled"] = due
            if pending["attempts"] >= config.REVEAL_AFTER_ATTEMPTS:
                self.profile["pending_question"] = None
                result["question_closed"] = True

        result["attempts"] = pending["attempts"]
        result["newly_unlocked"] = [
            self.topics[t]["title"] for t in self.topics
            if before[t] == "locked" and self.status(t) == "available"
        ]
        result["topic_status"] = self.status(tid)
        result["correct_so_far"] = self.profile["topics"][tid]["correct"]
        self.save()
        return result

    # ---------- views ----------
    def recurring_mistakes(self) -> list:
        counts = {}
        for m in self.profile["mistakes"]:
            key = (m["topic_id"], m["type"])
            counts[key] = counts.get(key, 0) + 1
        return [
            {"topic_id": tid, "topic": self.topics[tid]["title"], "type": kind, "count": n}
            for (tid, kind), n in sorted(counts.items(), key=lambda kv: -kv[1]) if tid in self.topics
        ]

    def state_for_prompt(self, today: date) -> str:
        """Compact snapshot injected into the system prompt on every turn."""
        student = self.profile["student"]
        lines = [
            f"Today: {today.isoformat()}",
            f"Student: {student['name']} | LA exam date: {student['exam_date'] or 'not set'} | "
            f"hours per week: {student['hours_per_week'] or 'not set'}",
            "Linear Algebra topics (id | title | status | prerequisites):",
        ]
        for tid, topic in self.topics.items():
            stats = self.profile["topics"][tid]
            prereqs = ", ".join(topic.get("prereqs", [])) or "none"
            lines.append(
                f"- {tid} | {topic['title']} | {self.status(tid)} "
                f"({stats['correct']}/{config.MASTERY_CORRECT} correct) | {prereqs}"
            )
        lines.append("ML lectures this semester (date | lecture | LA topics it needs):")
        for lecture in self.course_map.get("ml_lectures", []):
            lines.append(f"- {lecture['date']} | {lecture['title']} | {', '.join(lecture['needs'])}")

        recurring = [m for m in self.recurring_mistakes() if m["count"] >= 2]
        if recurring:
            lines.append("Recurring mistakes: " + "; ".join(
                f"{m['topic']}: {m['type']} x{m['count']}" for m in recurring))

        plan = self.profile.get("plan")
        if plan:
            upcoming = [i for i in plan["items"] if self.status(i["topic_id"]) != "mastered"]
            if upcoming:
                nxt = upcoming[0]
                lines.append(
                    f"Study plan: exists. Next item: {nxt['title']} (id {nxt['topic_id']}), "
                    f"ready by {nxt['finish']}, needed for {nxt['needed_for']}.")
            else:
                lines.append("Study plan: exists. All topics mastered; exam simulation is next.")
        else:
            lines.append("Study plan: none yet.")

        pending = self.profile.get("pending_question")
        if pending:
            lines.append(
                f"OPEN QUESTION (topic {pending['topic_id']}, wrong attempts so far: {pending['attempts']} of "
                f"{config.REVEAL_AFTER_ATTEMPTS}): {pending['question']}")
            lines.append("Key points of a good answer (NEVER show these to the student while the question is "
                         "open): " + " | ".join(pending["key_points"]))
        else:
            lines.append("OPEN QUESTION: none.")
        return "\n".join(lines)


# ---------- lecturer inbox (shared, not per student) ----------
def read_inbox(path: Path = config.INBOX_PATH) -> list:
    if Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return []


def add_to_inbox(entry: dict, path: Path = config.INBOX_PATH) -> None:
    items = read_inbox(path)
    items.append(entry)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
