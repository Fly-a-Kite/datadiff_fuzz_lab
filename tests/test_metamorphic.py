from datadiff.datagen import generate_case
from datadiff.dsl import Program
from datadiff.metamorphic import build_metamorphic_variants


def test_metamorphic_builds_row_permutation_without_limit():
    case = generate_case(7)
    case.program = Program(case.program.program_id, case.program.seed, [{"op": "select", "columns": ["id"]}])
    variants = build_metamorphic_variants(case)
    assert any(v.relation == "row_permutation" for v in variants)


def test_metamorphic_skips_row_permutation_with_limit():
    case = generate_case(8)
    case.program = Program(case.program.program_id, case.program.seed, [{"op": "limit", "n": 1}])
    variants = build_metamorphic_variants(case)
    assert not any(v.relation == "row_permutation" for v in variants)
