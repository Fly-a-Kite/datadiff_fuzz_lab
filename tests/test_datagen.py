from datadiff.datagen import generate_case
from datadiff.classification_oracle import validate_case_program


def _assert_program_columns_are_valid(case):
    table_by_name = {table.name: table for table in case.tables}
    known_cols = {c.name for c in case.tables[0].columns}
    for op in case.program.operations:
        if op["op"] == "join":
            right = table_by_name[op["table"]]
            assert op["left_on"] in known_cols
            assert op["right_on"] in {c.name for c in right.columns}
            known_cols.update(c.name for c in right.columns if c.name != op["right_on"])
        elif op["op"] == "filter":
            assert op["column"] in known_cols
        elif op["op"] == "select":
            assert set(op["columns"]).issubset(known_cols)
            assert len(op["columns"]) == len(set(op["columns"]))
            known_cols = set(op["columns"])
        elif op["op"] == "sort":
            assert set(op["columns"]).issubset(known_cols)
            assert len(op["columns"]) == len(set(op["columns"]))
        elif op["op"] == "mutate":
            assert op["expr"]["source"] in known_cols
            known_cols.add(op["column"])
        elif op["op"] == "groupby":
            assert set(op["keys"]).issubset(known_cols)
            assert len(op["keys"]) == len(set(op["keys"]))
            for agg in op["aggs"]:
                assert agg["column"] in known_cols
            aliases = [agg["as"] for agg in op["aggs"]]
            assert len(aliases) == len(set(aliases))
            known_cols = set(op["keys"]) | {agg["as"] for agg in op["aggs"]}


def test_generate_case_is_deterministic():
    a = generate_case(123).to_dict()
    b = generate_case(123).to_dict()
    assert a == b
    assert a["case_id"] == "case-00000123"
    assert a["tables"][0]["rows"] or a["tables"][0]["columns"]


def test_generate_case_edge_float_profile_is_supported():
    case = generate_case(123, profile="edge_float")
    assert case.case_id == "case-00000123"
    assert case.program.operations


def test_generate_case_workflow_profile_is_supported_and_valid():
    case = generate_case(123, profile="workflow")
    assert case.case_id.startswith("case-00000123-workflow-")
    assert case.program.operations
    assert validate_case_program(case) == []


def test_workflow_profile_covers_named_workflow_families():
    families = set()
    for seed in range(10):
        case = generate_case(seed, profile="workflow")
        families.add(case.case_id.rsplit("-", 1)[-1])
        assert validate_case_program(case) == []
    assert families == {"etl", "log", "feature", "join", "null"}


def test_generate_case_bughunt_profile_is_supported_and_valid():
    case = generate_case(123, profile="bughunt")
    assert case.case_id == "case-00000123-bughunt"
    assert case.program.operations
    assert validate_case_program(case) == []


def test_generate_case_bughunt_no_groupby_profile_is_supported_and_valid():
    case = generate_case(123, profile="bughunt_no_groupby")
    assert case.case_id == "case-00000123-bughunt-no-groupby"
    assert case.program.operations
    assert all(op["op"] != "groupby" for op in case.program.operations)
    assert validate_case_program(case) == []


def test_bughunt_no_groupby_profile_excludes_groupby_without_type_aware_generation():
    cases = [generate_case(seed, type_aware=False, profile="bughunt_no_groupby") for seed in range(100)]

    assert all("groupby" not in {op["op"] for op in case.program.operations} for case in cases)


def test_generate_case_null_groupby_topk_profile_is_supported_and_valid():
    case = generate_case(123, profile="null_groupby_topk")
    assert case.case_id == "case-00000123-null-groupby-topk"
    assert [op["op"] for op in case.program.operations] == ["mutate", "groupby", "select", "sort", "limit"]
    assert any(row["s"] is None for row in case.tables[0].rows)
    assert validate_case_program(case) == []


def test_generate_case_null_agg_topk_profile_is_supported_and_valid():
    case = generate_case(123, profile="null_agg_topk")
    assert case.case_id == "case-00000123-null-agg-topk"
    assert [op["op"] for op in case.program.operations] == ["groupby", "select", "sort", "limit"]
    assert all(row["g"] is not None for row in case.tables[0].rows)
    assert any(row["x"] is None for row in case.tables[0].rows)
    agg = case.program.operations[0]["aggs"][0]
    sort = case.program.operations[2]
    assert agg["func"] in {"min", "max"}
    assert case.program.operations[1]["columns"] == [agg["as"]]
    assert sort["columns"] == [agg["as"]]
    assert sort["ascending"] is (agg["func"] == "min")
    assert validate_case_program(case) == []


