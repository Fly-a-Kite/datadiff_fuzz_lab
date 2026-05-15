# DataDiffFuzz Pattern Variant Analysis

- Manifest: `runs/experiment-20260514T195546.json`
- Pattern: `null_agg_topk`
- Cases: 2988
- Candidate cases: 2562
- False-positive findings: 0

| target suite | preset | agg | sort | cases | candidate cases | false positives | top families |
|---|---|---|---|---:|---:|---:|---|
| core_datafusion | null_agg_topk | max | asc | 69 | 0 | 0 | none |
| core_datafusion | null_agg_topk | max | desc | 714 | 664 | 0 | grouped_topk_null_sort_key@datafusion:664 |
| core_datafusion | null_agg_topk | min | asc | 667 | 621 | 0 | grouped_topk_null_sort_key@datafusion:621 |
| core_datafusion | null_agg_topk | min | desc | 44 | 0 | 0 | none |
| datafusion_cross | null_agg_topk | max | asc | 74 | 0 | 0 | none |
| datafusion_cross | null_agg_topk | max | desc | 698 | 646 | 0 | grouped_topk_null_sort_key@datafusion:646 |
| datafusion_cross | null_agg_topk | min | asc | 677 | 631 | 0 | grouped_topk_null_sort_key@datafusion:631 |
| datafusion_cross | null_agg_topk | min | desc | 45 | 0 | 0 | none |
