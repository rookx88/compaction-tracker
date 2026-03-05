# compaction-tracker

> **OpenClaw compaction cost identifier — self-evolving via Nous**

## The Problem

OpenClaw silently compacts session context when it gets too long. This process costs tokens — but the cost is invisible. It blends into normal usage stats with no label, no breakdown. You can't tell if you're spending 5% or 30% of your bill on compaction overhead.

[Frugal-IQ](https://clawhub.com) tells you which model is most cost-efficient. It can't tell you that a third of your cost is compaction tax that no model switch will fix.

## The Approach

This project uses **Nous** — a meta-agent evolution framework — to discover the correct methodology for measuring compaction cost. The skill starts with a naive estimate (input spike delta) and improves generation by generation as Nous benchmarks it, identifies weaknesses, and proposes targeted mutations.

The answer is not known in advance. Nous has to figure it out.

## How Compaction Events Look in Session Files

OpenClaw session files live at `~/.openclaw/agents/main/sessions/*.jsonl` — one JSON object per line:

```json
// Compaction event — fires when context is summarized
{"type":"compaction","id":"de531023","timestamp":"2026-02-26T04:22:25.955Z","tokensBefore":110121,"summary":"..."}

// Regular assistant message — has usage/cost data
{"type":"message","message":{"role":"assistant","usage":{"input":5432,"output":847,"cacheRead":98210,"totalTokens":104489,"cost":{"total":0.078106}}}}

// memoryFlush — fires just before compaction as a user message
{"type":"message","message":{"role":"user","content":[{"text":"Pre-compaction memory flush. Store durable memories now..."}]}}
```

The compaction event itself has **no usage field**. The cost of summarization is invisible.

## Directory Structure

```
compaction-tracker/
├── skills/
│   └── compaction-cost/
│       ├── SKILL.md        # The evolving skill prompt
│       ├── TESTS.md        # Eval criteria and known weaknesses
│       ├── HISTORY.md      # Generation-by-generation mutation log
│       └── config.json     # Model config + version counter
├── benchmarks/
│   └── skills/
│       └── compaction-cost/
│           ├── task1/      # Basic detection
│           ├── task2/      # Cost estimation accuracy
│           └── task3/      # Zero-compaction edge case
├── src/
│   └── nous/
│       ├── skill_genome.py   # SkillGenome adapter (reads SKILL.md as prompt)
│       └── evolve_skills.py  # Evolution loop wired to OpenClaw skills
└── scripts/
    └── run_evolution.sh    # Shell wrapper
```

## Quick Start

```bash
# Dry run — benchmark only, no mutations
./scripts/run_evolution.sh compaction-cost --dry-run

# Full evolution cycle (stub mode, no live API calls)
./scripts/run_evolution.sh compaction-cost

# Live evaluation (requires OpenClaw + Anthropic API wiring)
NOUS_LIVE=1 ./scripts/run_evolution.sh compaction-cost
```

## Wiring Live Evaluation

Implement three functions in `evolve_skills.py`:

- `run_skill_on_task()` — call OpenClaw sessions_spawn with the skill prompt + task input
- `score_output()` — send output + rubric to an LLM, parse 0.0–1.0 score
- `evolve_skill()` — call Claude with the evolution prompt, parse `<SKILL>` and `<HYPOTHESIS>` tags

Then set `NOUS_LIVE=1`.

## Adding Benchmark Tasks

1. Create `benchmarks/skills/compaction-cost/taskN/`
2. Add `task.json` with `description`, `input`, optional `groundTruth`
3. Add `rubric.md` with scoring criteria summing to 1.0

## The Evolution Story

| Gen | Method | Expected Error |
|-----|--------|---------------|
| 0 | Raw input spike (3-msg window) | ~25% |
| 2 | Exclude memoryFlush from pre-window | ~18% |
| 4 | Subtract cacheRead from post-compaction input | ~12% |
| 6 | Adaptive window size | ~7% |
| 8 | memoryFlush bracket method when available | ~4% |
| 10+ | Hybrid validated method | <3% |

HISTORY.md becomes a research artifact — an AI system discovering how to measure something that was never documented.

## Frugal-IQ Integration

Once error rate <5%, a thin adapter adds to Frugal-IQ's report:
- **Compaction overhead %** — fraction of spend on compaction tax
- **High-overhead sessions** — flagged when compaction >15% of session cost
- **True model cost** — scores adjusted to exclude compaction noise

## Related

- [Nous](https://github.com/nous-research/nous) — meta-agent evolution framework
- [Frugal-IQ](https://clawhub.com) — OpenClaw model cost optimization skill
