#!/bin/bash
# Run one Nous evolution cycle for an OpenClaw skill
# Usage: ./scripts/run_evolution.sh [skill-name] [extra args]
SKILL=${1:-compaction-cost}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHONPATH="$ROOT/src" python -m nous.evolve_skills --skill "$SKILL" --root "$ROOT" "${@:2}"
