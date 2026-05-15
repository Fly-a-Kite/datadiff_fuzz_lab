# Triage Report: case-00008632-bughunt-mut-8676-mut-8844

- Verdict: `candidate_implementation_bug`
- Paper status: `submitted_upstream_needs_external_confirmation`
- Upstream issue: https://github.com/apache/datafusion/issues/22190
- Confidence: `high`
- Generator profile: `bughunt`
- Backends: pandas, duckdb, datafusion
- Rows: 27
- Operations: 10
- Reduced: False
- Original kinds: semantic_output_mismatch
- Reproduced kinds: semantic_output_mismatch
- Reproduced roots: grouped_topk_null_sort_key
- Suspicious backends: datafusion

## Features

- contains_null: True
- contains_nan: False
- contains_inf: False
- contains_non_ascii_string: True
- uses_filter: True
- uses_mutate: True
- uses_modulo: False
- uses_string_lower: False
- uses_groupby: True
- uses_sort: True
- uses_limit: True
- operation_sequence: ['join', 'mutate', 'filter', 'select', 'groupby', 'select', 'sort', 'select', 'sort', 'limit']

## Recommendation

- Minimize the artifact and create a backend-specific reproduction script.
- Submitted upstream as https://github.com/apache/datafusion/issues/22190.
- Count as confirmed only after maintainer acknowledgement, fix, or clear spec violation.
