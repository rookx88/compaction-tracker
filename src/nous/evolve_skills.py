"""
evolve_skills.py — Nous evolution loop adapted for OpenClaw skills.

Usage:
    PYTHONPATH=src python -m nous.evolve_skills --skill compaction-cost [--root /path/to/repo]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from compaction_tracker.core import analyze_session_file


def find_benchmark_tasks(benchmarks_dir: Path, skill_name: str) -> list[dict]:
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
    return Path(match.group(1)) if match else None


def run_skill_on_task(genome, task: dict) -> str:
    _ = genome
    task_input = task.get("input", "")
    path = _extract_jsonl_path(task_input)

    if path is None:
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
        output = analyze_session_file(path)

    return json.dumps(output, indent=2)


def score_output_deterministic(output: str, rubric: str, task: dict) -> float:
    _ = rubric
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
        if any(e.get("tokensBefore") == gt.get("tokensBefore") for e in data.get("perEvent", [])):
            score += 0.2
        if {"compactionCount", "perEvent", "summary"}.issubset(data.keys()):
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
        if gt.get("message", "") in str(data.get("summary", "")):
            score += 0.1

    elif name == "task4":
        if data.get("compactionCount") == gt.get("compactionCount"):
            score += 0.4
        if data.get("scoredCompactions") == gt.get("scoredCompactions"):
            score += 0.2
        if len(data.get("perEvent", [])) == gt.get("compactionCount"):
            score += 0.2
        if any(str(e.get("notes", "")).strip() for e in data.get("perEvent", [])):
            score += 0.2

    elif name == "task5":
        if data.get("compactionCount") == gt.get("compactionCount"):
            score += 0.5
        if float(data.get("estimatedUSD", -1)) == float(gt.get("estimatedCostUSD", -2)):
            score += 0.3
        if gt.get("message", "") in str(data.get("summary", "")):
            score += 0.2

    elif name == "task6":
        if data.get("compactionCount") == gt.get("compactionCount"):
            score += 0.4
        if data.get("scoredCompactions") == gt.get("scoredCompactions"):
            score += 0.2
        if any(e.get("deltaTokens") is not None for e in data.get("perEvent", [])):
            score += 0.2
        if len(data.get("limitations", [])) > 0:
            score += 0.2

    return round(min(max(score, 0.0), 1.0), 3)


def _openai_judge_score(output: str, rubric: str, task: dict) -> float:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.getenv("JUDGE_MODEL", "gpt-4o-mini")
    prompt = (
        "You are a strict benchmark judge. Score the candidate output against the rubric. "
        "Return ONLY valid JSON: {\"score\": <0.0-1.0 number>, \"reason\": \"short text\"}.\n\n"
        f"Task name: {task.get('_name')}\n"
        f"Task description: {task.get('description')}\n"
        f"Task input: {task.get('input')}\n"
        f"Ground truth: {json.dumps(task.get('groundTruth', {}), ensure_ascii=False)}\n\n"
        f"Rubric:\n{rubric}\n\n"
        f"Candidate output:\n{output}\n"
    )

    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
        "temperature": 0,
        "max_output_tokens": 200,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI judge HTTP error: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenAI judge network error: {e.reason}") from e

    text = payload.get("output_text")
    if not text:
        # fallback: try to collect text fragments
        text_parts: list[str] = []
        for item in payload.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    text_parts.append(c["text"])
        text = "\n".join(text_parts)

    try:
        judged = json.loads(text)
        score = float(judged.get("score", 0.0))
    except Exception as e:
        raise RuntimeError(f"Could not parse judge response as JSON score: {text!r}") from e

    return round(min(max(score, 0.0), 1.0), 3)


def score_output(output: str, rubric: str, task: dict, judge: str = "deterministic") -> float:
    if judge == "llm":
        return _openai_judge_score(output, rubric, task)
    return score_output_deterministic(output, rubric, task)


def run_benchmarks(genome, tasks: list[dict], judge: str = "deterministic") -> dict:
    results = []
    for task in tasks:
        output = run_skill_on_task(genome, task)
        try:
            score = score_output(output, task.get("_rubric", ""), task, judge=judge)
            judge_error = None
        except Exception as e:
            # Safe fallback keeps run alive.
            score = score_output_deterministic(output, task.get("_rubric", ""), task)
            judge_error = str(e)

        result = {"task": task.get("_name"), "score": score, "output": output}
        if judge_error:
            result["judgeError"] = judge_error
        results.append(result)

    total = sum(r["score"] for r in results) / len(results) if results else 0.0
    return {"tasks": results, "overall": total}


def build_evolution_prompt(genome, pre_results: dict) -> str:
    return f"""You are evolving an OpenClaw skill to improve benchmark scores.

## Skill: {genome.name}

### Current SKILL.md
{genome.prompt}

### TESTS.md
{genome.tests}

### HISTORY.md
{genome.history}

### Current benchmark results (overall: {pre_results['overall']:.3f})
{json.dumps(pre_results['tasks'], indent=2)}

