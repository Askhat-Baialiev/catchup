"""The cross-course planner: Linear Algebra ordered for what ML needs next.

Deterministic code, not the LLM. The model decides *when* to plan; this module
decides *what* the plan is, so the dates are always consistent and checkable.

Idea: every LA topic gets a deadline.
  - If an ML lecture needs it, the deadline is the day before that lecture.
  - Prerequisites inherit the earliest deadline of anything that depends on them.
  - Everything else is due one week before the LA exam (last week = exam simulation).
Topics are then studied in deadline order, at the student's hours per week.
If the plan does not fit, we say so instead of pretending.
"""
from __future__ import annotations

import math
from datetime import date, timedelta


def topo_order(topics: list) -> list:
    """Topic ids so that prerequisites always come first."""
    by_id = {t["id"]: t for t in topics}
    order, seen = [], set()

    def visit(tid: str) -> None:
        if tid in seen:
            return
        seen.add(tid)
        for pre in by_id[tid].get("prereqs", []):
            visit(pre)
        order.append(tid)

    for topic in topics:
        visit(topic["id"])
    return order


def topic_deadlines(course_map: dict, exam_date: date) -> dict:
    """tid -> (deadline date, reason string)."""
    topics = course_map["topics"]
    by_id = {t["id"]: t for t in topics}
    order = topo_order(topics)
    exam_deadline = exam_date - timedelta(days=7)

    deadlines = {}
    for lecture in course_map.get("ml_lectures", []):
        due = date.fromisoformat(lecture["date"]) - timedelta(days=1)
        if due > exam_deadline:
            continue
        reason = f"ML: {lecture['title']} ({lecture['date']})"
        for tid in lecture.get("needs", []):
            if tid in by_id and (tid not in deadlines or due < deadlines[tid][0]):
                deadlines[tid] = (due, reason)

    # prerequisites inherit the earliest deadline of their dependants
    for tid in reversed(order):
        if tid not in deadlines:
            continue
        for pre in by_id[tid].get("prereqs", []):
            if pre not in deadlines or deadlines[tid][0] < deadlines[pre][0]:
                deadlines[pre] = deadlines[tid]

    for tid in order:
        deadlines.setdefault(tid, (exam_deadline, "LA exam"))
    return deadlines


def build_plan(course_map: dict, mastered: set, today: date, exam_date: date,
               hours_per_week: float) -> dict:
    topics = course_map["topics"]
    by_id = {t["id"]: t for t in topics}
    order = topo_order(topics)
    deadlines = topic_deadlines(course_map, exam_date)

    todo = [tid for tid in order if tid not in mastered]
    todo.sort(key=lambda tid: (deadlines[tid][0], order.index(tid)))

    items, cumulative, needed_rate = [], 0.0, 0.0
    for tid in todo:
        hours = float(by_id[tid].get("hours", 2))
        start = today + timedelta(days=math.floor(cumulative / hours_per_week * 7))
        cumulative += hours
        finish = today + timedelta(days=math.ceil(cumulative / hours_per_week * 7))
        due, reason = deadlines[tid]
        weeks_left = max((due - today).days, 1) / 7
        needed_rate = max(needed_rate, cumulative / weeks_left)
        items.append({
            "topic_id": tid,
            "title": by_id[tid]["title"],
            "hours": hours,
            "start": start.isoformat(),
            "finish": finish.isoformat(),
            "deadline": due.isoformat(),
            "needed_for": reason,
            "on_time": finish <= due,
        })

    min_rate = math.ceil(needed_rate * 2) / 2  # round up to the next half hour
    warnings = []
    late = [item for item in items if not item["on_time"]]
    if late:
        first = late[0]
        warnings.append(
            f"At {hours_per_week:g} h/week this plan does not fit: '{first['title']}' would be ready on "
            f"{first['finish']}, after it is needed for {first['needed_for']} (deadline {first['deadline']}). "
            f"{len(late)} topic(s) are late in total. To be on time you need about {min_rate:g} h/week, "
            f"or you could move the LA exam to a later session."
        )

    return {
        "created": today.isoformat(),
        "exam_date": exam_date.isoformat(),
        "hours_per_week": hours_per_week,
        "items": items,
        "exam_simulation": {
            "start": (exam_date - timedelta(days=7)).isoformat(),
            "end": exam_date.isoformat(),
        },
        "min_hours_per_week": min_rate,
        "fits": not late,
        "warnings": warnings,
    }


def plan_to_ics(plan: dict) -> str:
    """Calendar file the student can import into Google Calendar or any other."""

    def day(iso: str, plus: int = 0) -> str:
        return (date.fromisoformat(iso) + timedelta(days=plus)).strftime("%Y%m%d")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CatchUp//Prototype//EN"]
    for index, item in enumerate(plan.get("items", [])):
        lines += [
            "BEGIN:VEVENT",
            f"UID:catchup-{index}-{item['topic_id']}@catchup.local",
            f"DTSTAMP:{day(plan['created'])}T000000Z",
            f"DTSTART;VALUE=DATE:{day(item['start'])}",
            f"DTEND;VALUE=DATE:{day(item['finish'], 1)}",
            f"SUMMARY:CatchUp LA: {item['title']} ({item['hours']:g} h)",
            f"DESCRIPTION:Needed for {item['needed_for']}. Deadline {item['deadline']}.",
            "END:VEVENT",
        ]
    sim = plan.get("exam_simulation")
    if sim:
        lines += [
            "BEGIN:VEVENT",
            "UID:catchup-exam-simulation@catchup.local",
            f"DTSTAMP:{day(plan['created'])}T000000Z",
            f"DTSTART;VALUE=DATE:{day(sim['start'])}",
            f"DTEND;VALUE=DATE:{day(sim['end'], 1)}",
            "SUMMARY:CatchUp LA: exam simulation week",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
