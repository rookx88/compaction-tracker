"""
evolve_skills.py — Nous evolution loop adapted for OpenClaw skills.

Usage:
    python -m nous.evolve_skills --skill compaction-cost [--root /path/to/repo]
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def find_benchmark_tasks(benchmarks_dir: Path, skill_name: str) -> list[dict]:
    """Load all task.json files for the given skill."""
    skill_bench = benchmarks_dir / "skills" / skill_name
    tasks = []
    if not skill_bench.exists():
        return tasks
    for task_dir in sorted(skill_bench.iterdir()):
        task_file = task_dir / "task.json"
        rubric_file = task_dir / "rubric.md"
        if task_file.exists():
            task = json.loads(task_file.read_text())
            task["_rubric"] = rubric_file.read_text() if rubric_file.exists() else ""
            task["_name"] = task_dir.name
            tasks.append(task)
    return tasks


def run_skill_on_task(genome, task: dict) -> str:
    """
    Placeholder: run the skill against a task input.
    In production, this would call the OpenClaw sessions_spawn API
    or the Nous orchestrator with the skill prompt + task input.
    Returns the skill's output as a string.
    """
    # Stub output for initial scaffolding
    return f"[Skill output for task '{task.get('description', task.get('_name', 'unknown'))}' — integrate with sessions_spawn to run live]"


def score_output(output: str, rubric: str) -> float:
    """
    Placeholder: LLM-as-judge scoring.
    In production, sends output + rubric to a model for scoring 0.0–1.0.
    """
    # Stub: return 0.5 baseline until live scoring is wired
    return 0.5


def run_benchmarks(genome, tasks: list[dict]) -> dict:
    """Run all benchmark tasks and return aggregate results."""
    results = []
    for task in tasks:
        output = run_skill_on_task(genome, task)
        score = score_output(output, task.get("_rubric", ""))
        results.append({
            "task": task.get("_name"),
            "score": score,
            "output": output,
        })
    total = sum(r["score"] for r in results) / len(results) if results else 0.0
    return {"tasks": results, "overall": total}


def build_evolution_prompt(genome, pre_results: dict, tasks: list[dict]) -> str:
    """Build the prompt that asks the meta-agent to evolve the skill."""
    return f"""You are evolving an OpenClaw skill to improve its benchmark scores.

## Skill: {genome.name}

### Current SKILL.md (the prompt being evolved):
{genome.prompt}

### TESTS.md (what good looks like):
{genome.tests}

### HISTORY.md (what has been tried before):
{genome.history}

### Current benchmark results (overall: {pre_results['overall']:.2f}):
{json.dumps(pre_results['tasks'], indent=2)}

## Your task:
1. Identify ONE specific weakness in the current skill prompt
2. Propose a single targeted change to SKILL.md that addresses it
3. Write the complete updated SKILL.md
4. Explain your hypothesis: why will this change improve the score?

Rules:
- Only ONE change per generation
- The change must be testable and specific
- Do not rewrite the entire prompt — make a surgical edit
- Output ONLY the new SKILL.md content between <SKILL> tags, then your hypothesis between <HYPOTHESIS> tags.
"""


def evolve_skill(genome, pre_results: dict, tasks: list[dict]) -> tuple[str, str]:
    """
    Placeholder: call the meta-agent to propose a skill mutation.
    In production, sends the evolution prompt to claude and parses the response.
    Returns (new_prompt, hypothesis).
    """
    prompt = build_evolution_prompt(genome, pre_results, tasks)
    # Stub: return current prompt unchanged with placeholder hypothesis
    return genome.prompt, "[Hypothesis placeholder — wire to claude SDK to run live evolution]"


def main():
    parser = argparse.ArgumentParser(description="Evolve an OpenClaw skill via Nous")
    parser.add_argument("--skill", required=True, help="Skill name (e.g. compaction-cost)")
    parser.add_argument("--root", default=".", help="Repo root directory")
    parser.add_argument("--dry-run", action="store_true", help="Run benchmarks but don't apply changes")
    parser.add_argument("--regression-threshold", type=float, default=0.05,
                        help="Score drop threshold for regression gate (default: 0.05)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    skill_dir = root / "skills" / args.skill
    benchmarks_dir = root / "benchmarks"

    if not skill_dir.exists():
        print(f"Error: skill directory not found: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    # Import SkillGenome (works whether run as module or script)
    sys.path.insert(0, str(root / "src"))
    from nous.skill_genome import SkillGenome

    genome = SkillGenome.load(skill_dir)
    gen = genome.config.get("version", 0)
    print(f"[evolve_skills] Skill: {genome.name} | Gen: {gen}")

    # Load benchmark tasks
    tasks = find_benchmark_tasks(benchmarks_dir, args.skill)
    if not tasks:
        print(f"Warning: no benchmark tasks found in {benchmarks_dir / 'skills' / args.skill}")
    print(f"[evolve_skills] Benchmark tasks: {len(tasks)}")

    # Pre-evolution benchmark
    print("[evolve_skills] Running pre-evolution benchmarks...")
    pre_results = run_benchmarks(genome, tasks)
    print(f"[evolve_skills] Pre-score: {pre_results['overall']:.3f}")

    if args.dry_run:
        print("[evolve_skills] Dry run — skipping evolution and mutation.")
        return

    # Evolve
    print("[evolve_skills] Running evolution agent...")
    new_prompt, hypothesis = evolve_skill(genome, pre_results, tasks)

    # Apply mutation
    genome.save_prompt(new_prompt)

    # Post-evolution benchmark
    print("[evolve_skills] Running post-evolution benchmarks...")
    post_results = run_benchmarks(genome, tasks)
    print(f"[evolve_skills] Post-score: {post_results['overall']:.3f}")

    # Regression gate
    delta = post_results["overall"] - pre_results["overall"]
    if delta < -args.regression_threshold:
        print(f"[evolve_skills] REGRESSION detected (delta={delta:.3f}). Reverting.")
        genome.save_prompt(genome.prompt)  # revert
        entry = f"\n## Gen {gen + 1} — {datetime.now().strftime('%Y-%m-%d')} (REVERTED)\nHypothesis: {hypothesis}\nPre: {pre_results['overall']:.3f} | Post: {post_results['overall']:.3f} | Delta: {delta:+.3f} ✗ REGRESSION\n"
    else:
        print(f"[evolve_skills] Evolution successful (delta={delta:+.3f}). Applying.")
        genome.increment_version()
        entry = f"\n## Gen {gen + 1} — {datetime.now().strftime('%Y-%m-%d')}\nHypothesis: {hypothesis}\nPre: {pre_results['overall']:.3f} | Post: {post_results['overall']:.3f} | Delta: {delta:+.3f} ✓\n"

    genome.append_history(entry)
    print(f"[evolve_skills] Done. History updated.")


if __name__ == "__main__":
    main()
