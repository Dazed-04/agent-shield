import pytest

from evaluation.schema import Sample, assign_split, check_unique_ids, read_jsonl, write_jsonl


def mk(i="a", label=1, kind="jailbreak", split="dev", prompt="p", context=None):
    return Sample(i, label, prompt, context, kind, "cat", "src", split)


def test_roundtrip(tmp_path):
    rows = [mk("1"), mk("2", 0, "benign", "test", "hi", "ctx")]
    p = tmp_path / "s.jsonl"
    assert write_jsonl(p, rows) == 2
    assert list(read_jsonl(p)) == rows


@pytest.mark.parametrize(
    "kw",
    [dict(label=2), dict(kind="nope"), dict(split="val"), dict(label=0, kind="jailbreak"), dict(label=1, kind="benign"), dict(prompt="")],
)
def test_invalid_samples_are_rejected(kw):
    with pytest.raises(ValueError):
        mk(**kw)


def test_split_is_stable_and_roughly_balanced():
    ids = [f"id-{i}" for i in range(4000)]
    a = [assign_split(i) for i in ids]
    assert a == [assign_split(i) for i in reversed(ids)][::-1]  # order-independent
    assert 0.45 < a.count("dev") / len(a) < 0.55
    assert assign_split("x", seed="other") in ("dev", "test")


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        check_unique_ids([mk("1"), mk("1")])


def test_bad_line_reports_location(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "x"}\n')
    with pytest.raises(ValueError, match="bad.jsonl:1"):
        list(read_jsonl(p))
