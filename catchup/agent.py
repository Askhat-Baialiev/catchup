"""The orchestrator: plan -> act -> observe, with a step budget.

One student message = one turn. In each step the model either asks for tools
(our code runs them and feeds the results back) or writes a final answer.
The answer passes the output guardrails before the student sees it. If the
step budget runs out, the agent stops and hands the question to a human.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import config, guardrails
from .tools import TOOL_SPECS


@dataclass
class TurnResult:
    reply: str
    steps: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    handed_over: bool = False


class Agent:
    def __init__(self, llm, toolbox, memory, system_prompt: str, tracer,
                 step_budget: int = config.STEP_BUDGET):
        self.llm = llm
        self.toolbox = toolbox
        self.memory = memory
        self.system_prompt = system_prompt
        self.tracer = tracer
        self.step_budget = step_budget

    def _system_message(self) -> dict:
        state = self.memory.state_for_prompt(self.toolbox.today)
        return {"role": "system", "content": f"{self.system_prompt}\n\n## Live state (from memory)\n{state}"}

    def _finish(self, reply: str, usage: dict, handed_over: bool = False) -> TurnResult:
        cited = list(dict.fromkeys(re.findall(r"S\d+", " ".join(re.findall(r"\[[^\]]*\]", reply)))))
        sources = [{"id": s, "source": self.toolbox.retrieved[s]} for s in cited if s in self.toolbox.retrieved]
        self.tracer.log("final", reply=reply, handed_over=handed_over)
        return TurnResult(reply=reply, steps=list(self.tracer.events), sources=sources,
                          usage=usage, handed_over=handed_over)

    def run_turn(self, history: list, user_text: str) -> TurnResult:
        self.tracer.start_turn()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "calls": 0}

        # ---- input guardrails (code, before the model) ----
        verdict = guardrails.check_input(user_text, self.memory.profile.get("pending_question"))
        self.tracer.log("input_check", user=verdict.text, flags=verdict.flags, blocked=verdict.blocked)
        if verdict.blocked:
            return self._finish(verdict.reply, usage)

        user_content = verdict.text
        if verdict.directive:
            user_content += "\n\n" + verdict.directive
        messages = [self._system_message()]
        messages += [{"role": m["role"], "content": m["content"]} for m in history[-config.HISTORY_MESSAGES:]]
        messages.append({"role": "user", "content": user_content})

        tools_used = []
        retries_left = 1

        # ---- the loop ----
        for step in range(1, self.step_budget + 1):
            response = self.llm.chat(messages, tools=TOOL_SPECS)
            step_usage = response.get("usage") or {}
            usage["prompt_tokens"] += step_usage.get("prompt_tokens", 0) or 0
            usage["completion_tokens"] += step_usage.get("completion_tokens", 0) or 0
            usage["cost"] += step_usage.get("cost", 0) or 0
            usage["calls"] += 1

            if response["tool_calls"]:
                # act + observe
                messages.append(response["raw_message"])
                for call in response["tool_calls"]:
                    result = self.toolbox.call(call["name"], call["arguments"])
                    tools_used.append(call["name"])
                    self.tracer.log("tool", budget=f"{step}/{self.step_budget}", tool=call["name"],
                                    arguments=call["arguments"], result=result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                # the system message carries live state: refresh it after tools changed memory
                messages[0] = self._system_message()
                continue

            # ---- output guardrails (code, before the student) ----
            draft = response["content"]
            if not draft.strip():
                self.tracer.log("output_check", budget=f"{step}/{self.step_budget}", ok=False,
                                violation="empty_reply", flags=[])
                messages.append({"role": "user", "content": "[APP CHECK] Your reply was empty. "
                                                            "Write your reply to the student now."})
                continue
            check = guardrails.check_output(draft, self.memory.profile.get("pending_question"),
                                            self.toolbox.retrieved, tools_used)
            self.tracer.log("output_check", budget=f"{step}/{self.step_budget}", ok=check.ok,
                            violation=check.violation, flags=check.flags)
            if check.ok:
                return self._finish(check.text, usage)
            if retries_left > 0:
                retries_left -= 1
                messages.append({"role": "assistant", "content": draft})
                messages.append({"role": "user", "content": check.correction})
                continue
            return self._finish(check.fallback, usage)

        # ---- step budget exhausted: hand over to a human ----
        self.toolbox.call("flag_for_lecturer", {
            "question": user_text,
            "reason": "Agent could not finish within its step budget (automatic handover).",
        })
        self.tracer.log("handover", reason="step budget exhausted")
        reply = (
            "I couldn't work this out reliably within my step limit, so I've passed your question to the "
            "lecturer instead of guessing. In the meantime, we can continue with your plan."
        )
        return self._finish(reply, usage, handed_over=True)
