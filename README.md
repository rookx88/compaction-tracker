# compaction-tracker

Compaction cost tracker + Nous-style self-evolution for OpenClaw skills.

## What this project is

`compaction-tracker` targets a blind spot: **compaction overhead is not explicitly surfaced** in OpenClaw spend views.

This repo provides:
- A **compaction-cost skill spec** (`skills/compaction-cost`) that defines the estimation method.
- A **real analyzer implementation** (`src/compaction_tracker/core.py`) used by CLI and benchmarks.
- A **benchmark harness + evolution loop** (`src/nous/evolve_skills.py`) to track and improve behavior.

## Core insight

Compaction overhead can be estimated from an **input-token spike** pattern:

- For each `type="compaction"` event, find the first next assistant input tokens.
- Subtract the average input tokens of the 3 prior assistant turns.
- Sum deltas and convert using Claude Sonnet 4.6 input pricing ($3/MTok).

This turns hidden overhead into an explicit metric you can optimize.

## JSONL event shape (OpenClaw sessions)

Compaction event example:

```json
{"type":"compaction","id":"de531023","timestamp":"2026-02-26T04:22:25.955Z","tokensBefore":110121}
```

Assistant message usage example:

```json
{"type":"message","message":{"role":"assistant","usage":{"input":5432}}}
```

A pre-compaction marker may appear as user content:
- `"Pre-compaction memory flush"`

## Project structure

```text
compaction-tracker/
├── skills/compaction-cost/          # Prompt, tests, history, config
├── benchmarks/
│   ├── fixtures/                    # Versioned sample JSONL logs
│   └── skills/compaction-cost/      # taskN/task.json + rubric.md
├── src/
│   ├── compaction_tracker/
│   │   ├── core.py                  # Analyzer logic
│   │   └── analyze.py               # CLI entrypoint
│   └── nous/
│       ├── skill_genome.py
│       └── evolve_skills.py         # Benchmark + evolution loop
├── scripts/run_evolution.sh
└── .github/workflows/ci.yml
```

## Quick start

### Run analyzer on a session

```bash
cd /home/ocsam/projects/compaction-tracker
PYTHONPATH=src python -m compaction_tracker.analyze --session /tmp/sample-compaction-session.jsonl --pretty
```

### Run benchmarks manually

```bash
PYTHONPATH=src python -m nous.evolve_skills --skill compaction-cost --root . --dry-run --judge deterministic
```

## Run an evolution cycle

```bash
./scripts/run_evolution.sh compaction-cost
```

Or directly:

```bash
PYTHONPATH=src python -m nous.evolve_skills --skill compaction-cost --root . --judge deterministic
```

`--judge` supports:
- `deterministic` (default, local deterministic scorer)
- `llm` (OpenAI rubric judge via `OPENAI_API_KEY`; `JUDGE_MODEL` optional, default `gpt-4o-mini`)

Example LLM-judge run:

```bash
OPENAI_API_KEY=... JUDGE_MODEL=gpt-4o-mini \
PYTHONPATH=src python -m nous.evolve_skills --skill compaction-cost --root . --dry-run --judge llm
```

If LLM judging fails for a task (missing key/network/parsing), the harness falls back to deterministic scoring for that task and records `judgeError` in results.

## Add new benchmark tasks

1. Create directory: `benchmarks/skills/compaction-cost/taskN/`
2. Add `task.json` and `rubric.md`
3. (Optional) add fixture file under `benchmarks/fixtures/*.jsonl`
4. Re-run dry-run benchmark command

## Evolution story (expected)

- **Gen 1:** baseline, obvious cases pass.
- **Gen 2+**: tighter behavior on malformed logs, sparse usage fields, back-to-back compactions.
- **Later generations:** improved robustness and better cost signal quality for real workloads.

## Frugal-IQ integration

Use analyzer output as an extra cost stream in Frugal-IQ:
- `estimatedCompactionTokens`
- `estimatedUSD`
- `compactionCount`

This complements model-routing savings by exposing hidden context-management overhead.

## Nous reference

- https://github.com/nous-research/nous
- Local source: `/home/ocsam/.openclaw/workspace/nous/nous-main/`


## Real prompt mutation (new)

Evolution now attempts to mutate `SKILL.md` via OpenAI Responses API.

Environment variables:
- `OPENAI_API_KEY` (required for live mutation)
- `EVOLVER_MODEL` (optional, default `gpt-4o`)

CLI flag:
- `--evolver-model <model>` overrides `EVOLVER_MODEL`

If mutation API/parsing fails, the run safely falls back to the current prompt and records a fallback hypothesis.


### Mutation acceptance gates

Evolution now has stricter acceptance controls:

- `--min-prompt-diff` (default `0.01`): rejects near no-op prompt mutations.
- `--require-improvement`: only accepts mutation when post-score is strictly greater than pre-score.
- Existing `--regression-threshold` still reverts if score drop exceeds threshold.

Example strict run:

```bash
OPENAI_API_KEY=... PYTHONPATH=src python -m nous.evolve_skills   --skill compaction-cost --root . --judge llm   --min-prompt-diff 0.02 --require-improvement
```
