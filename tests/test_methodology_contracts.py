from datadiff.cli import _preset_config
from datadiff.targets import TARGETS, common_capabilities, resolve_target_backends


CORE_METHOD_CAPABILITIES = {
    "op:filter",
    "op:mutate",
    "op:groupby",
    "op:join",
    "op:sort",
    "op:limit",
    "expr:arith_const",
    "expr:string_lower",
    "agg:min",
    "agg:count",
    "nulls",
}


def test_methodology_targets_span_multiple_framework_families():
    implemented = [target for target in TARGETS.values() if target.status == "implemented"]
    families = {target.family for target in implemented}
    layers = {target.layer for target in implemented}

    assert {"dataframe", "embedded_sql", "query_engine", "arrow"}.issubset(families)
    assert {"python_dataframe", "embedded_analytical_engine", "arrow_query_engine", "arrow_compute"}.issubset(layers)
    assert len([target for target in implemented if target.family != "seeded_fault"]) >= 7


def test_methodology_cross_family_suites_keep_common_dsl_contract():
    suites = {
        "core": resolve_target_backends(target_suite="core"),
        "core_lazy": resolve_target_backends(target_suite="core_lazy"),
        "core_datafusion": resolve_target_backends(target_suite="core_datafusion"),
        "core_arrow": resolve_target_backends(target_suite="core_arrow"),
        "datafusion_cross": resolve_target_backends(target_suite="datafusion_cross"),
        "arrow_cross": resolve_target_backends(target_suite="arrow_cross"),
    }

    for suite, backends in suites.items():
        families = {TARGETS[backend].family for backend in backends}
        assert len(families) >= 2, suite
        assert CORE_METHOD_CAPABILITIES.issubset(common_capabilities(backends)), suite


def test_methodology_experiment_presets_cover_required_ablation_axes():
    baseline = _preset_config("baseline")
    no_type = _preset_config("no_type_aware")
    no_normalizer = _preset_config("no_normalizer")
    no_feedback = _preset_config("no_feedback")
    metamorphic = _preset_config("metamorphic")
    guided = _preset_config("guided")
    guided_join = _preset_config("guided_join")

    assert baseline.enable_type_aware_generation
    assert baseline.enable_normalizer
    assert baseline.enable_feedback
    assert not no_type.enable_type_aware_generation
    assert not no_normalizer.enable_normalizer
    assert not no_feedback.enable_feedback
    assert metamorphic.enable_metamorphic_oracle
    assert metamorphic.oracle_mode == "both"
    assert guided.guidance_strategy == "guided"
    assert guided.guidance_candidate_pool > 1
    assert guided_join.generator_profile == "bughunt_no_groupby"
    assert "join" in guided_join.guidance_targets


def test_methodology_bug_hunting_presets_target_distinct_semantic_risks():
    null_groupby = _preset_config("null_groupby_topk")
    null_agg = _preset_config("null_agg_topk")
    float_group = _preset_config("float_group_key")
    float_group_meta = _preset_config("float_group_key_metamorphic")

    assert null_groupby.generator_profile == "null_groupby_topk"
    assert {"groupby", "nulls", "sort_limit"}.issubset(null_groupby.guidance_targets)
    assert null_agg.generator_profile == "null_agg_topk"
    assert {"aggregation", "nulls", "sort_limit"}.issubset(null_agg.guidance_targets)
    assert float_group.generator_profile == "float_group_key"
    assert {"join", "mutate", "groupby", "expressions"}.issubset(float_group.guidance_targets)
    assert float_group_meta.enable_metamorphic_oracle
    assert float_group_meta.metamorphic_variant_limit > float_group.metamorphic_variant_limit


def test_methodology_seeded_fault_suites_support_sensitivity_evaluation():
    assert resolve_target_backends(target_suite="seeded_filter") == ["pandas", "buggy_filter"]
    assert resolve_target_backends(target_suite="seeded_groupby") == ["pandas", "buggy_groupby"]
    assert resolve_target_backends(target_suite="seeded_join") == ["pandas", "buggy_join"]
    assert resolve_target_backends(target_suite="seeded_mutate") == ["pandas", "buggy_mutate"]
