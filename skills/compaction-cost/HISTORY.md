# Evolution History

## Gen 0 — 2026-03-05 (baseline)
Method: Input spike delta method
Hypothesis: The delta between average pre-compaction input tokens and first post-compaction input tokens approximates the summarization overhead.
Result: Pending first benchmark run.
Known weaknesses: May overcount on tool-heavy sessions; does not account for memoryFlush message tokens.


## Gen 2 — 2026-03-05
Hypothesis: [Evolution fallback: OpenAI HTTP error: 400 Bad Request]
Pre: 1.000 | Post: 1.000 | Delta: +0.000 ✓


## Gen 3 — 2026-03-05 (REJECTED)
Hypothesis: [Evolution fallback: OpenAI HTTP error: 400 Bad Request]
Reason: prompt diff ratio 0.0000 below threshold 0.0100.
Pre: 1.000 | Post: 1.000 | Delta: +0.000 ✗ NO-OP
