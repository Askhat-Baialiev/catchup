# CatchUp: a course that never closes

Prototype for the Reply Student Tech Clash 2026, "AI on Campus", Level 2 (Path B, coding).

CatchUp is an AI agent for a student who failed or missed a course and cannot wait a year for it to run
again. This prototype covers one case: **Linear Algebra (LA) for a student who is following Machine
Learning (ML) at the same time.** The agent teaches LA from the lecturer's own material, in the order the
next ML lectures need it.

> The course material and the ML calendar in this repo are **sample data** so the app runs out of the box.
> Replace them with the real slides and syllabus before the demo (see "Use your real course material").

## Quick start

Needs Python 3.10 or newer.

```
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env   then paste your OpenRouter key into .env
streamlit run app.py
```

The app opens in the browser. In the sidebar press **Load demo student**, then use the four buttons above
the chat box.

Checks that need no API key:

```
python tests/test_offline.py    # 11 tests of the agent loop with a scripted fake model
```

## What the agent does (Level 2 requirements)

| Requirement | How the prototype meets it |
| --- | --- |
| **Work with real material** | `search_notes` searches the files in `materials/` (PDF slides, notes). Every explanation cites the chunk it came from, and the app shows the source (file and page or section). If the material does not cover a question, the agent says so and does not answer from its own knowledge. |
| **Do something, not just say something** | Five tools: it builds a study plan and a calendar file, registers quiz questions, grades answers, tracks repeated mistakes and schedules reviews, and flags questions for the lecturer. |
| **Know its limits** | It gives hints, not answers: the solution to an open question is locked until the student has tried twice. It refuses graded work, off-syllabus content and attempts to change its rules. These limits are checked in code, not only asked for in the prompt. |

## Architecture

```
 Streamlit UI (app.py)
        │
        ▼
 Orchestrator (catchup/agent.py)        ◄──►  LLM via OpenRouter (catchup/llm.py)
 plan → act → observe, step budget 6           + system prompt (prompts/system_prompt.md)
        │
        ├──►  Tools (catchup/tools.py)
        │        search_notes · create_study_plan · ask_quiz_question
        │        grade_answer · flag_for_lecturer
        ├──►  Memory (catchup/memory.py)        learner profile, JSON
        ├──►  Guardrails (catchup/guardrails.py) input and output checks in code
        └──►  Logs (catchup/tracing.py)          every step → logs/trace.jsonl
```

**Input.** One student message, plus the last 10 chat messages and a snapshot of the learner profile
(topic status, open question, plan, recurring mistakes, the ML calendar).

**Knowledge.** Only the files in `materials/`, cut into chunks and ranked with BM25 (pure Python, no
vector database). The course structure is in `data/course_map.json`: LA topics, their prerequisites, and
which ML lecture needs which topic on which date.

**Tools the agent can call.**

| Tool | What it does |
| --- | --- |
| `search_notes(query)` | Returns up to 3 chunks of course material with ids (S1, S2, …), or `found: false`. |
| `create_study_plan(exam_date, hours_per_week)` | Builds and saves the plan, returns warnings if it does not fit. A calendar file (.ics) can be downloaded from the Study plan page. |
| `ask_quiz_question(topic_id, question, key_points, source_ids)` | Registers one open question. Refused if the topic is locked or the question is not based on retrieved chunks. |
| `grade_answer(correct, mistake_type, note)` | Records an attempt. The app then updates mastery, unlocks topics, detects repeated mistakes and schedules a review. |
| `flag_for_lecturer(question, reason)` | Puts a question in the lecturer's inbox (Lecturer view). |

**Decisions the model makes.** Which tool to call and when, how to explain a topic, what question to ask,
whether an answer covers the key points, what hint to give.

**Decisions the code makes.** What the plan is, when a topic is mastered or unlocked, whether a draft
reply may be shown, when to stop and hand over.

**Output.** A short reply with citations, shown with its sources and the list of steps the agent took.

## Custom logic

