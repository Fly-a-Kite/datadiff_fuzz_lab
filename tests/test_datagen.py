from datadiff.datagen import generate_case


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


def test_generated_program_uses_existing_columns_initially():
    case = generate_case(7)
    table_cols = {c.name for c in case.tables[0].columns}
    known_cols = set(table_cols)
    for op in case.program.operations:
        if op["op"] == "filter":
            assert op["column"] in known_cols
        elif op["op"] == "select":
            assert set(op["columns"]).issubset(known_cols)
            known_cols = set(op["columns"])
        elif op["op"] == "mutate":
            assert op["expr"]["source"] in known_cols
            known_cols.add(op["column"])
        elif op["op"] == "groupby":
            assert set(op["keys"]).issubset(known_cols)
            for agg in op["aggs"]:
                assert agg["column"] in known_cols
                known_cols.add(agg["as"])


def test_generated_programs_are_valid_for_seed_range():
    for seed in range(100):
        case = generate_case(seed)
        table_cols = {c.name for c in case.tables[0].columns}
        known_cols = set(table_cols)
        for op in case.program.operations:
            if op["op"] == "filter":
                assert op["column"] in known_cols
            elif op["op"] == "select":
                assert set(op["columns"]).issubset(known_cols)
                known_cols = set(op["columns"])
            elif op["op"] == "sort":
                assert set(op["columns"]).issubset(known_cols)
            elif op["op"] == "mutate":
                assert op["expr"]["source"] in known_cols
                known_cols.add(op["column"])
            elif op["op"] == "groupby":
                assert set(op["keys"]).issubset(known_cols)
                for agg in op["aggs"]:
                    assert agg["column"] in known_cols
                known_cols = set(op["keys"]) | {agg["as"] for agg in op["aggs"]}
