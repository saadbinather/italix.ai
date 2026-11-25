from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import get_ident
from types import ModuleType, SimpleNamespace

import pytest

from italix.engines import LOCAL_MODELS, LocalMLXEngine


def snapshot(cache, key):
    spec = LOCAL_MODELS[key]
    path = cache / ("models--" + spec.repository.replace("/", "--")) / "snapshots" / spec.revision
    path.mkdir(parents=True)
    for name in ("config.json", "tokenizer_config.json", "tokenizer.json", "model.safetensors"):
        (path / name).touch()
    return path


def test_pinned_models_lazy_sequential_and_recoverable(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    first_path = snapshot(tmp_path, "qwen3-4b")
    calls = []

    def load(path, **kwargs):
        assert kwargs["tokenizer_config"] == {"trust_remote_code": False}
        assert kwargs["model_config"] == {"model_file": None}
        calls.append(("load", path, get_ident()))
        tokenizer = SimpleNamespace(
            bos_token=None,
            eos_token_id=151645,
            eos_token_ids={151643},
            apply_chat_template=lambda *args, **kwargs: Path(path).parent.parent.name,
            encode=lambda prompt, **kwargs: [len(prompt)],
        )
        return path, tokenizer

    def generate(model, tokenizer, *, prompt, **kwargs):
        calls.append(("generate", model, get_ident()))
        assert prompt == [len(Path(model).parent.parent.name)]
        assert tokenizer.eos_token_ids == {151643, 151645}
        yield SimpleNamespace(text="ok", prompt_tokens=1, generation_tokens=2,
                              generation_tps=12, peak_memory=2.5)

    mlx = ModuleType("mlx")
    core = ModuleType("mlx.core")
    core.clear_cache = lambda: calls.append(("unload", None, get_ident()))
    mlx.core = core
    lm = ModuleType("mlx_lm")
    lm.load = load
    lm.stream_generate = generate
    sampler = ModuleType("mlx_lm.sample_utils")
    sampler.make_sampler = lambda **kwargs: None
    for module in (mlx, core, lm, sampler):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    first = LocalMLXEngine(model_id="qwen3-4b")
    second = LocalMLXEngine(model_id="qwen-coder-7b")
    assert calls == []
    with pytest.raises(FileNotFoundError):
        second.generate([], 4, 0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: first.generate([], 4, 0), range(8)))
    assert [call[:2] for call in calls if call[0] == "load"] == [("load", str(first_path))]
    assert all(result.completion_tokens == 2 for result in results)
    with pytest.raises(ValueError, match="context"):
        first.generate([], 262144, 0)
    second_path = snapshot(tmp_path, "qwen-coder-7b")
    with pytest.raises(ValueError, match="adapters"):
        second.generate([], 4, 0, adapter_path="not-compatible")
    assert second.generate([], 4, 0).metadata["model_revision"] == second_path.name
    second.unload()
    assert len({thread_id for _, _, thread_id in calls}) == 1
    assert [action for action, _, _ in calls[-4:]] == ["unload", "load", "generate", "unload"]
