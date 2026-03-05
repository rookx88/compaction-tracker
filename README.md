# compaction-tracker

Compaction cost tracker + Nous-powered skill evolution for OpenClaw.

## What this project is

`compaction-tracker` is a small research-and-ops repo for one specific blind spot in OpenClaw session analytics: **compaction overhead**.

It contains:
- A first-pass OpenClaw skill (`skills/compaction-cost`) that estimates compaction token overhead from session JSONL logs.
- A benchmark suite (`benchmarks/skills/compaction-cost`) to score quality and edge-case handling.
- A lightweight Nous-style evolution loop (`src/nous/evolve_skills.py`) that can mutate and improve the skill prompt over generations.

## Core insight

Today, compaction cost is often operationally invisible: you see overall token usage, but not a direct "this much was spent due to compaction summarization" metric.

This project treats the skill prompt as an evolvable genome and uses benchmark feedback to improve how the metric is estimated.

**Key idea:** Nous is used to discover and refine the best practical measurement methodology (starting with the input spike delta heuristic), not just to produce a static one-off script.

## How compaction events look in OpenClaw JSONL

Session files are JSONL (one JSON object per line).

Compaction event example:

```json
{"type":"compaction","id":"de531023","parentId":"4da00f8a","timestamp":"2026-02-26T04:22:25.955Z","summary":"...","firstKeptEntryId":"c9b53147","tokensBefore":110121,"details":{...}}
```

Regular assistant message example:

```json
{"type":"message","id":"...","message":{"role":"assistant","usage":{"input":5432,"output":847,"cacheRead":98210,"cacheWrite":0,"totalTokens":104489,"cost":{"input":0.016296,"output":0.012705,"cacheRead":0.049105,"cacheWrite":0.0,"total":0.078106}},...}}
```

A memory flush signal appears immediately before compaction as a user message containing:
- `"Pre-compaction memory flush"`

## Directory structure

```text
compaction-tracker/
├── skills/
│   └── compaction-cost/
│       ├── SKILL.md        # Skill prompt (the thing that evolves)
│       ├── TESTS.md        # Expected behavior and acceptance criteria
│       ├── HISTORY.md      # Generation-by-generation mutation log
│       └── config.json     # Skill runtime/version metadata
├── benchmarks/
│   └── skills/
│       └── compaction-cost/
│           ├── task1/
│           │   ├── task.json
│           │   └── rubric.md
│           ├── task2/
│           │   ├── task.json
│           │   └── rubric.md
│           └── task3/
│               ├── task.json
│               └── rubric.md
├── src/
│   ├── __init__.py
│   └── nous/
│       ├── __init__.py
│       ├── skill_genome.py # Adapter for loading/saving skill artifacts
│       └── evolve_skills.py# Evolution + benchmark loop scaffold
├── scripts/
│   └── run_evolution.sh    # Convenience wrapper for one generation
├── .gitignore
└── README.md
```

## Quick start

### 1) Verify Python import path assumptions

The evolution script expects `src/` to exist and imports via:
- `from nous.skill_genome import SkillGenome`

### 2) Run benchmark loop in dry-run mode

```bash
cd /home/ocsam/projects/compaction-tracker
python -m nous.evolve_skills --skill compaction-cost --root . --dry-run
```

This will:
- Load tasks from `benchmarks/skills/compaction-cost/*/task.json`
- Run stubbed task execution/scoring
- Print a pre-score without mutating prompt/history

### 3) Manually inspect benchmark task definitions

```bash
cat benchmarks/skills/compaction-cost/task1/task.json
cat benchmarks/skills/compaction-cost/task1/rubric.md
```

## Running an evolution cycle

One full generation (mutation + post-check):

```bash
cd /home/ocsam/projects/compaction-tracker
./scripts/run_evolution.sh compaction-cost
```

Equivalent direct command:

```bash
python -m nous.evolve_skills --skill compaction-cost --root .
```

Optional regression threshold override:

```bash
python -m nous.evolve_skills --skill compaction-cost --root . --regression-threshold 0.03
```

## How to add new benchmark tasks

1. Create a new task directory:

```bash
mkdir -p benchmarks/skills/compaction-cost/task4
```

2. Add `task.json` with:
- `description`
- `input`
- `groundTruth` (or expected constraints)

3. Add `rubric.md` with weighted scoring criteria (sum to 1.0 preferred).

4. Re-run dry-run benchmark:

```bash
python -m nous.evolve_skills --skill compaction-cost --root . --dry-run
```

The loader auto-discovers all child directories under:
- `benchmarks/skills/<skill-name>/`

## Evolution story (expected trajectory)

- **Gen 1 (naive):** baseline heuristic works on simple logs, misses edge nuance.
- **Gen 2–N (improving):** prompt mutations tighten event selection, improve handling of missing context, reduce false positives.
- **Later generations:** better robustness on back-to-back compactions, tool-heavy sessions, sparse pre-history, and unscorable segments.

The current scaffold uses stub execution/judging (`run_skill_on_task`, `score_output`). Once wired to real runner + judge, this repo becomes a practical closed-loop prompt evolution system.

## Integration with Frugal-IQ

Frugal-IQ focuses on model efficiency and spend optimization. `compaction-tracker` complements it by exposing hidden overhead from context compaction behavior.

Together:
- Frugal-IQ answers: *Which model/setup is cheaper for my workload?*
- Compaction tracker answers: *How much hidden cost is caused by compaction itself?*

This lets you optimize both model choice and context-management strategy.

## Nous reference

- Upstream project: https://github.com/nous-research/nous
- Local source on this machine: `/home/ocsam/.openclaw/workspace/nous/nous-main/`

## Current limitations

- Evolution engine currently contains placeholders for:
  - live task execution via OpenClaw sessions orchestration
  - LLM-as-judge scoring
- Regression revert path is scaffold-level and should be hardened when live mutation is enabled.

## License / usage

Internal prototype scaffold for rapid iteration on skill quality and cost observability.
