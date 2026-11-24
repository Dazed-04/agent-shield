from collections import Counter

from evaluation.inhouse import load_inhouse
from evaluation.schema import check_unique_ids


def test_inhouse_set_is_valid_balanced_and_split():
    rows = check_unique_ids(load_inhouse())
    assert 100 <= len(rows) <= 200
    labels = Counter(r.label for r in rows)
    assert abs(labels[1] - labels[0]) <= 15
    for lab in (0, 1):
        assert Counter(r.split for r in rows if r.label == lab).keys() == {"dev", "test"}
    assert all(r.meta["authored"] for r in rows)


def test_inhouse_ids_are_stable():
    assert [r.id for r in load_inhouse()][:2] == ["inhouse_v1:001", "inhouse_v1:002"]


def test_hard_negative_categories_present():
    cats = {r.category for r in load_inhouse() if r.label == 0}
    assert {"benign_ignore", "benign_roleplay", "benign_trigger_word", "security_question", "security_education"} <= cats
