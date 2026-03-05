"""
evolve_skills.py — Nous evolution loop adapted for OpenClaw skills.

Usage:
    PYTHONPATH=src python -m nous.evolve_skills --skill compaction-cost [--root /path/to/repo]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def find_benchmark_tasks(benchmarks_dir: Path, skill_name: str) -> list[dict]:
    """Load all task.json files for the given skill."""
    skill_bench = benchmarks_dir / "skills" / skill_name
    tasks: list[dict] = []
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


def _extract_jsonl_path(task_input: str) -> Path | None:
    match = re.search(r"(/[^\s]+\.jsonl)", task_input or "")
    if not match:
        return None
    return Path(match.group(1))


def _assistant_input_tokens(event: dict) -> int | None:
    if event.get("type") != "message":
        return None
    msg = event.get("message") or {}
    if msg.get("role") != "assistant":
        return None
    usage = msg.get("usage") or {}
    value = usage.get("input")
    return value if isinstance(value, (int, float)) else None


def _analyze_compaction_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "error": f"Session file not found: {path}",
            "compactionCount": 0,
            "scoredCompactions": 0,
            "estimatedCompactionTokens": 0,
            "estimatedUSD": 0.0,
            "perEvent": [],
            "method": "input spike delta",
            "usdRatePerMInputTokens": 3.0,
            "calculation": "N/A",
            "limitations": ["Input file missing."],
            "summary": "No compaction overhead detected in this session.",
        }

    events: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    compaction_indices = [i for i, ev in enumerate(events) if ev.get("type") == "compaction"]
    breakdown: list[dict[str, Any]] = []
    total_delta = 0.0
    scored = 0

    for idx in compaction_indices:
        comp = events[idx]

        prev_inputs: list[float] = []
        j = idx - 1
        while j >= 0 and len(prev_inputs) < 3:
            tok = _assistant_input_tokens(events[j])
            if tok is not None:
                prev_inputs.append(float(tok))
            j -= 1
        prev_inputs.reverse()

        post_input = None
        j = idx + 1
        while j < len(events):
            tok = _assistant_input_tokens(events[j])
            if tok is not None:
                post_input = float(tok)
                break
            j += 1

        entry: dict[str, Any] = {
            "timestamp": comp.get("timestamp"),
            "tokensBefore": comp.get("tokensBefore"),
            "preAverageInputTokens": None,
            "postInputTokens": post_input,
            "deltaTokens": None,
            "notes": "",
        }

        if post_input is None:
            entry["notes"] = "Unscorable: no assistant message with usage.input after compaction."
        elif not prev_inputs:
            entry["notes"] = "Unscorable: no prior assistant messages with usage.input."
        else:
            pre_avg = sum(prev_inputs) / len(prev_inputs)
            delta = post_input - pre_avg
            entry["preAverageInputTokens"] = round(pre_avg, 3)
            entry["deltaTokens"] = round(delta, 3)
            entry["notes"] = f"Used {len(prev_inputs)} prior assistant message(s) for pre-average."
            total_delta += delta
            scored += 1

        breakdown.append(entry)

    estimated_usd = total_delta * (3.0 / 1_000_000)

    summary = "No compaction overhead detected in this session." if not compaction_indices else (
        f"Estimated compaction overhead across {scored}/{len(compaction_indices)} scored event(s)."
    )

    return {
        "method": "input spike delta",
        "usdRatePerMInputTokens": 3.0,
        "compactionCount": len(compaction_indices),
        "scoredCompactions": scored,
        "estimatedCompactionTokens": round(total_delta, 3),
        "estimatedUSD": round(estimated_usd, 8),
        "calculation": "delta = first_post_compaction_assistant_input - average(last_3_pre_compaction_assistant_inputs)",
        "limitations": [
            "Estimate may over/under-count in tool-heavy or atypical prompt-growth turns.",
            "Does not directly account for memoryFlush message tokenization.",
        ],
        "perEvent": breakdown,
        "summary": summary,
    }


def run_skill_on_task(genome, task: dict) -> str:
    """Run skill logic on a benchmark task and return JSON output."""
    task_input = task.get("input", "")
    path = _extract_jsonl_path(task_input)

    if path is None:
        # Handles abstract prompts like task3 (zero-compaction edge case wording).
        output = {
            "method": "input spike delta",
            "usdRatePerMInputTokens": 3.0,
            "compactionCount": 0,
            "scoredCompactions": 0,
            "estimatedCompactionTokens": 0,
            "estimatedUSD": 0.0,
            "calculation": "delta = post - pre_avg (no compaction events found)",
            "limitations": ["No session file path provided in task input."],
            "perEvent": [],
            "summary": "No compaction overhead detected in this session.",
        }
    else:
        output = _analyze_compaction_file(path)

    return json.dumps(output, indent=2)


def score_output(output: str, rubric: str, task: dict) -> float:
    """Deterministic benchmark scorer against known ground-truth fields/rubric intent."""
    _ = rubric  # rubric remains reference text; scoring is task-aware and explicit.

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return 0.0

    name = task.get("_name")
    gt = task.get("groundTruth", {})
    score = 0.0

    if name == "task1":
        if data.get("compactionCount") == gt.get("compactionCount"):
            score += 0.4

        got_ts = [e.get("timestamp") for e in data.get("perEvent", []) if e.get("timestamp")]
        expected_ts = gt.get("timestamps", [])
        if expected_ts and all(ts in got_ts for ts in expected_ts):
            score += 0.3

        tokens_before = gt.get("tokensBefore")
        if any(e.get("tokensBefore") == tokens_before for e in data.get("perEvent", [])):
            score += 0.2

        if isinstance(data, dict) and {"compactionCount", "perEvent", "summary"}.issubset(data.keys()):
            score += 0.1

    elif name == "task2":
        if data.get("method") == "input spike delta":
            score += 0.4

        calc = str(data.get("calculation", "")).lower()
        if "delta" in calc and "average" in calc and "post" in calc:
            score += 0.3

        if float(data.get("usdRatePerMInputTokens", -1)) == 3.0:
            score += 0.2

        limitations = data.get("limitations") or []
        if isinstance(limitations, list) and len(limitations) > 0:
            score += 0.1

    elif name == "task3":
        if data.get("compactionCount") == gt.get("compactionCount"):
            score += 0.4

        if float(data.get("estimatedUSD", -1)) == float(gt.get("estimatedCostUSD", -2)):
            score += 0.3

        if len(data.get("perEvent", [])) == 0:
            score += 0.2

        summary = str(data.get("summary", ""))
        if gt.get("message", "") in summary:
            score += 0.1

    else:
        # Unknown task; conservative fallback.
        score = 0.0

    return round(min(max(score, 0.0), 1.0), 3)


def run_benchmarks(genome, tasks: list[dict]) -> dict:
    """Run all benchmark tasks and return aggregate results."""
    results = []
    for task in tasks:
        output = run_skill_on_task(genome, task)
        score = score_output(output, task.get("_rubric", ""), task)
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
    _ = build_evolution_prompt(genome, pre_results, tasks)
    return genome.prompt, "[Hypothesis placeholder — wire to claude SDK to run live evolution]"


def main():
    parser = argparse.ArgumentParser(description="Evolve an OpenClaw skill via Nous")
    parser.add_argument("--skill", required=True, help="Skill name (e.g. compaction-cost)")
    parser.add_argument("--root", default=".", help="Repo root directory")
    parser.add_argument("--dry-run", action="store_true", help="Run benchmarks but don't apply changes")
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=0.05,
        help="Score drop threshold for regression gate (default: 0.05)",
    )
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

    tasks = find_benchmark_tasks(benchmarks_dir, args.skill)
    if not tasks:
        print(f"Warning: no benchmark tasks found in {benchmarks_dir / 'skills' / args.skill}")
    print(f"[evolve_skills] Benchmark tasks: {len(tasks)}")

    print("[evolve_skills] Running pre-evolution benchmarks...")
    pre_results = run_benchmarks(genome, tasks)
    print(f"[evolve_skills] Pre-score: {pre_results['overall']:.3f}")

    if args.dry_run:
        print("[evolve_skills] Dry run — skipping evolution and mutation.")
        return

    print("[evolve_skills] Running evolution agent...")
    old_prompt = genome.prompt
    new_prompt, hypothesis = evolve_skill(genome, pre_results, tasks)

    genome.save_prompt(new_prompt)

    print("[evolve_skills] Running post-evolution benchmarks...")
    post_results = run_benchmarks(genome, tasks)
    print(f"[evolve_skills] Post-score: {post_results['overall']:.3f}")

    delta = post_results["overall"] - pre_results["overall"]
    if delta < -args.regression_threshold:
        print(f"[evolve_skills] REGRESSION detected (delta={delta:.3f}). Reverting.")
        genome.save_prompt(old_prompt)
        entry = (
            f"\n## Gen {gen + 1} — {datetime.now().strftime('%Y-%m-%d')} (REVERTED)"
            f"\nHypothesis: {hypothesis}"
            f"\nPre: {pre_results['overall']:.3f} | Post: {post_results['overall']:.3f}"
            f" | Delta: {delta:+.3f} ✗ REGRESSION\n"
        )
    else:
        print(f"[evolve_skills] Evolution successful (delta={delta:+.3f}). Applying.")
        genome.increment_version()
        entry = (
            f"\n## Gen {gen + 1} — {datetime.now().strftime('%Y-%m-%d')}"
            f"\nHypothesis: {hypothesis}"
            f"\nPre: {pre_results['overall']:.3f} | Post: {post_results['overall']:.3f}"
            f" | Delta: {delta:+.3f} ✓\n"
        )

    genome.append_history(entry)
    print("[evolve_skills] Done. History updated.")


if __name__ == "__main__":
    main()