def test_null_agg_topk_profile_covers_min_asc_and_max_desc():
    pairs = set()
    for seed in range(50):
        case = generate_case(seed, profile="null_agg_topk")
        agg = case.program.operations[0]["aggs"][0]
        sort = case.program.operations[2]
        pairs.add((agg["func"], sort["ascending"]))
    assert ("min", True) in pairs
    assert ("max", False) in pairs


def test_generate_case_float_group_key_profile_is_supported_and_valid():
    case = generate_case(123, profile="float_group_key")
    assert case.case_id == "case-00000123-float-group-key"
    assert [op["op"] for op in case.program.operations] == [
        "join",
        "mutate",
        "filter",
        "sort",
        "mutate",
        "mutate",
        "mutate",
        "groupby",
    ]
    assert case.program.operations[-1]["keys"] == ["m_3"]
    assert validate_case_program(case) == []


def test_bughunt_profile_biases_toward_multi_table_and_deeper_programs():
    cases = [generate_case(seed, profile="bughunt") for seed in range(50)]
    multi_table_count = sum(1 for case in cases if len(case.tables) > 1)
    avg_ops = sum(len(case.program.operations) for case in cases) / len(cases)
    assert multi_table_count >= 30
    assert avg_ops >= 3.0


def test_bughunt_profile_biases_toward_join_mutate_groupby_paths():
    cases = [generate_case(seed, profile="bughunt") for seed in range(100)]
    combined = 0
    covered_joins = 0
    for case in cases:
        ops = {op["op"] for op in case.program.operations}
        combined += int({"join", "mutate", "groupby"}.issubset(ops))
        if len(case.tables) > 1 and "join" in ops:
            left_ids = {row["id"] for row in case.tables[0].rows}
            right_ids = {row["id"] for row in case.tables[1].rows}
            covered_joins += int(left_ids.issubset(right_ids))
    assert combined >= 50
    assert covered_joins >= 50


def test_bughunt_no_groupby_profile_biases_join_mutate_filter_without_groupby():
    cases = [generate_case(seed, profile="bughunt_no_groupby") for seed in range(100)]
    assert all("groupby" not in {op["op"] for op in case.program.operations} for case in cases)
    joined = 0
    mut_filter = 0
    for case in cases:
        ops = {op["op"] for op in case.program.operations}
        joined += int("join" in ops)
        mut_filter += int({"mutate", "filter"}.issubset(ops))
    assert joined >= 50
    assert mut_filter >= 50


def test_generated_program_uses_existing_columns_initially():
    case = generate_case(7)
    _assert_program_columns_are_valid(case)


def test_generated_programs_are_valid_for_seed_range():
    for seed in range(100):
        case = generate_case(seed)
        _assert_program_columns_are_valid(case)


def test_generator_can_emit_join_and_new_expressions():
    seen_ops = set()
    seen_exprs = set()
    for seed in range(300):
        case = generate_case(seed)
        seen_ops.update(op["op"] for op in case.program.operations)
        for op in case.program.operations:
            if op["op"] == "mutate":
                seen_exprs.add(op["expr"]["kind"])
    assert "join" in seen_ops
    assert {"arith_const", "string_length", "string_lower", "cast"} & seen_exprs


def test_common_and_workflow_profiles_do_not_emit_modulo_by_default():
    for seed in range(500):
        assert not _case_uses_modulo(generate_case(seed))
    for seed in range(20):
        assert not _case_uses_modulo(generate_case(seed, profile="workflow"))


def test_edge_float_profile_can_emit_modulo_boundary_cases():
    assert any(_case_uses_modulo(generate_case(seed, profile="edge_float")) for seed in range(300))


def _case_uses_modulo(case):
    return any(
        op.get("op") == "mutate"
        and op.get("expr", {}).get("kind") == "arith_const"
        and op.get("expr", {}).get("op") == "mod"
        for op in case.program.operations
    )
