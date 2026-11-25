# Evaluation harness

Reproducible measurements of Agent Shield for the paper. Everything here calls the same code the
gateway runs (`app.shield.screen_inbound`, the LangGraph agent, the tool monitor), so what is measured
is what ships.

Run all commands from `backend/` inside the virtualenv, with `python -m evaluation <command>`.

## Quick start

```bash
python -m evaluation prepare                      # clone the public datasets at pinned commits
python -m evaluation build                        # -> data/processed/eval_set.jsonl
python -m evaluation scan --embeddings on         # score every sample with the production detectors
python -m evaluation calibrate results/<run>      # fit thresholds on the DEV split only
python -m evaluation report results/<run>         # report.json / report.md / report.csv / ablation.tex

python -m evaluation agent-scan --llm real --repeats 3   # end-to-end: needs a provider key in .env
python -m evaluation agent-report results/<run>
```

`results/` and `data/` are git-ignored. The admin dashboard (sidebar → *Open dashboard* → *Evaluation
runs*) reads `results/` (override with `EVAL_RESULTS_DIR`).

## Data

| Source | What it provides | Pinned commit | Licence |
|---|---|---|---|
| [InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent) | indirect injection inside tool responses | `f19c9f2c` | MIT |
| [BIPIA](https://github.com/microsoft/BIPIA) | indirect injection in email / table / code contexts, with clean paired contexts | `a004b69e` | MIT |
| [jailbreak_llms](https://github.com/verazuo/jailbreak_llms) | in-the-wild jailbreak prompts vs regular prompts | `4f4031bf` | MIT |
| in-house v1 | paraphrased / multilingual / encoded attacks and hard negatives | in repo | n/a |

Nothing is vendored. `prepare` fetches each repository at its exact SHA and refuses to continue if the
checked-out commit differs. Full SHAs and paper references are in `datasets.py`.

Things to state in the paper because they affect validity:

- **Derived controls.** InjecAgent ships attacks only. Its benign controls are built by replacing the
  attacker instruction with neutral filler, and are marked as derived in each sample's `meta`.
- **BIPIA pairing.** Attacks are inserted into the clean contexts at a seeded position, so every attack
  has a matching clean twin.
- **Label noise.** The "regular" prompts in jailbreak_llms were not individually verified as benign.
- **In-house set is not independent.** It was written while developing the detectors. Use it for
  development and error analysis; headline claims should come from the public sets.
- **Length cap.** Inputs are cut to the gateway's `MAX_PROMPT_CHARS`, because the API would reject longer ones.

## Integrity rules (enforced in code)

- **Dev/test split is deterministic** (hash of the sample's group id) and groups never straddle it.
  Thresholds are calibrated on dev only; the report quotes test numbers.
- **Error examples are dev-only**, so detectors are never tuned against held-out data.
- **Runtime-learned anchors are excluded** by default (`--use-learned` opts in), because they would
  contaminate a benchmark.
- **Every run records** commit SHA, whether the tree was dirty, detector mode (`semantic` or `heuristic`),
  thresholds, weights, Python/torch versions and the dataset manifest.
- **Intervals are always shown**: Wilson 95% for rates, bootstrap for AUC.

## Before you quote a number

1. Run with `--embeddings on` and confirm the report says `semantic` mode. `--embeddings off` measures the
   keyword fallback, which is far weaker, and the dashboard flags such runs.
2. Run from a clean commit (the run metadata shows `dirty` otherwise).
3. For `agent-scan --llm real`, use `--repeats` of at least 3: models are non-deterministic.
4. Never report runs from `--llm scripted-*`. Those use a scripted stand-in model to validate the harness
   and are labelled **SYNTHETIC** in every output.
5. Compare against the `no_shield` and `prompt_hardening` systems, not only against the full shield. A
   model's own refusals hide what the shield contributes, which is why the benchmark measures the
   attacker's goal being *executed*, and separately whether the model *attempted* it.

## End-to-end systems

| System | What differs |
|---|---|
| `no_shield` | plain tool loop, plain system prompt |
| `prompt_hardening` | plain loop plus the gateway's security prompt and spotlighting |
| `shield_full` | the real pipeline: inbound screen, tool-output quarantine, tool monitor, output scanner |
| `shield_no_quarantine` | full, minus scanning of tool output (ablation) |
| `shield_no_monitor` | full, minus tool-call policy and code screening (ablation) |

Shielded systems run once per role (`Domain Admins`, `Data Science` by default) because role policy
changes what is allowed. Success is judged by observable effects (file written, code executed, canary
secret in the answer), never by the model's wording.

## Known limits

- Scenarios are limited to the three gateway tools (read/write file, run Python) and three attacker goals.
- Public benchmarks target other agent stacks; the detector-level evaluation is comparable, the
  end-to-end one is specific to this gateway's tools.
- The semantic detector uses a small general-purpose embedding model and similarity to a fixed anchor
  list, so novel attacks far from every anchor can score low. The report's per-category table shows where.
