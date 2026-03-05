# Evaluation Criteria

A successful implementation should satisfy all of the following:

- Correctly identifies all compaction events (no missed events, no false positives)
- Token estimate is within 15% of ground truth
- Dollar estimate is within 15% of ground truth
- Handles sessions with zero compactions gracefully (reports `0`, `$0.00`)
- Handles sessions with multiple back-to-back compactions
