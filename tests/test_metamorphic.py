from datadiff.datagen import generate_case
from datadiff.dsl import Case, ColumnSpec, Program, TableData
from datadiff.metamorphic import build_metamorphic_variants


def test_metamorphic_builds_row_permutation_without_limit():
    case = generate_case(7)
    case.program = Program(case.program.program_id, case.program.seed, [{"op": "select", "columns": ["id"]}])
    variants = build_metamorphic_variants(case, limit=20)
    assert any(v.relation == "row_permutation" for v in variants)


def test_metamorphic_skips_row_permutation_with_limit():
    case = generate_case(8)
    case.program = Program(case.program.program_id, case.program.seed, [{"op": "limit", "n": 1}])
    variants = build_metamorphic_variants(case, limit=20)
    assert not any(v.relation == "row_permutation" for v in variants)


def test_row_permutation_preserves_join_tables():
    case = Case(
        "case-join",
        1,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 10}, {"id": 2, "x": 20}],
            ),
            TableData(
                "t1",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("j", "int")],
                [{"id": 1, "j": 100}, {"id": 2, "j": 200}],
            ),
        ],
        Program(
            "prog-join",
            1,
            [{"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "inner"}],
        ),
    )

    variant = next(v for v in build_metamorphic_variants(case, limit=20) if v.relation == "row_permutation")

    assert [table.name for table in variant.case.tables] == ["t0", "t1"]
    assert variant.case.tables[0].rows == [{"id": 2, "x": 20}, {"id": 1, "x": 10}]
    assert variant.case.tables[1].rows == case.tables[1].rows


def test_metamorphic_builds_filter_idempotence():
    case = generate_case(9)
    case.program = Program(
        case.program.program_id,
        case.program.seed,
        [{"op": "filter", "column": "id", "cmp": ">=", "value": 0}],
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "filter_idempotence")
    assert variant.case.program.operations == [
        {"op": "filter", "column": "id", "cmp": ">=", "value": 0},
        {"op": "filter", "column": "id", "cmp": ">=", "value": 0},
    ]


def test_metamorphic_builds_limit_idempotence():
    case = generate_case(10)
    case.program = Program(case.program.program_id, case.program.seed, [{"op": "limit", "n": 3}])

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "limit_idempotence")
    assert variant.case.program.operations == [{"op": "limit", "n": 3}, {"op": "limit", "n": 3}]


def test_metamorphic_builds_sort_idempotence():
    case = generate_case(12)
    case.program = Program(
        case.program.program_id,
        case.program.seed,
        [{"op": "sort", "columns": ["id", "g"], "ascending": False}],
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "sort_idempotence")
    assert variant.case.program.operations == [
        {"op": "sort", "columns": ["id", "g"], "ascending": False},
        {"op": "sort", "columns": ["id", "g"], "ascending": False},
    ]


def test_metamorphic_builds_groupby_key_permutation():
    case = generate_case(11, profile="workflow")
    case.program = Program(
        case.program.program_id,
        case.program.seed,
        [
            {
                "op": "groupby",
                "keys": ["flag", "g"],
                "aggs": [{"column": "x", "func": "count", "as": "count_x"}],
            }
        ],
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "groupby_key_permutation")
    assert variant.case.program.operations[0]["keys"] == ["g", "flag"]


def test_metamorphic_builds_groupby_aggregation_permutation():
    case = generate_case(15, profile="workflow")
    case.program = Program(
        case.program.program_id,
        case.program.seed,
        [
            {
                "op": "groupby",
                "keys": ["g"],
                "aggs": [
                    {"column": "x", "func": "count", "as": "count_x"},
                    {"column": "id", "func": "sum", "as": "sum_id"},
                ],
            }
        ],
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "groupby_aggregation_permutation")
    assert variant.case.program.operations[0]["aggs"] == [
        {"column": "id", "func": "sum", "as": "sum_id"},
        {"column": "x", "func": "count", "as": "count_x"},
    ]


def test_metamorphic_builds_groupby_neutral_mutation():
    case = Case(
        "case-groupby-neutral",
        17,
        [
            TableData(
                "t0",
                [ColumnSpec("g", "str"), ColumnSpec("x", "int")],
                [{"g": "a", "x": 1}, {"g": "a", "x": None}],
            )
        ],
        Program(
            "prog-groupby-neutral",
            17,
            [{"op": "groupby", "keys": ["g"], "aggs": [{"column": "x", "func": "sum", "as": "sum_x"}]}],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "groupby_neutral_mutation")
    assert variant.case.program.operations == [
        {"op": "mutate", "column": "mr_x_plus0", "expr": {"kind": "add_const", "source": "x", "value": 0}},
        {"op": "groupby", "keys": ["g"], "aggs": [{"column": "mr_x_plus0", "func": "sum", "as": "sum_x"}]},
    ]


def test_metamorphic_builds_mutate_add_zero_insertion():
    case = Case(
        "case-mutate-zero",
        18,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 2}],
            )
        ],
        Program("prog-mutate-zero", 18, [{"op": "select", "columns": ["id", "x"]}]),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "mutate_add_zero_insertion")
    assert variant.case.program.operations[0] == {
        "op": "mutate",
        "column": "id",
        "expr": {"kind": "add_const", "source": "id", "value": 0},
    }


