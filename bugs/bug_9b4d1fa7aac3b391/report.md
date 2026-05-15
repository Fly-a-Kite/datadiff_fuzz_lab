# Bug Artifact: case-00008632-bughunt-mut-8676-mut-8844

Seed: `8844`

## Program

```json
{
  "program_id": "prog-00008632-mut-8676-mut-8844",
  "seed": 8844,
  "operations": [
    {
      "op": "join",
      "table": "t1",
      "left_on": "id",
      "right_on": "id",
      "how": "inner"
    },
    {
      "op": "mutate",
      "column": "m_0",
      "expr": {
        "kind": "add_const",
        "source": "y",
        "value": -2
      }
    },
    {
      "op": "filter",
      "column": "m_0",
      "cmp": "<=",
      "value": 0.0
    },
    {
      "op": "select",
      "columns": [
        "flag",
        "g",
        "j",
        "m_0",
        "tag",
        "x",
        "y"
      ]
    },
    {
      "op": "groupby",
      "keys": [
        "g"
      ],
      "aggs": [
        {
          "column": "x",
          "func": "min",
          "as": "min_x"
        },
        {
          "column": "m_0",
          "func": "count",
          "as": "count_m_0"
        }
      ]
    },
    {
      "op": "select",
      "columns": [
        "count_m_0",
        "min_x"
      ]
    },
    {
      "op": "sort",
      "columns": [
        "count_m_0",
        "min_x"
      ],
      "ascending": true
    },
    {
      "op": "select",
      "columns": [
        "min_x"
      ]
    },
    {
      "op": "sort",
      "columns": [
        "min_x"
      ],
      "ascending": true
    },
    {
      "op": "limit",
      "n": 20
    }
  ]
}
```

## Findings
- **semantic_output_mismatch** severity=critical root=groupby_aggregation oracle=differential confidence=high triage=candidate_implementation_bug triage_confidence=high suspicious=['datafusion']: Backends returned different canonical tables; shapes={'pandas': (15, 1), 'duckdb': (15, 1), 'datafusion': (14, 1)}
  - triage_evidence=Independent DSL reference agrees with ['duckdb', 'pandas'] and disagrees with ['datafusion'].

## Reproduce

```bash
python reproduce.py
```

## Environment

```json
{
  "python": "3.13.3 (main, Apr  8 2025, 13:54:08) [Clang 17.0.0 (clang-1700.0.13.3)]",
  "platform": "macOS-26.4-arm64-arm-64bit-Mach-O",
  "pandas": "3.0.2",
  "polars": "1.40.1",
  "duckdb": "1.5.2",
  "sqlite": "3.49.2",
  "datadiff_fuzz_lab": "0.1.0"
}
```
