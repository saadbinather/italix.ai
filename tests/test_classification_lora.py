import math

import pytest


def test_classification_loss_masks_and_normalizes():
    mx = pytest.importorskip("mlx.core")
    from mlx_lm.tuner.trainer import default_loss
    from italix.weighted_lora import classification_components, classification_loss

    batch = mx.array([[0, 2, 1, 3, 0, 0]])
    lengths = mx.array([[2, 3]])
    decision = mx.array([[2, 1, 2, 1, 3]])
    logits = mx.array([[[0., 2., 1., 3.]] * 5])
    standard = lambda values: default_loss(lambda _: values, batch, lengths)[0]
    combined = lambda values, coefficient: classification_loss(
        lambda _: values, batch, lengths, decision, coefficient=coefficient)[0]
    loss, gradient = mx.value_and_grad(standard)(logits)
    zero, zero_gradient = mx.value_and_grad(lambda values: combined(values, 0))(logits)
    assert mx.allclose(loss, zero, atol=1e-6).item()
    assert mx.allclose(gradient, zero_gradient, atol=1e-6).item()
    sft, risk, count = classification_components(lambda _: logits, batch, lengths, decision)
    assert risk.item() == pytest.approx(math.log(sum(math.exp(x) for x in (1, 2, 3))) - 2)
    assert count.item() == 2
    assert combined(logits, 1).item() == pytest.approx(sft.item() + risk.item())
    added = mx.grad(lambda values: combined(values, 1))(logits) - gradient
    assert mx.allclose(added[0, [0, 2, 3, 4]], mx.zeros((4, 4))).item()
    assert abs(added[0, 1, 0].item()) < 1e-6
    assert added[0, 1, 1].item() < 0


def test_classification_updates_lora_with_frozen_base():
    mx = pytest.importorskip("mlx.core")
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_flatten
    from mlx_lm.tuner.lora import LoRALinear
    from italix.weighted_lora import classification_loss

    class ToyModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.projection = LoRALinear(4, 4, r=2)
            self.projection.linear.freeze()

        def __call__(self, inputs):
            return self.projection(mx.eye(4)[inputs])

    model = ToyModel()
    original = model.projection.linear.weight
    def loss(model):
        return classification_loss(model, mx.array([[0, 2, 1, 3, 0]]), mx.array([[2, 3]]),
                                   mx.array([[2, 1, 2, 1, 3]]), coefficient=1)[0]
    _, grads = nn.value_and_grad(model, loss)(model)
    assert {name for name, _ in tree_flatten(grads)} == {"projection.lora_a", "projection.lora_b"}
    assert mx.all(mx.isfinite(grads["projection"]["lora_b"])).item()
    assert mx.any(grads["projection"]["lora_b"] != 0).item()
    optim.Adam(learning_rate=0.001).update(model, grads)
    assert mx.any(model.projection.lora_b != 0).item()
    assert mx.array_equal(original, model.projection.linear.weight).item()


def test_classification_target_alignment_and_multitoken_rejection():
    pytest.importorskip("mlx.core")
    from mlx_lm.tuner.datasets import ChatDataset
    from italix.weighted_lora import prepare_spans

    class FixtureTokenizer:
        labels = {"low": 1, "medium": 2, "high": 3}
        def decode(self, ids):
            return "".join({value:key for key,value in self.labels.items()}.get(i, chr(i)) for i in ids)
        def apply_chat_template(self, messages, *, tools, tokenize=True, add_generation_prompt=False,
                                return_dict=False):
            rendered = "".join(f"<{m['role']}>{m['content']}" for m in messages)
            rendered += "<assistant>" if add_generation_prompt else "</end>"
            return self(rendered, add_special_tokens=False, return_offsets_mapping=True)["input_ids"] if tokenize else rendered
        def __call__(self, text, *, add_special_tokens, return_offsets_mapping):
            import re
            parts = list(re.finditer("|".join([*self.labels, "."]), text))
            return {"input_ids":[self.labels[p[0]] if p[0] in self.labels else ord(p[0]) for p in parts],
                    "offset_mapping":[p.span() for p in parts]}

    tokenizer = FixtureTokenizer()
    row = {"messages":[{"role":"user","content":'{"risk":"high"}'},
                       {"role":"assistant","content":'{"owner":"x","risk":"medium"}'}]}
    dataset=ChatDataset([row],tokenizer,mask_prompt=True)
    tokens, offset = dataset.process(row)
    (position,target,*ids), = prepare_spans(dataset,384,classification=True).values()
    assert position >= offset and target == 1 and list(ids) == [1,2,3] and tokens[position] == 2
    tokenizer.labels = {"medium":2,"high":3}
    with pytest.raises(ValueError, match="single-token"):
        prepare_spans(dataset,384,classification=True)
