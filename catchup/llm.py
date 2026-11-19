"""Thin OpenRouter client (OpenAI-compatible chat completions with tool calling)."""
from __future__ import annotations

import json
import time

import requests


class LLMError(RuntimeError):
    pass


class OpenRouterLLM:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str, temperature: float = 0.3,
                 max_tokens: int = 1200, timeout: int = 90):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def chat(self, messages: list, tools: list | None = None) -> dict:
        """Returns {"content", "tool_calls": [{"id","name","arguments"}], "raw_message", "usage"}."""
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "CatchUp prototype",
        }

        response = None
        for attempt in range(3):
            try:
                response = requests.post(self.URL, headers=headers, json=body, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise LLMError(f"Network error calling OpenRouter: {exc}") from exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break

        if response is None or response.status_code != 200:
            status = getattr(response, "status_code", "?")
            text = getattr(response, "text", "")[:400]
            raise LLMError(f"OpenRouter returned {status}: {text}")

        data = response.json()
        if "error" in data:
            raise LLMError(f"OpenRouter error: {json.dumps(data['error'])[:400]}")
        if not data.get("choices"):
            raise LLMError("OpenRouter returned no choices.")

        message = data["choices"][0]["message"]
        raw_calls = message.get("tool_calls") or []
        calls = []
        for call in raw_calls:
            raw_args = call["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
                if not isinstance(args, dict):
                    args = {"_invalid_arguments": raw_args}
            except json.JSONDecodeError:
                args = {"_invalid_arguments": raw_args}
            calls.append({"id": call["id"], "name": call["function"]["name"], "arguments": args})

        raw_message = {"role": "assistant", "content": message.get("content") or ""}
        if raw_calls:
            raw_message["tool_calls"] = raw_calls
        return {
            "content": message.get("content") or "",
            "tool_calls": calls,
            "raw_message": raw_message,
            "usage": data.get("usage") or {},
        }
