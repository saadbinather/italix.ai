"""Local MLX inference and explicitly enabled cloud provider clients."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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


@dataclass(frozen=True)
class LocalModelSpec:
    repository: str
    revision: str
    context_tokens: int

    def cached_path(self) -> Path:
        cache = Path(os.getenv("HF_HUB_CACHE") or
                     Path(os.getenv("HF_HOME") or Path.home() / ".cache/huggingface") / "hub")
        root = cache / ("models--" + self.repository.replace("/", "--")) / "snapshots"
        snapshot = root / self.revision
        required = ("config.json", "tokenizer_config.json", "tokenizer.json", "model.safetensors")
        if not all((snapshot / name).is_file() for name in required):
            raise FileNotFoundError(f"cached snapshot unavailable for {self.repository}@{self.revision}")
        return snapshot


LOCAL_MODELS = {
    "qwen-base": LocalModelSpec("mlx-community/Qwen2.5-1.5B-Instruct-4bit",
                               "8b403126fc14f14cfc99bb4cfa72ecbc129ea677", 32768),
    "qwen3-4b": LocalModelSpec("mlx-community/Qwen3-4B-Instruct-2507-4bit",
                              "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b", 262144),
    "qwen-coder-7b": LocalModelSpec("mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                                   "019cc73c45c770444708a6dd8690c66243cc5c80", 32768),
}

# MLX streams are thread-affine. All engine operations use the same worker.
_MLX_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="italix-mlx")


class LocalMLXEngine:
    model_name = LOCAL_MODELS["qwen-base"].repository
    _resident: LocalMLXEngine | None = None

    def __init__(self, model_path: str | Path | None = None, *, model_id: str | None = None):
        if model_path is not None and model_id is not None:
            raise ValueError("choose a pinned local model ID or an explicit local directory")
        self.model_path = Path(model_path) if model_path else None
        self._spec = LOCAL_MODELS.get(model_id or "qwen-base")
        if self._spec is None:
            raise ValueError("unknown local model ID")
        self._pinned = model_id is not None
        self.model_name = self._spec.repository
        self._model = None
        self._tokenizer = None
        self._loaded_adapter: str | None = None

    def unload(self) -> None:
        _MLX_WORKER.submit(self._unload).result()

    def _unload(self):
        if self._model is not None:
            import mlx.core as mx

            self._model = self._tokenizer = self._loaded_adapter = None
            LocalMLXEngine._resident = None
            mx.clear_cache()

    def _load(self, adapter_path: str | None):
        if adapter_path and self._spec != LOCAL_MODELS["qwen-base"]:
            raise ValueError("existing adapters require the Qwen 1.5B base")
        if self._model is None or adapter_path != self._loaded_adapter:
            model_path = self.model_path or (self._spec.cached_path() if self._pinned else cached_qwen_path())
            if not model_path.is_dir():
                raise FileNotFoundError("local model directory unavailable")
            from mlx_lm import load

            resident = LocalMLXEngine._resident
            if resident is not None:
                resident._unload()
            model, tokenizer = load(
                str(model_path), adapter_path=adapter_path,
                tokenizer_config={"trust_remote_code": False},
                model_config={"model_file": None},
            )
            # Some conversions declare a model EOS distinct from the native chat EOS.
            if tokenizer.eos_token_id is not None:
                tokenizer.eos_token_ids = {*tokenizer.eos_token_ids, tokenizer.eos_token_id}
            self._model, self._tokenizer = model, tokenizer
            self._loaded_adapter = adapter_path
            LocalMLXEngine._resident = self

    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, adapter_path: str | None = None
    ) -> Generation:
        return _MLX_WORKER.submit(self._generate, messages, max_tokens, temperature, adapter_path).result()

    def _generate(self, messages, max_tokens, temperature, adapter_path):
        self._load(adapter_path)

        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        bos = self._tokenizer.bos_token
        prompt_ids = self._tokenizer.encode(
            prompt, add_special_tokens=bos is None or not prompt.startswith(bos)
        )
        if len(prompt_ids) + max_tokens > self._spec.context_tokens:
            raise ValueError("prompt and generation exceed the local model context limit")
        chunks = []
        last = None
        for last in stream_generate(
            self._model, self._tokenizer, prompt=prompt_ids, max_tokens=max_tokens,
            sampler=make_sampler(temp=temperature),
        ):
            chunks.append(last.text)
        return Generation(
            text="".join(chunks).strip(),
            model=self.model_name,
            prompt_tokens=last.prompt_tokens if last else len(prompt_ids),
            completion_tokens=last.generation_tokens if last else 0,
            metadata={
                "model_revision": self._spec.revision if self._pinned else None,
                "generation_tps": last.generation_tps if last else None,
                "peak_memory_gb": last.peak_memory if last else None,
            },
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
