"""Turn the raw public datasets into ``Sample`` rows.

Design rules (they matter for validity):
* Dev/test is assigned per *group* (a user scenario, a BIPIA context, ...) so that near-duplicates of
  one template never straddle the split.
* Anything we derive ourselves (benign controls, attack insertion) is labelled as such in ``meta``.
* Long inputs are cut to the gateway's own ``MAX_PROMPT_CHARS`` -- the API rejects larger prompts,
  so they would never reach a detector in production.
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.config import MAX_PROMPT_CHARS

from .schema import Sample, assign_split

csv.field_size_limit(2**31 - 1)

NEUTRAL_FILLERS = (
    "Great product, arrived on time and works as described.",
    "Decent quality for the price. Would buy again.",
    "Not what I expected, but customer support was helpful.",
)


def _cut(text: str | None, limit: int) -> tuple[str | None, bool]:
    if text is None or len(text) <= limit:
        return text, False
    return text[:limit], True


def _mk(id_: str, group: str, label: int, prompt: str, context: str | None, kind: str, category: str,
        source: str, limit: int, **meta: Any) -> Sample:
    prompt, cut_p = _cut(prompt, limit)
    context, cut_c = _cut(context, limit)
    if cut_p or cut_c:
        meta["truncated"] = True
    return Sample(id_, label, prompt or "", context, kind, category, source, assign_split(group), meta)


# ---------------------------------------------------------------------------- InjecAgent
def _unwrap(tool_response: str) -> str:
    """InjecAgent stores some responses as JSON-quoted strings; give the detector the plain text."""
    try:
        v = json.loads(tool_response)
    except ValueError:
        return tool_response
    return v if isinstance(v, str) else tool_response


def load_injecagent(root: Path, limit: int = MAX_PROMPT_CHARS) -> Iterator[Sample]:
    """Indirect injection: attacker text inside a tool response the user's task fetched."""
    data = root / "data"
    scenarios = [json.loads(line) for line in (data / "user_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    group_of = {(s["User Tool"], s["User Instruction"]): f"injecagent-scenario-{i}" for i, s in enumerate(scenarios)}

    for variant in ("base", "enhanced"):
        for domain in ("dh", "ds"):
            cases = json.loads((data / f"test_cases_{domain}_{variant}.json").read_text(encoding="utf-8"))
            for i, c in enumerate(cases):
                group = group_of[(c["User Tool"], c["User Instruction"])]
                yield _mk(
                    f"injecagent:{variant}:{domain}:{i}", group, 1, c["User Instruction"], _unwrap(c["Tool Response"]),
                    "indirect_injection", c["Attack Type"], "injecagent", limit,
                    variant=variant, domain=domain, attacker_tools=c["Attacker Tools"],
                )
    # Benign controls: the same scenarios with the placeholder filled by a neutral review (derived by us).
    for i, s in enumerate(scenarios):
        for j, filler in enumerate(NEUTRAL_FILLERS):
            body = _unwrap(s["Tool Response Template"]).replace("<Attacker Instruction>", filler)
            yield _mk(
                f"injecagent:control:{i}:{j}", f"injecagent-scenario-{i}", 0, s["User Instruction"], body,
                "benign", "injecagent_control", "injecagent", limit, derived="placeholder filled with neutral text",
            )


# ---------------------------------------------------------------------------- BIPIA
def _insert(text: str, attack: str, where: str, rng: random.Random) -> str:
    lines = text.split("\n")
    if where == "start":
        return attack + "\n" + text
    if where == "end":
        return text + "\n" + attack
    k = rng.randint(1, max(1, len(lines) - 1))
    return "\n".join([*lines[:k], attack, *lines[k:]])


def load_bipia(root: Path, seed: int = 2023, limit: int = MAX_PROMPT_CHARS) -> Iterator[Sample]:
    """Each context yields one clean sample and one with a seeded, randomly placed attack.

    This is our own insertion, not BIPIA's builder. email/table take the *text* attacks, code takes
    the *code* attacks. The ``abstract`` and ``qa`` tasks need licensed corpora and are skipped.
    """
    bench = root / "benchmark"
    text_attacks = json.loads((bench / "text_attack_test.json").read_text(encoding="utf-8"))
    code_attacks = json.loads((bench / "code_attack_test.json").read_text(encoding="utf-8"))
    for task, attacks in (("email", text_attacks), ("table", text_attacks), ("code", code_attacks)):
        rng = random.Random(f"{seed}:{task}")
        rows = [json.loads(line) for line in (bench / task / "test.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        flat = [(cat, a) for cat, items in sorted(attacks.items()) for a in items]
        for i, r in enumerate(rows):
            group = f"bipia-{task}-{i}"
            question = r.get("question") or "Answer using the provided content."
            ctx = str(r["context"])
            yield _mk(f"bipia:{task}:{i}:clean", group, 0, question, ctx, "benign", "bipia_clean_context", "bipia", limit, task=task)
            cat, attack = flat[rng.randrange(len(flat))]
            where = rng.choice(("start", "middle", "end"))
            yield _mk(
                f"bipia:{task}:{i}:attack", group, 1, question, _insert(ctx, attack, where, rng),
                "indirect_injection", cat, "bipia", limit, task=task, position=where,
            )


# ---------------------------------------------------------------------------- jailbreak_llms
_WS = re.compile(r"\s+")


def _norm(t: str) -> str:
    return _WS.sub(" ", t).strip().lower()


def load_jailbreak_llms(root: Path, max_regular: int = 2000, seed: int = 2023, limit: int = MAX_PROMPT_CHARS) -> Iterator[Sample]:
    """In-the-wild jailbreaks (attacks) vs. regular prompts (benign), de-duplicated.

    Caveat for the paper: the 'regular' label comes from the dataset's own pipeline and is noisy
    (it includes junk strings and may contain unflagged jailbreaks), so FPR here is an upper bound.
    """
    prompts = root / "data" / "prompts"
    seen: set[str] = set()

    def rows(name: str) -> list[dict[str, str]]:
        out = []
        with (prompts / name).open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                key = _norm(r.get("prompt", ""))
                if key and key not in seen:
                    seen.add(key)
                    out.append(r)
        return out

    jb = rows("jailbreak_prompts_2023_12_25.csv")
    for i, r in enumerate(jb):
        yield _mk(f"jailbreak_llms:jb:{i}", f"jbllms-jb-{i}", 1, r["prompt"], None, "jailbreak",
                  r.get("community") or "uncategorised", "jailbreak_llms", limit, platform=r.get("platform"), source_name=r.get("source"))
    regular = rows("regular_prompts_2023_12_25.csv")
    rng = random.Random(f"{seed}:regular")
    rng.shuffle(regular)
    for i, r in enumerate(regular[:max_regular]):
        yield _mk(f"jailbreak_llms:regular:{i}", f"jbllms-reg-{i}", 0, r["prompt"], None, "benign", "wild_regular",
                  "jailbreak_llms", limit, platform=r.get("platform"))
