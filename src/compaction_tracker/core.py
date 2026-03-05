from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRICE_PER_M_INPUT_TOKENS = 3.0


def _assistant_input_tokens(event: dict) -> float | None:
    if event.get("type") != "message":
        return None
    msg = event.get("message") or {}
    if msg.get("role") != "assistant":
        return None
    usage = msg.get("usage") or {}
    value = usage.get("input")
    return float(value) if isinstance(value, (int, float)) else None


def analyze_session_file(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {
            "error": f"Session file not found: {path}",
            "method": "input spike delta",
            "usdRatePerMInputTokens": PRICE_PER_M_INPUT_TOKENS,
            "compactionCount": 0,
            "scoredCompactions": 0,
            "estimatedCompactionTokens": 0.0,
            "estimatedUSD": 0.0,
            "calculation": "N/A",
            "limitations": ["Input file missing."],
            "perEvent": [],
            "summary": "No compaction overhead detected in this session.",
        }

    events: list[dict[str, Any]] = []
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
    per_event: list[dict[str, Any]] = []
    total_delta = 0.0
    scored = 0

    for idx in compaction_indices:
        comp = events[idx]

        prev_inputs: list[float] = []
        j = idx - 1
        while j >= 0 and len(prev_inputs) < 3:
            tok = _assistant_input_tokens(events[j])
            if tok is not None:
                prev_inputs.append(tok)
            j -= 1
        prev_inputs.reverse()

        post_input: float | None = None
        j = idx + 1
        while j < len(events):
            tok = _assistant_input_tokens(events[j])
            if tok is not None:
                post_input = tok
                break
            j += 1

        row: dict[str, Any] = {
            "timestamp": comp.get("timestamp"),
            "tokensBefore": comp.get("tokensBefore"),
            "preAverageInputTokens": None,
            "postInputTokens": post_input,
            "deltaTokens": None,
            "notes": "",
        }

        if post_input is None:
            row["notes"] = "Unscorable: no assistant message with usage.input after compaction."
        elif not prev_inputs:
            row["notes"] = "Unscorable: no prior assistant messages with usage.input."
        else:
            pre_avg = sum(prev_inputs) / len(prev_inputs)
            delta = post_input - pre_avg
            row["preAverageInputTokens"] = round(pre_avg, 3)
            row["deltaTokens"] = round(delta, 3)
            row["notes"] = f"Used {len(prev_inputs)} prior assistant message(s) for pre-average."
            total_delta += delta
            scored += 1

        per_event.append(row)

    estimated_usd = total_delta * (PRICE_PER_M_INPUT_TOKENS / 1_000_000)
    summary = (
        "No compaction overhead detected in this session."
        if not compaction_indices
        else f"Estimated compaction overhead across {scored}/{len(compaction_indices)} scored event(s)."
    )

    return {
        "method": "input spike delta",
        "usdRatePerMInputTokens": PRICE_PER_M_INPUT_TOKENS,
        "compactionCount": len(compaction_indices),
        "scoredCompactions": scored,
        "estimatedCompactionTokens": round(total_delta, 3),
        "estimatedUSD": round(estimated_usd, 8),
        "calculation": "delta = first_post_compaction_assistant_input - average(last_3_pre_compaction_assistant_inputs)",
        "limitations": [
            "Estimate may over/under-count in tool-heavy or atypical prompt-growth turns.",
            "Does not directly account for memoryFlush message tokenization.",
        ],
        "perEvent": per_event,
        "summary": summary,
    }
