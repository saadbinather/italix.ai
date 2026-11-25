import json

import pytest


def test_masked_risk_loss_and_gradients():
    mx = pytest.importorskip("mlx.core")
    from mlx_lm.tuner.trainer import default_loss
    from italix.weighted_lora import risk_loss, weighted_cross_entropy

    # Targets at positions 2–5 are supervised; positions 3–4 form the risk value.
    batch = mx.array([[0, 2, 1, 2, 1, 2, 0, 0]])
    lengths = mx.array([[2, 5]])
    spans = mx.array([[3, 5]])
    logits = mx.broadcast_to(mx.array([2.0, 0.0, 0.0]), (1, 7, 3))
    stock = lambda scores: default_loss(lambda _: scores, batch, lengths)[0]
    weighted = lambda scores, weight: weighted_cross_entropy(
        lambda _: scores, batch, lengths, spans, weight=weight
    )[0]

    reference, ordinary_grad = mx.value_and_grad(stock)(logits)
    same, unit_grad = mx.value_and_grad(lambda scores: weighted(scores, 1))(logits)
    assert mx.allclose(reference, same, atol=1e-6).item()
    assert mx.allclose(ordinary_grad, unit_grad, atol=1e-6).item()
    assert mx.allclose(risk_loss(lambda _: logits, batch, lengths, weight=5)[0], reference).item()
    loss, grad = mx.value_and_grad(lambda scores: weighted(scores, 5))(logits)
    assert mx.allclose(loss, reference).item()  # All active positions have equal CE here.
    assert mx.all(grad[0, [0, 5, 6]] == 0).item()
    assert mx.allclose(grad[0, [2, 3]], ordinary_grad[0, [2, 3]] * (5 * 4 / 12)).item()
    assert mx.allclose(grad[0, [1, 4]], ordinary_grad[0, [1, 4]] * (4 / 12)).item()


def test_multitoken_risk_span_uses_assistant_offsets():
    pytest.importorskip("mlx.core")
    from italix.weighted_lora import risk_token_span

    class CharacterTokenizer:
        def apply_chat_template(self, messages, *, tools, tokenize, add_generation_prompt=False):
            assert not tokenize
            return "".join(f"<{m['role']}>{m['content']}" for m in messages) + (
                "<assistant>" if add_generation_prompt else "</end>"
            )

        def __call__(self, text, *, add_special_tokens, return_offsets_mapping):
            assert not add_special_tokens and return_offsets_mapping
            return {"input_ids": list(map(ord, text)),
                    "offset_mapping": [(i, i + 1) for i in range(len(text))]}

    tokenizer = CharacterTokenizer()
    messages = [{"role": "user", "content": '{"risk":"decoy"}'},
                {"role": "assistant", "content": json.dumps({"owner": "fixture", "risk": "very high"})}]
    prefix = tokenizer.apply_chat_template(messages[:-1], tools=None, tokenize=False, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(messages, tools=None, tokenize=False)
    start, end = risk_token_span(tokenizer, {"messages": messages}, list(map(ord, full)), len(prefix))
    assert full[start:end] == "very high"
    assert start >= len(prefix) and end - start > 1