## Task
Make EXACTLY ONE targeted improvement to SKILL.md that is likely to improve benchmark score.

Rules:
- One change only (surgical edit)
- Keep intent and method consistent (input spike delta)
- Preserve output requirements
- Do not add new external dependencies

Output format (mandatory):
<SKILL>
...complete new SKILL.md content...
</SKILL>
<HYPOTHESIS>
...1-3 sentences explaining why this single change should improve score...
</HYPOTHESIS>
"""


def _extract_tag(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def _openai_complete(prompt: str, model: str, max_output_tokens: int = 2200) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
        "temperature": 0.2,
        "max_output_tokens": max_output_tokens,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI HTTP error: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenAI network error: {e.reason}") from e

    text = payload.get("output_text")
    if not text:
        parts: list[str] = []
        for item in payload.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    parts.append(c["text"])
        text = "\n".join(parts)

    if not text:
        raise RuntimeError("Model returned empty output")
    return text


def evolve_skill(genome, pre_results: dict, evolver_model: str = "gpt-4o") -> tuple[str, str]:
    prompt = build_evolution_prompt(genome, pre_results)
    try:
        response_text = _openai_complete(prompt, model=evolver_model)
        new_skill = _extract_tag(response_text, "SKILL")
        hypothesis = _extract_tag(response_text, "HYPOTHESIS")

        if not new_skill:
            raise RuntimeError("Missing <SKILL>...</SKILL> in evolver response")
        if not hypothesis:
            hypothesis = "[No hypothesis tag returned by evolver model]"

        # Guardrail: avoid accidental empty/no-op writes.
        if not new_skill.strip():
            raise RuntimeError("Evolver returned empty SKILL content")

        return new_skill, hypothesis
    except Exception as e:
        # Safe fallback keeps pipeline functioning.
        return genome.prompt, f"[Evolution fallback: {e}]"


def main():
    parser = argparse.ArgumentParser(description="Evolve an OpenClaw skill via Nous")
    parser.add_argument("--skill", required=True, help="Skill name (e.g. compaction-cost)")
    parser.add_argument("--root", default=".", help="Repo root directory")
    parser.add_argument("--dry-run", action="store_true", help="Run benchmarks but don't apply changes")
    parser.add_argument("--judge", choices=["deterministic", "llm"], default="deterministic")
    parser.add_argument("--regression-threshold", type=float, default=0.05)
    parser.add_argument("--evolver-model", default=os.getenv("EVOLVER_MODEL", "gpt-4o"))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    skill_dir = root / "skills" / args.skill
    benchmarks_dir = root / "benchmarks"

    if not skill_dir.exists():
        print(f"Error: skill directory not found: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, str(root / "src"))
    from nous.skill_genome import SkillGenome

    genome = SkillGenome.load(skill_dir)
    gen = genome.config.get("version", 0)
    print(f"[evolve_skills] Skill: {genome.name} | Gen: {gen} | Judge: {args.judge} | Evolver: {args.evolver_model}")

    tasks = find_benchmark_tasks(benchmarks_dir, args.skill)
    print(f"[evolve_skills] Benchmark tasks: {len(tasks)}")

    print("[evolve_skills] Running pre-evolution benchmarks...")
    pre_results = run_benchmarks(genome, tasks, judge=args.judge)
    print(f"[evolve_skills] Pre-score: {pre_results['overall']:.3f}")

    if args.dry_run:
        print("[evolve_skills] Dry run — skipping evolution and mutation.")
        return

    old_prompt = genome.prompt
    new_prompt, hypothesis = evolve_skill(genome, pre_results, evolver_model=args.evolver_model)
    genome.save_prompt(new_prompt)

    print("[evolve_skills] Running post-evolution benchmarks...")
    post_results = run_benchmarks(genome, tasks, judge=args.judge)
    print(f"[evolve_skills] Post-score: {post_results['overall']:.3f}")

    delta = post_results["overall"] - pre_results["overall"]
    if delta < -args.regression_threshold:
        print(f"[evolve_skills] REGRESSION detected (delta={delta:.3f}). Reverting.")
        genome.save_prompt(old_prompt)
        entry = (
            f"\n## Gen {gen + 1} — {datetime.now().strftime('%Y-%m-%d')} (REVERTED)"
            f"\nHypothesis: {hypothesis}"
            f"\nPre: {pre_results['overall']:.3f} | Post: {post_results['overall']:.3f} | Delta: {delta:+.3f} ✗ REGRESSION\n"
        )
    else:
        print(f"[evolve_skills] Evolution successful (delta={delta:+.3f}). Applying.")
        genome.increment_version()
        entry = (
            f"\n## Gen {gen + 1} — {datetime.now().strftime('%Y-%m-%d')}"
            f"\nHypothesis: {hypothesis}"
            f"\nPre: {pre_results['overall']:.3f} | Post: {post_results['overall']:.3f} | Delta: {delta:+.3f} ✓\n"
        )

    genome.append_history(entry)
    print("[evolve_skills] Done. History updated.")


if __name__ == "__main__":
    main()
