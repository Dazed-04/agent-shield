"""One evaluation sample, JSONL (de)serialisation and the deterministic dev/test split."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

KINDS = ("jailbreak", "direct_injection", "indirect_injection", "benign")
SPLITS = ("dev", "test")


@dataclass(frozen=True)
class Sample:
    """A labelled input as the gateway would see it.

    ``prompt`` is the trusted user channel (may be empty for purely indirect attacks);
    ``context`` is untrusted content (tool output, document, RAG chunk) fed back to the model.
    ``label`` is 1 for an attack and 0 for benign.
    """

    id: str
    label: int
    prompt: str
    context: str | None
    kind: str
    category: str
    source: str
    split: str
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.label not in (0, 1):
            raise ValueError(f"{self.id}: label must be 0 or 1")
        if self.kind not in KINDS:
            raise ValueError(f"{self.id}: unknown kind {self.kind!r}")
        if self.split not in SPLITS:
            raise ValueError(f"{self.id}: unknown split {self.split!r}")
        if (self.kind == "benign") != (self.label == 0):
            raise ValueError(f"{self.id}: kind 'benign' must be exactly the label-0 samples")
        if not self.prompt and not self.context:
            raise ValueError(f"{self.id}: empty sample")


def assign_split(sample_id: str, dev_fraction: float = 0.5, seed: str = "agent-shield-eval-v1") -> str:
    """Stable split from the id alone: independent of order, dataset size and Python's hash seed.

    The same id always lands in the same split, so thresholds tuned on ``dev`` can never see ``test``.
    """
    h = hashlib.sha256(f"{seed}:{sample_id}".encode()).digest()
    return "dev" if int.from_bytes(h[:8], "big") / 2**64 < dev_fraction else "test"


def write_jsonl(path: str | Path, samples: Iterable[Sample]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: str | Path) -> Iterator[Sample]:
    with Path(path).open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield Sample(**json.loads(line))
            except (TypeError, ValueError) as e:
                raise ValueError(f"{path}:{line_no}: {e}") from e


def check_unique_ids(samples: Iterable[Sample]) -> list[Sample]:
    out, seen = [], set()
    for s in samples:
        if s.id in seen:
            raise ValueError(f"duplicate sample id {s.id!r}")
        seen.add(s.id)
        out.append(s)
    return out
