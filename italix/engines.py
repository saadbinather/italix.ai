"""Local MLX inference and explicitly enabled cloud provider clients."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Protocol

import httpx

from italix.pr_summary import SYSTEM_PROMPT
from italix.change_triage import COMPACT_PROMPT


@dataclass(frozen=True)
class Generation:
    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    metadata: dict | None = None


class Engine(Protocol):
    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, adapter_path: str | None = None
    ) -> Generation: ...


class DeterministicPRSummaryEngine:
    """Evidence-only PR summarization; never loads or invokes an ML model."""

    model_name = "pr-summary-deterministic-v1"

    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float,
        adapter_path: str | None = None,
    ) -> Generation:
        from italix.hybrid_pr_summary import (
            deterministic_summary,
            extract_diff_facts,
            validate_hybrid,
        )

        if adapter_path is not None:
            raise ValueError("deterministic PR summarizer does not accept adapters")
        source = "\n".join(
            message.get("content", "") for message in messages if message.get("role") == "user"
        )
        marker = source.find("diff --git ")
        diff = source[marker:] if marker >= 0 else source
        facts = extract_diff_facts(diff)
        text = deterministic_summary(facts)
        validation = validate_hybrid(text, facts, diff)
        abstained = bool(facts.abstention_reasons)
        return Generation(
            text=text,
            model=self.model_name,
            prompt_tokens=None,
            completion_tokens=None,
            metadata={
                "validation": validation,
                "abstained": abstained,
                "abstention_reasons": list(facts.abstention_reasons),
                "files": list(facts.files),
                "adapter_used": False,
                "trained_model": False,
            },
        )


def cached_qwen_path() -> Path:
    root = Path.home() / ".cache/huggingface/hub/models--mlx-community--Qwen2.5-1.5B-Instruct-4bit/snapshots"
    candidates = sorted(root.glob("*/model.safetensors"))
    if not candidates:
        raise FileNotFoundError("cached Qwen model not found; automatic downloads are disabled")
    return candidates[-1].parent


class LocalMLXEngine:
    model_name = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(model_path) if model_path else cached_qwen_path()
        self._model = None
        self._tokenizer = None
        self._loaded_adapter: str | None = None

    def _load(self, adapter_path: str | None):
        if self._model is None or adapter_path != self._loaded_adapter:
            from mlx_lm import load

            self._model, self._tokenizer = load(
                str(self.model_path), adapter_path=adapter_path
            )
            self._loaded_adapter = adapter_path

    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, adapter_path: str | None = None
    ) -> Generation:
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        self._load(adapter_path)
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        prompt_ids = self._tokenizer.encode(prompt)
        text = generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=make_sampler(temp=temperature),
            verbose=False,
        ).strip()
        return Generation(
            text=text,
            model=self.model_name,
            prompt_tokens=len(prompt_ids),
            completion_tokens=len(self._tokenizer.encode(text, add_special_tokens=False)),
        )


class GeminiEngine:
    model_name = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = client or httpx.Client(timeout=60)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, adapter_path: str | None = None
    ) -> Generation:
        if not self.api_key:
            raise RuntimeError("Gemini is not configured")
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
            if message["role"] != "system"
        ]
        body: dict = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            response = self.client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent",
                headers={"x-goog-api-key": self.api_key}, json=body,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Gemini request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Gemini returned HTTP {exc.response.status_code}") from exc
        payload = response.json()
        text = "".join(
            part.get("text", "")
            for part in payload["candidates"][0]["content"].get("parts", [])
        ).strip()
        usage = payload.get("usageMetadata", {})
        return Generation(
            text=text,
            model=self.model_name,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
        )


class GroqEngine:
    model_name = "llama-3.1-8b-instant"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.client = client or httpx.Client(timeout=60)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, adapter_path: str | None = None
    ) -> Generation:
        if not self.api_key:
            raise RuntimeError("Groq is not configured")
        try:
            response = self.client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model_name, "messages": messages,
                      "max_tokens": max_tokens, "temperature": temperature},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Groq request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Groq returned HTTP {exc.response.status_code}") from exc
        payload = response.json()
        usage = payload.get("usage", {})
        return Generation(
            text=payload["choices"][0]["message"]["content"].strip(),
            model=self.model_name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


def prepare_messages(workload: str, messages: list[dict]) -> list[dict]:
    if workload == "pr_summary" and not any(m["role"] == "system" for m in messages):
        return [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    if workload == "change_triage" and not any(m["role"] == "system" for m in messages):
        return [{"role": "system", "content": COMPACT_PROMPT}, *messages]
    return messages
