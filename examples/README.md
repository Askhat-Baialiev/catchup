# Example interactions

This folder holds the "example interactions" deliverable.

Generate it with the real model (needs your API key in `.env`):

```
python scripts/run_examples.py
```

It writes `example_interactions.md` with six short conversations: a plan, a lesson with a wrong answer,
the agent refusing to hand over an answer, an off-syllabus question, a locked topic, an honest "this plan
does not fit" and a prompt-injection attempt. Read the output once before submitting it.