def test_metamorphic_builds_join_inner_left_equivalence_when_keys_are_covered():
    case = Case(
        "case-join-covered",
        19,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 10}, {"id": 2, "x": 20}],
            ),
            TableData(
                "t1",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("j", "int")],
                [{"id": 1, "j": 100}, {"id": 2, "j": 200}, {"id": 2, "j": 201}],
            ),
        ],
        Program(
            "prog-join-covered",
            19,
            [{"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"}],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "join_inner_left_equivalence")
    assert variant.case.program.operations[0]["how"] == "inner"


def test_metamorphic_builds_join_filter_pushdown_for_left_column():
    case = Case(
        "case-join-filter-pushdown",
        20,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 10}, {"id": 2, "x": 20}],
            ),
            TableData(
                "t1",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("j", "int")],
                [{"id": 1, "j": 100}, {"id": 2, "j": 200}],
            ),
        ],
        Program(
            "prog-join-filter-pushdown",
            20,
            [
                {"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"},
                {"op": "filter", "column": "x", "cmp": ">=", "value": 10},
            ],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "join_filter_pushdown")
    assert [op["op"] for op in variant.case.program.operations] == ["filter", "join"]


def test_metamorphic_builds_filter_mutate_commutation_for_independent_columns():
    case = Case(
        "case-filter-mutate-commute",
        21,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 10}, {"id": 2, "x": 20}],
            )
        ],
        Program(
            "prog-filter-mutate-commute",
            21,
            [
                {"op": "filter", "column": "id", "cmp": ">=", "value": 1},
                {"op": "mutate", "column": "x2", "expr": {"kind": "add_const", "source": "x", "value": 1}},
            ],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "filter_mutate_commutation")
    assert [op["op"] for op in variant.case.program.operations] == ["mutate", "filter"]


def test_metamorphic_builds_filter_tautology_insertion():
    case = generate_case(16)
    case.program = Program(case.program.program_id, case.program.seed, [{"op": "select", "columns": ["id", "x"]}])

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "filter_tautology_insertion")
    assert variant.case.program.operations[0] == {"op": "filter", "column": "id", "cmp": ">=", "value": 0}
    assert variant.case.program.operations[1:] == [{"op": "select", "columns": ["id", "x"]}]


def test_metamorphic_builds_sort_select_commutation():
    case = generate_case(13)
    case.program = Program(
        case.program.program_id,
        case.program.seed,
        [
            {"op": "select", "columns": ["g", "id", "x"]},
            {"op": "sort", "columns": ["id", "g"], "ascending": True},
        ],
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "sort_select_commutation")
    assert variant.case.program.operations == [
        {"op": "sort", "columns": ["id", "g"], "ascending": True},
        {"op": "select", "columns": ["g", "id", "x"]},
    ]


def test_join_table_permutation_reverses_secondary_table():
    case = Case(
        "case-join-secondary",
        2,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 10}, {"id": 2, "x": 20}],
            ),
            TableData(
                "t1",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("j", "int")],
                [{"id": 1, "j": 100}, {"id": 2, "j": 200}],
            ),
        ],
        Program(
            "prog-join-secondary",
            2,
            [{"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"}],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "join_table_permutation")
    assert variant.case.tables[0].rows == case.tables[0].rows
    assert variant.case.tables[1].rows == [{"id": 2, "j": 200}, {"id": 1, "j": 100}]


def test_domain_metamorphic_injects_filter_rejecting_row():
    case = Case(
        "case-cleaning",
        3,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("flag", "bool")],
                [{"id": 1, "flag": True}, {"id": 2, "flag": True}],
            )
        ],
        Program("prog-cleaning", 3, [{"op": "filter", "column": "flag", "cmp": "==", "value": True}]),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "filter_rejecting_row_injection")
    assert variant.case.tables[0].rows[-1] == {"id": 0, "flag": False}
    assert variant.case.program.operations == case.program.operations


def test_domain_metamorphic_injects_unmatched_dimension_row():
    case = Case(
        "case-enrichment",
        4,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("x", "int")],
                [{"id": 1, "x": 10}, {"id": 2, "x": 20}],
            ),
            TableData(
                "t1",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("tag", "str")],
                [{"id": 1, "tag": "gold"}, {"id": 2, "tag": "silver"}],
            ),
        ],
        Program(
            "prog-enrichment",
            4,
            [{"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"}],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "join_unmatched_dimension_injection")
    assert variant.case.tables[0].rows == case.tables[0].rows
    assert variant.case.tables[1].rows[-1]["id"] not in {1, 2}
    assert variant.case.tables[1].rows[-1]["tag"] == ""


def test_domain_metamorphic_repeats_string_lower_normalization():
    case = Case(
        "case-log-normalization",
        5,
        [
            TableData(
                "t0",
                [ColumnSpec("id", "int", nullable=False), ColumnSpec("s", "str")],
                [{"id": 1, "s": "ERROR"}, {"id": 2, "s": "warn"}],
            )
        ],
        Program(
            "prog-log-normalization",
            5,
            [{"op": "mutate", "column": "level", "expr": {"kind": "string_lower", "source": "s"}}],
        ),
    )

    variants = build_metamorphic_variants(case, limit=20)

    variant = next(v for v in variants if v.relation == "string_lower_idempotence")
    assert variant.case.program.operations == [
        {"op": "mutate", "column": "level", "expr": {"kind": "string_lower", "source": "s"}},
        {"op": "mutate", "column": "level", "expr": {"kind": "string_lower", "source": "level"}},
    ]
