#!/bin/bash
# Run one evolution cycle for a skill
# Usage: ./scripts/run_evolution.sh [skill-name]
SKILL=${1:-compaction-cost}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python -m nous.evolve_skills --skill "$SKILL" --root "$ROOT" "${@:2}"
