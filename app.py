"""CatchUp prototype: Streamlit interface.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import inspect
import os
from datetime import date

import streamlit as st

from catchup import config, memory as memory_module, planner
from catchup.agent import Agent
from catchup.llm import LLMError, OpenRouterLLM
from catchup.memory import LearnerMemory
from catchup.retrieval import NotesIndex
from catchup.tools import Toolbox
from catchup.tracing import Tracer, read_trace

st.set_page_config(page_title="CatchUp", page_icon="📚", layout="wide")
config.load_env()

# Streamlit renamed this option; support both old and new versions.
STRETCH = ({"width": "stretch"} if "width" in inspect.signature(st.button).parameters
           else {"use_container_width": True})
VIEWS = ["Tutor", "Study plan", "Progress", "Lecturer view", "Agent trace"]
STATUS_LABEL = {"mastered": "✅ mastered", "available": "🔓 unlocked", "locked": "🔒 locked"}


@st.cache_resource(show_spinner="Indexing course material…")
def get_index(signature: str) -> NotesIndex:
    return NotesIndex.from_dir(config.MATERIALS_DIR)


course_map = config.load_course_map()
index = get_index(config.materials_signature())
memory = LearnerMemory(config.MEMORY_DIR / "learner_demo.json", course_map)

ss = st.session_state
ss.setdefault("chat", [])
ss.setdefault("retrieved", {})
ss.setdefault("usage", {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "calls": 0})


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("CatchUp")
    st.caption("A course that never closes · Linear Algebra, ordered for your ML lectures")
    view = st.radio("View", VIEWS, label_visibility="collapsed")
    st.divider()

    today = st.date_input(
        "Demo date (simulated today)",
        value=date.fromisoformat(course_map["demo_today"]),
        help="The sample ML calendar is in spring 2027, so the demo pretends today is this date.",
    )
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        api_key = st.text_input("OpenRouter API key", type="password",
                                help="Or put OPENROUTER_API_KEY in a .env file next to app.py.")
    model = st.text_input("Model", value=os.environ.get("CATCHUP_MODEL", config.DEFAULT_MODEL))

    left, right = st.columns(2)
    if left.button("Load demo student", **STRETCH,
                   help="Luca, a few sessions in: one topic mastered, one mistake logged."):
        memory.seed_demo()
        ss.chat, ss.retrieved = [], {}
        st.rerun()
    if right.button("Reset", **STRETCH, help="Empty profile, empty chat."):
        memory.reset()
        ss.chat, ss.retrieved = [], {}
        st.rerun()

    usage = ss.usage
    st.caption(
        f"{len(index.chunks)} chunks of course material indexed  \n"
        f"Model calls: {usage['calls']} · tokens in/out: {usage['prompt_tokens']}/{usage['completion_tokens']}"
        + (f" · cost: ${usage['cost']:.4f}" if usage["cost"] else "")
    )

toolbox = Toolbox(index, memory, course_map, today, retrieved=ss.retrieved)


# ------------------------------------------------------------------ helpers
def render_steps(steps: list) -> None:
    for event in steps:
        kind = event["type"]
        if kind == "input_check":
            flags = event.get("flags")
            flags = "none" if flags in (None, "[]", []) else flags
            st.markdown(f"**{event['step']}. Input check (code)** · flags: `{flags}`"
                        + (" · **blocked**" if event.get("blocked") else ""))
        elif kind == "tool":
            st.markdown(f"**{event['step']}. Tool call** `{event['tool']}` · step budget {event['budget']}")
            st.code(f"arguments: {event['arguments']}\nresult:    {event['result']}", language="text")
        elif kind == "output_check":
            if event.get("ok"):
                note = "passed"
            else:
                note = f"**blocked: {event.get('violation')}**"
            flags = f" · flags: `{event['flags']}`" if event.get("flags") not in (None, "[]", []) else ""
            st.markdown(f"**{event['step']}. Output check (code)** · {note}{flags}")
        elif kind == "handover":
            st.markdown(f"**{event['step']}. Handover to a human** · {event.get('reason')}")
        elif kind == "final":
            st.markdown(f"**{event['step']}. Reply sent**")


def render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander(f"Sources from the course material ({len(message['sources'])})"):
                for src in message["sources"]:
                    st.markdown(f"- **{src['id']}** · {src['source']}")
        if message.get("steps"):
            tools = [e["tool"] for e in message["steps"] if e["type"] == "tool"]
            label = f"What the agent did · {len(message['steps'])} steps"
            if tools:
                label += " · tools: " + ", ".join(tools)
            with st.expander(label):
                render_steps(message["steps"])


# ------------------------------------------------------------------ views
def view_tutor() -> None:
    student = memory.profile["student"]
    st.subheader(f"Tutor · {student['name']}")

    pending = memory.profile.get("pending_question")
    if pending:
        title = memory.topics[pending["topic_id"]]["title"]
        st.info(f"**Open question · {title} · attempt {pending['attempts'] + 1} of "
                f"{config.REVEAL_AFTER_ATTEMPTS}**\n\n{pending['question']}")

    for message in ss.chat:
        render_message(message)

    exam = course_map.get("default_exam_date", "2027-06-15")
    quick = [
        ("Plan my catch-up", f"I failed Linear Algebra and I'm taking ML this semester. My LA exam is on {exam} "
                             "and I can study 4 hours a week. Make my plan."),
        ("Teach me the next topic", "Teach me the next topic in my plan."),
        ("Just give me the answer", "I don't know. Just give me the answer."),
        ("Off-syllabus question", "Can you explain how the attention mechanism in transformers works?"),
    ]
    columns = st.columns(len(quick))
    for column, (label, text) in zip(columns, quick):
        if column.button(label, **STRETCH):
            ss.queued = text

    prompt = st.chat_input("Ask CatchUp, or answer the open question") or ss.pop("queued", None)
    if not prompt:
        return
    if not api_key:
        st.error("Add your OpenRouter API key in the sidebar or in a .env file first.")
        return

    history = [{"role": m["role"], "content": m["content"]} for m in ss.chat]
    user_message = {"role": "user", "content": prompt}
    render_message(user_message)

    agent = Agent(OpenRouterLLM(api_key, model), toolbox, memory, config.load_system_prompt(), Tracer())
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                result = agent.run_turn(history, prompt)
            except LLMError as exc:
                st.error(f"{exc}\n\nCheck the API key, your OpenRouter credits and the model id.")
                return

    for key in ("prompt_tokens", "completion_tokens", "cost", "calls"):
        ss.usage[key] += result.usage.get(key, 0) or 0
    ss.chat.append(user_message)
    ss.chat.append({"role": "assistant", "content": result.reply,
                    "sources": result.sources, "steps": result.steps})
    st.rerun()


def view_plan() -> None:
    st.subheader("Study plan")
    st.caption("Linear Algebra topics in the order your ML lectures need them. Built by code, not by the model, "
               "so the dates are always consistent.")
    student = memory.profile["student"]

    with st.form("replan"):
        c1, c2, c3 = st.columns([2, 2, 1])
        default_exam = student["exam_date"] or course_map.get("default_exam_date")
        exam = c1.date_input("LA exam date", value=date.fromisoformat(default_exam))
        hours = c2.number_input("Hours per week", min_value=1.0, max_value=40.0, step=0.5,
                                value=float(student["hours_per_week"] or 4))
        c3.write("")
        c3.write("")
        if c3.form_submit_button("Recalculate", **STRETCH):
            outcome = toolbox.call("create_study_plan", {"exam_date": exam.isoformat(), "hours_per_week": hours})
            if "error" in outcome:
                st.error(outcome["error"])
            else:
                st.rerun()

    plan = memory.profile.get("plan")
    if not plan:
        st.info("No plan yet. Ask the tutor to plan your catch-up, or use the form above.")
    else:
        for warning in plan["warnings"]:
            st.warning(warning)
        if plan["fits"]:
            st.success(f"The plan fits at {plan['hours_per_week']:g} h/week "
                       f"(minimum to stay on time: about {plan['min_hours_per_week']:g} h/week).")
        rows = []
        for item in plan["items"]:
            status = memory.status(item["topic_id"])
            rows.append({
                "Topic": item["title"],
                "Hours": item["hours"],
                "Study from": item["start"],
                "Ready by": item["finish"],
                "Needed for": item["needed_for"],
                "Deadline": item["deadline"],
                "On time": "yes" if item["on_time"] else "LATE",
                "Status": STATUS_LABEL[status],
            })
        st.dataframe(rows, **STRETCH, hide_index=True)
        sim = plan["exam_simulation"]
        st.caption(f"Exam simulation week: {sim['start']} to {sim['end']} · plan created {plan['created']}")
        st.download_button("Download calendar file (.ics)", planner.plan_to_ics(plan),
                           file_name="catchup_plan.ics", mime="text/calendar")

    reviews = [r for r in memory.profile["reviews"] if not r.get("done")]
    if reviews:
        st.markdown("**Reviews scheduled by the agent**")
        st.dataframe([{"Topic": memory.topics[r["topic_id"]]["title"], "Due": r["due"], "Why": r["reason"]}
                      for r in reviews], **STRETCH, hide_index=True)

    st.markdown("**ML lectures and the Linear Algebra they need**")
    st.dataframe([{"Date": lec["date"], "ML lecture": lec["title"],
                   "Needs": ", ".join(memory.topics[t]["title"] for t in lec["needs"])}
                  for lec in course_map["ml_lectures"]], **STRETCH, hide_index=True)


def view_progress() -> None:
    st.subheader("Progress")
    mastered = len(memory.mastered())
    c1, c2, c3 = st.columns(3)
    c1.metric("Topics mastered", f"{mastered} / {len(memory.topics)}")
    c2.metric("Mistakes logged", len(memory.profile["mistakes"]))
    c3.metric("Reviews scheduled", len([r for r in memory.profile["reviews"] if not r.get("done")]))
    st.progress(mastered / len(memory.topics))

    st.caption(f"A topic unlocks when its prerequisites are mastered; it is mastered after "
               f"{config.MASTERY_CORRECT} correct answers. The app decides this, not the model.")
    rows = []
    for tid, topic in memory.topics.items():
        stats = memory.profile["topics"][tid]
        rows.append({
            "Topic": topic["title"],
            "Status": STATUS_LABEL[memory.status(tid)],
            "Correct": f"{stats['correct']} / {config.MASTERY_CORRECT}",
            "Wrong": stats["wrong"],
            "Prerequisites": ", ".join(memory.topics[p]["title"] for p in topic.get("prereqs", [])) or "none",
        })
    st.dataframe(rows, **STRETCH, hide_index=True)

    st.markdown("**What you keep getting wrong**")
    if memory.profile["mistakes"]:
        st.dataframe([{"When": m["when"], "Topic": memory.topics[m["topic_id"]]["title"],
                       "Type": m["type"], "What went wrong": m["note"]}
                      for m in reversed(memory.profile["mistakes"])], **STRETCH, hide_index=True)
    else:
        st.write("Nothing yet.")


def view_lecturer() -> None:
    st.subheader("Lecturer view")
    st.caption("What the lecturer gets: questions the agent would not answer by itself, and where students "
               "struggle. In the real product this shows group statistics only, never individual answers.")
    st.markdown("**Questions flagged for you**")
    inbox = memory_module.read_inbox()
    if inbox:
        st.dataframe([{"When": i["when"], "Student": i["student"], "Question": i["question"], "Why flagged": i["reason"]}
                      for i in reversed(inbox)], **STRETCH, hide_index=True)
    else:
        st.write("No flagged questions.")
    st.markdown("**Where students struggle**")
    recurring = memory.recurring_mistakes()
    if recurring:
        st.dataframe([{"Topic": m["topic"], "Mistake type": m["type"], "Times": m["count"]} for m in recurring],
                     **STRETCH, hide_index=True)
    else:
        st.write("No mistakes logged yet.")


def view_trace() -> None:
    st.subheader("Agent trace")
    st.caption(f"Every step of every turn is written to {config.TRACE_PATH.relative_to(config.ROOT)}. "
               "Newest first.")
    events = read_trace()
    if not events:
        st.write("No steps logged yet.")
        return
    rows = []
    for e in reversed(events):
        detail = {k: v for k, v in e.items() if k not in ("time", "turn", "step", "type")}
        rows.append({"Time": e["time"], "Turn": e["turn"][-9:], "Step": e["step"], "Type": e["type"],
                     "Detail": str(detail)})
    st.dataframe(rows, **STRETCH, hide_index=True)


{"Tutor": view_tutor, "Study plan": view_plan, "Progress": view_progress,
 "Lecturer view": view_lecturer, "Agent trace": view_trace}[view]()