**1. The cross-course planner (`catchup/planner.py`).** This is the core idea. Each LA topic gets a
deadline: the day before the first ML lecture that needs it. Prerequisites inherit the earliest deadline of
anything that depends on them. Topics no ML lecture needs are due one week before the LA exam; the last
week is exam simulation. Topics are studied in deadline order at the student's hours per week. If a topic
would be ready after its deadline, the plan says so and reports the hours per week that would fit.

**2. Mastery gates (`catchup/memory.py`).** A topic is mastered after 2 correct answers and unlocks when
its prerequisites are mastered. The model reports each graded answer, but only the code changes a
topic's status.

**3. Mistake tracking.** Every wrong answer is stored with a type (conceptual, computational, misread
question, incomplete). Two mistakes of the same type on one topic schedule a review two days later and
tell the model to explain the idea differently.

**4. Guardrails in code (`catchup/guardrails.py`).**

- Input: prompt-injection patterns are blocked before the model is called. "Just give me the answer"
  (English, Italian, Russian) while a question is open adds a hint-only rule to the turn.
- Output: citation ids the agent never retrieved are removed. A draft that reveals the key points of an
  open question is blocked. A long explanation with no citation and no tool call is blocked. A blocked
  draft gets one retry; if the retry fails too, a fixed safe reply is sent.
- Step budget: after 6 steps without an answer, the agent stops, flags the question for the lecturer and
  tells the student.

The solution-leak check is a word-overlap heuristic. It is simple on purpose and can be wrong in both
directions; the tests show the cases it handles.

## Models, libraries, frameworks

- **Model:** any OpenRouter model with tool calling. Default `anthropic/claude-haiku-5.5`; change
  `CATCHUP_MODEL` in `.env`. A typical turn is 2 to 4 model calls.
- **Libraries:** `streamlit` (interface), `requests` (OpenRouter API), `pypdf` (reading PDF slides).
- **No agent framework.** The loop is about 100 lines in `catchup/agent.py`.

## Use your real course material

1. Put the real LA slides and notes (text PDFs, `.md` or `.txt`) in `materials/linear_algebra/` and delete
   `LA_sample_notes.md`.
2. Edit `data/course_map.json`: the LA topics with hours and prerequisites, and the real ML lectures with
   dates and the LA topics each one needs. Set `demo_today` to the date the demo should pretend it is.
3. Restart the app.

## Example interactions

`python scripts/run_examples.py` runs six short conversations with the real model and writes them to
`examples/example_interactions.md`, including the ones where the agent holds its boundary.

## Demo walkthrough (about 2 minutes)

1. **Load demo student**, then **Plan my catch-up**. Open "What the agent did": one tool call. Open the
   Study plan page: LA topics are ordered by ML lecture, not by textbook chapter.
2. On the Study plan page set 3 hours a week and **Recalculate**: the plan honestly says it does not fit.
   Set it back to 4.
3. **Teach me the next topic**: an explanation with sources, then an open question.
4. **Just give me the answer**: the agent refuses and gives a hint.
5. Answer wrong, then right. Progress page: the mistake is logged, the counter moves.
6. **Off-syllabus question**: the agent does not answer and offers to flag it. Lecturer view shows it.

## What this prototype does not do

- No Google Classroom integration and no login: one local student profile.
- No diagnostic test at the start; use "Load demo student" to begin mid-way.
- One course pair (LA for ML), with the topic links written by hand in `course_map.json`. In the full
  design the links are generated from the syllabi.
- Lessons are generated on demand, not pre-approved by the lecturer; the lecturer view is read-only.
- Search is keyword-based (BM25), so material and queries should be in the same language.

## Repository layout

```
app.py                     Streamlit interface
catchup/agent.py           orchestrator loop
catchup/llm.py             OpenRouter client
catchup/tools.py           tool definitions and implementations
catchup/retrieval.py       loading and searching the course material
catchup/planner.py         cross-course study plan and calendar export
catchup/memory.py          learner profile and lecturer inbox
catchup/guardrails.py      input and output checks
catchup/tracing.py         step log
prompts/system_prompt.md   system prompt (versioned here)
data/course_map.json       topics, prerequisites, ML calendar (sample)
materials/                 course material (sample)
scripts/run_examples.py    generates the example interactions
tests/test_offline.py      offline tests
```
