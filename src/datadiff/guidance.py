from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from datadiff.dsl import Case
from datadiff.util import unique_preserve_order

TARGET_ALIASES: dict[str, set[str]] = {
    "filter": {"op:filter"},
    "groupby": {"op:groupby"},
    "mutate": {"op:mutate"},
    "sort": {"op:sort"},
    "limit": {"op:limit"},
    "sort_limit": {"op:sort", "op:limit"},
    "nulls": {"has:null"},
    "strings": {"type:str", "has:empty_string", "has:unicode_string", "has:space_string"},
    "numeric": {"type:int", "type:float", "has:negative_number", "has:fractional_float"},
    "edge_float": {"has:special_float", "has:fractional_float"},
    "empty": {"rows:empty", "op:limit_zero"},
    "aggregation": {"op:groupby", "agg:sum", "agg:min", "agg:max", "agg:count"},
    "null_groupby_topk": {"pattern:null_groupby_topk"},
    "null_agg_topk": {"pattern:null_agg_topk"},
    "float_group_key": {"pattern:float_group_key"},
    "join": {"op:join", "tables:multi"},
    "expressions": {"expr:add_const", "expr:arith_const", "expr:string_length", "expr:string_lower", "expr:cast"},
    "casts": {"expr:cast"},
}


def parse_guidance_targets(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple)) else value.split(",")
    targets = []
    for item in raw:
        text = str(item).strip()
        if text:
            targets.append(text)
    return targets


def extract_case_features(case: Case) -> set[str]:
    features: set[str] = set()
    table = case.tables[0]
    features.add("tables:multi" if len(case.tables) > 1 else "tables:single")
    row_count = len(table.rows)
    col_count = len(table.columns)
    features.add(_bucket("rows", row_count, [(0, "empty"), (3, "tiny"), (10, "small"), (20, "medium")], "large"))
    features.add(_bucket("cols", col_count, [(3, "narrow"), (5, "medium")], "wide"))
    for column in table.columns:
        features.add(f"type:{column.type}")
        features.add(f"nullable:{column.type}:{column.nullable}")

    for row in table.rows:
        for value in row.values():
            if value is None:
                features.add("has:null")
            elif isinstance(value, bool):
                features.add(f"bool:{str(value).lower()}")
            elif isinstance(value, int):
                if value < 0:
                    features.add("has:negative_number")
                elif value == 0:
                    features.add("has:zero")
            elif isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    features.add("has:special_float")
                elif not value.is_integer():
                    features.add("has:fractional_float")
                if value < 0:
                    features.add("has:negative_number")
                elif value == 0:
                    features.add("has:zero")
            elif isinstance(value, str):
                if value == "":
                    features.add("has:empty_string")
                if any(ord(ch) > 127 for ch in value):
                    features.add("has:unicode_string")
                if " " in value:
                    features.add("has:space_string")

    op_names = []
    available_types = {column.name: column.type for column in table.columns}
    for op in case.program.operations:
        kind = str(op.get("op", "unknown"))
        op_names.append(kind)
        features.add(f"op:{kind}")
        if kind == "filter":
            cmp = str(op.get("cmp", "unknown"))
            column = str(op.get("column", "unknown"))
            features.add(f"cmp:{cmp}")
            features.add(f"filter_type:{available_types.get(column, 'derived')}")
        elif kind == "select":
            width = len(op.get("columns", []))
            features.add(_bucket("select_width", width, [(1, "one"), (3, "few")], "many"))
        elif kind == "sort":
            features.add(f"sort:{'asc' if op.get('ascending', True) else 'desc'}")
        elif kind == "join":
            features.add(f"join:{op.get('how', 'unknown')}")
            features.add(f"join_table:{op.get('table', 'unknown')}")
        elif kind == "limit":
            limit = int(op.get("n", 0))
            if limit == 0:
                features.add("op:limit_zero")
            features.add(_bucket("limit", limit, [(0, "zero"), (3, "tiny"), (10, "small")], "large"))
        elif kind == "mutate":
            expr = op.get("expr", {})
            expr_kind = expr.get("kind", "unknown")
            features.add(f"mutate:{expr_kind}")
            features.add(f"expr:{expr_kind}")
            if expr_kind == "arith_const":
                features.add(f"arith:{expr.get('op', 'unknown')}")
            if expr_kind == "cast":
                features.add(f"cast_to:{expr.get('to', 'unknown')}")
        elif kind == "groupby":
            for key in op.get("keys", []):
                features.add(f"group_key_type:{available_types.get(key, 'derived')}")
            for agg in op.get("aggs", []):
                features.add(f"agg:{agg.get('func', 'unknown')}")
                available_types[str(agg.get("as", "derived"))] = "float"
    if op_names:
        features.add("opseq:" + ">".join(op_names))
        features.add(_bucket("op_count", len(op_names), [(1, "one"), (3, "few"), (5, "many")], "deep"))
    _, frontier_buckets = _frontier_signature(case)
    features.update(frontier_buckets)
    if _has_null_groupby_topk_pattern(op_names, frontier_buckets):
        features.add("pattern:null_groupby_topk")
    if _has_null_agg_topk_pattern(case.program.operations, frontier_buckets):
        features.add("pattern:null_agg_topk")
    if _has_float_group_key_pattern(case.program.operations):
        features.add("pattern:float_group_key")
    return features


@dataclass(slots=True)
class GuidanceDecision:
    case: Case
    score: float
    features: list[str]
    matched_targets: list[str]
    candidate_count: int
    contributing_candidate_count: int = 1
    pruned_candidate_count: int = 0
    frontier_buckets: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 6),
            "features": self.features,
            "matched_targets": self.matched_targets,
            "candidate_count": self.candidate_count,
            "contributing_candidate_count": self.contributing_candidate_count,
            "pruned_candidate_count": self.pruned_candidate_count,
            "frontier_buckets": self.frontier_buckets,
            "score_breakdown": {
                key: round(value, 6) for key, value in sorted(self.score_breakdown.items())
            },
        }


@dataclass(slots=True)
class GuidanceState:
    targets: list[str] = field(default_factory=list)
    feature_counts: Counter[str] = field(default_factory=Counter)
    finding_feature_counts: Counter[str] = field(default_factory=Counter)
    root_cause_counts: Counter[str] = field(default_factory=Counter)
    frontier_bucket_counts: Counter[str] = field(default_factory=Counter)

    def choose_case(self, candidates: list[Case]) -> GuidanceDecision:
        if not candidates:
            raise ValueError("guided candidate pool cannot be empty")
        scored = [self._score_case(case, len(candidates)) for case in candidates]
        contributing = [decision for decision in scored if self._is_contributing_candidate(decision)]
        if not contributing:
            contributing = [max(scored, key=lambda decision: (decision.score, -decision.case.seed))]
        pruned = len(scored) - len(contributing)
        for decision in contributing:
            decision.contributing_candidate_count = len(contributing)
            decision.pruned_candidate_count = pruned
        return max(contributing, key=lambda decision: (decision.score, -decision.case.seed))

    def record_result(self, case: Case, row: dict[str, Any]) -> None:
        features = extract_case_features(case)
        self.feature_counts.update(features)
        _, frontier_buckets = _frontier_signature(case)
        self.frontier_bucket_counts.update(frontier_buckets)
        findings = row.get("findings") or []
        if findings:
            self.finding_feature_counts.update(features)
            for finding in findings:
                root = str(finding.get("root_cause", "unknown"))
                self.root_cause_counts[root] += 1

    def _score_case(self, case: Case, candidate_count: int) -> GuidanceDecision:
        features = extract_case_features(case)
        matched_targets = _matched_targets(features, self.targets)
        path_coverage_proxy = _path_coverage_proxy(features, self.feature_counts)
        data_sensitivity = _data_sensitivity_score(features, self.feature_counts)
        frontier_conformance, frontier_buckets = _frontier_conformance(case, self.frontier_bucket_counts)
        target_bonus = 3.0 * len(matched_targets)
        finding_yield_bonus = (
            sum(
                _bounded_finding_signal(self.finding_feature_counts[f]) * _finding_feature_weight(f)
                for f in features
            )
            / math.sqrt(max(1, len(features)))
            * 0.50
        )
        feature_saturation_penalty = (
            sum(
                _feature_saturation(self.finding_feature_counts[f]) * _saturation_feature_weight(f)
                for f in features
            )
            / math.sqrt(max(1, len(features)))
            * 0.08
        )
        root_saturation_penalty = sum(
            _root_saturation(self.root_cause_counts[root]) for root in _predicted_roots(features)
        )
        if matched_targets:
            root_saturation_penalty *= 0.35
        contribution_potential = _contribution_potential(
            features,
            frontier_buckets,
            matched_targets,
            frontier_conformance,
            feature_counts=self.feature_counts,
            frontier_bucket_counts=self.frontier_bucket_counts,
            root_cause_counts=self.root_cause_counts,
        )
        score = path_coverage_proxy + data_sensitivity + frontier_conformance + target_bonus + finding_yield_bonus
        score -= feature_saturation_penalty + root_saturation_penalty
        return GuidanceDecision(
            case=case,
            score=score,
            features=sorted(features),
            matched_targets=matched_targets,
            candidate_count=candidate_count,
            frontier_buckets=frontier_buckets,
            score_breakdown={
                "path_coverage_proxy": path_coverage_proxy,
                "data_sensitivity": data_sensitivity,
                "frontier_conformance": frontier_conformance,
                "target_bonus": target_bonus,
                "finding_yield_bonus": finding_yield_bonus,
                "contribution_potential": contribution_potential,
                "feature_saturation_penalty": -feature_saturation_penalty,
                "root_saturation_penalty": -root_saturation_penalty,
            },
        )

    def _is_contributing_candidate(self, decision: GuidanceDecision) -> bool:
        features = set(decision.features)
        unseen_path = any(_is_path_feature(feature) and self.feature_counts[feature] == 0 for feature in features)
        unseen_frontier = any(self.frontier_bucket_counts[bucket] == 0 for bucket in decision.frontier_buckets)
        frontier_conformance = decision.score_breakdown.get("frontier_conformance", 0.0)
        contribution_potential = decision.score_breakdown.get("contribution_potential", 0.0)

        if decision.matched_targets:
            return True
        if unseen_path or unseen_frontier:
            return True
        if frontier_conformance >= 0.80:
            return True
        return contribution_potential >= 1.15


def _matched_targets(features: set[str], targets: list[str]) -> list[str]:
    matched = []
    for target in targets:
        required = TARGET_ALIASES.get(target, {target})
        if features & required:
            matched.append(target)
    return matched


def _bucket(prefix: str, value: int, limits: list[tuple[int, str]], fallback: str) -> str:
    for limit, name in limits:
        if value <= limit:
            return f"{prefix}:{name}"
    return f"{prefix}:{fallback}"


def _bounded_finding_signal(count: int) -> float:
    if count <= 0:
        return 0.0
    return min(math.log1p(count), 2.0) / (1.0 + count / 50.0)


def _feature_saturation(count: int) -> float:
    if count <= 25:
        return 0.0
    return math.log1p(count - 25)


def _root_saturation(count: int) -> float:
    if count <= 20:
        return 0.0
    return math.log1p(count - 20) * 0.22


def _finding_feature_weight(feature: str) -> float:
    if feature.startswith(("op:", "opseq:")):
        return 1.0
    if feature.startswith(("agg:", "cmp:", "expr:", "mutate:", "join:", "filter_type:", "cast_to:")):
        return 0.75
    if feature.startswith(("has:", "type:", "nullable:")):
        return 0.35
    return 0.50


def _path_coverage_proxy(features: set[str], feature_counts: Counter[str]) -> float:
    path_features = [feature for feature in features if _is_path_feature(feature)]
    if not path_features:
        return 0.0
    novelty = sum(_path_feature_weight(feature) / (1.0 + feature_counts[feature]) for feature in path_features)
    op_diversity = sum(1 for feature in path_features if feature.startswith("op:")) * 0.12
    sequence_bonus = 0.20 if any(feature.startswith("opseq:") for feature in path_features) else 0.0
    return novelty / math.sqrt(len(path_features)) + op_diversity + sequence_bonus


def _data_sensitivity_score(features: set[str], feature_counts: Counter[str]) -> float:
    data_features = [feature for feature in features if _is_data_sensitivity_feature(feature)]
    if not data_features:
        return 0.0
    weighted = sum(
        _data_feature_weight(feature) * (1.0 + 1.0 / (1.0 + feature_counts[feature]))
        for feature in data_features
    )
    return weighted / math.sqrt(len(data_features)) * 0.35


def _saturation_feature_weight(feature: str) -> float:
    if feature.startswith("opseq:"):
        return 1.0
    if feature.startswith("op:"):
        return 0.9
    if feature.startswith(("agg:", "cmp:", "expr:", "mutate:", "join:", "filter_type:", "cast_to:")):
        return 0.65
    if feature.startswith(("has:", "type:", "nullable:")):
        return 0.15
    return 0.25


def _is_path_feature(feature: str) -> bool:
    return feature.startswith(
        (
            "op:",
            "opseq:",
            "pattern:",
            "cmp:",
            "filter_type:",
            "select_width:",
            "sort:",
            "join:",
            "join_table:",
            "limit:",
            "mutate:",
            "expr:",
            "arith:",
            "cast_to:",
            "group_key_type:",
            "agg:",
            "op_count:",
            "groupby:",
        )
    )


def _path_feature_weight(feature: str) -> float:
    if feature.startswith("opseq:"):
        return 1.4
    if feature.startswith("pattern:"):
        return 1.6
    if feature.startswith("op:"):
        return 1.0
    if feature.startswith(("join:", "agg:", "expr:", "mutate:", "cmp:", "group_key_type:")):
        return 0.9
    if feature.startswith(("filter_type:", "select_width:", "sort:", "limit:", "cast_to:", "arith:")):
        return 0.7
    return 0.5


def _is_data_sensitivity_feature(feature: str) -> bool:
    return feature.startswith(
        (
            "tables:",
            "rows:",
            "cols:",
            "type:",
            "nullable:",
            "has:",
            "bool:",
        )
    ) or feature in {"op:limit_zero", "groupby:null-key", "groupby:null-agg-output"}


def _data_feature_weight(feature: str) -> float:
    if feature == "groupby:null-key":
        return 1.6
    if feature == "groupby:null-agg-output":
        return 1.7
    if feature in {"has:special_float", "has:null", "has:unicode_string"}:
        return 1.8
    if feature in {"has:fractional_float", "has:negative_number", "has:empty_string", "has:space_string"}:
        return 1.2
    if feature in {"tables:multi", "rows:empty", "rows:tiny", "cols:wide", "op:limit_zero"}:
        return 1.0
    if feature.startswith(("nullable:", "type:")):
        return 0.6
    if feature.startswith("bool:"):
        return 0.4
    return 0.5


def _frontier_conformance(case: Case, frontier_bucket_counts: Counter[str]) -> tuple[float, list[str]]:
    raw_score, frontier_buckets = _frontier_signature(case)
    if not frontier_buckets:
        return raw_score, frontier_buckets
    novelty = (
        sum(1.0 / (1.0 + frontier_bucket_counts[bucket]) for bucket in frontier_buckets)
        / math.sqrt(len(frontier_buckets))
        * 0.35
    )
    return raw_score + novelty, frontier_buckets


def _frontier_signature(case: Case) -> tuple[float, list[str]]:
    if not case.tables:
        return 0.0, []

    table_by_name = {table.name: table for table in case.tables}
    samples = {column.name: [row.get(column.name) for row in case.tables[0].rows] for column in case.tables[0].columns}
    scores: list[float] = []
    buckets: list[str] = []

    for op in case.program.operations:
        kind = str(op.get("op", ""))
        if kind == "filter":
            score, op_buckets = _filter_frontier_score(samples, op)
            scores.append(score)
            buckets.extend(op_buckets)
        elif kind == "join":
            right = table_by_name.get(str(op.get("table", "")))
            score, op_buckets = _join_frontier_score(samples, right, op)
            scores.append(score)
            buckets.extend(op_buckets)
            if right is not None:
                for column in right.columns:
                    if column.name == op.get("right_on"):
                        continue
                    samples[column.name] = [row.get(column.name) for row in right.rows]
        elif kind == "select":
            cols = [str(column) for column in op.get("columns", []) if str(column) in samples]
            samples = {column: samples[column] for column in unique_preserve_order(cols)}
        elif kind == "sort":
            score, op_buckets = _sort_frontier_score(samples, op)
            scores.append(score)
            buckets.extend(op_buckets)
        elif kind == "limit":
            score, op_buckets = _limit_frontier_score(samples, op)
            scores.append(score)
            buckets.extend(op_buckets)
        elif kind == "mutate":
            score, op_buckets, values = _mutate_frontier_score(samples, op)
            scores.append(score)
            buckets.extend(op_buckets)
            column = str(op.get("column", ""))
            if column:
                samples[column] = values
        elif kind == "groupby":
            score, op_buckets = _groupby_frontier_score(samples, op)
            scores.append(score)
            buckets.extend(op_buckets)
            samples = _groupby_output_samples(samples, op)

    scores = [score for score in scores if score > 0.0]
    return (sum(scores) / len(scores) if scores else 0.0), unique_preserve_order(buckets)


def _contribution_potential(
    features: set[str],
    frontier_buckets: list[str],
    matched_targets: list[str],
    frontier_conformance: float,
    *,
    feature_counts: Counter[str],
    frontier_bucket_counts: Counter[str],
    root_cause_counts: Counter[str],
) -> float:
    path_novelty = sum(1 for feature in features if _is_path_feature(feature) and feature_counts[feature] == 0)
    data_novelty = sum(1 for feature in features if _is_data_sensitivity_feature(feature) and feature_counts[feature] == 0)
    frontier_novelty = sum(1 for bucket in frontier_buckets if frontier_bucket_counts[bucket] == 0)
    root_novelty = sum(1 for root in _predicted_roots(features) if root_cause_counts[root] == 0)
    root_saturation = sum(1 for root in _predicted_roots(features) if root_cause_counts[root] >= 40)
    return (
        frontier_conformance
        + 0.30 * path_novelty
        + 0.20 * data_novelty
        + 0.45 * frontier_novelty
        + 0.35 * root_novelty
        + 0.60 * len(matched_targets)
        - 0.20 * root_saturation
    )


def _filter_frontier_score(samples: dict[str, list[Any]], op: dict[str, Any]) -> tuple[float, list[str]]:
    column = str(op.get("column", ""))
    values = samples.get(column, [])
    comparator = str(op.get("cmp", ""))
    literal = op.get("value")
    buckets: list[str] = []
    if not values:
        return 0.0, buckets

    if any(value is None for value in values):
        buckets.append("filter:null-aware")
    numeric_values = _numeric_values(values)
    if numeric_values and isinstance(literal, (int, float)) and not isinstance(literal, bool):
        spread = max(numeric_values) - min(numeric_values) if len(numeric_values) > 1 else 0.0
        scale = max(1.0, abs(float(literal)), spread)
        min_diff = min(abs(value - float(literal)) for value in numeric_values)
        closeness = 1.0 / (1.0 + (min_diff / scale))
        if min_diff == 0:
            buckets.append("filter:exact-hit")
        elif closeness >= 0.65:
            buckets.append("filter:near-hit")
        else:
            buckets.append("filter:range-probe")
        if comparator in {">", "<", ">=", "<="}:
            buckets.append(f"filter:cmp:{comparator}")
        return min(1.0, 0.40 + 0.45 * closeness + (0.10 if "filter:null-aware" in buckets else 0.0)), buckets

    scalar_values = [value for value in values if value is not None]
    if literal in scalar_values:
        buckets.append("filter:exact-hit")
        return 0.85, buckets
    if isinstance(literal, str):
        buckets.append("filter:string-literal")
        return 0.55 + (0.10 if any(isinstance(value, str) and value == "" for value in scalar_values) else 0.0), buckets
    if isinstance(literal, bool):
        buckets.append("filter:bool-literal")
        return 0.60, buckets
    return 0.30, buckets


def _join_frontier_score(
    samples: dict[str, list[Any]],
    right: Any,
    op: dict[str, Any],
) -> tuple[float, list[str]]:
    left_on = str(op.get("left_on", ""))
    right_on = str(op.get("right_on", ""))
    left_values = [value for value in samples.get(left_on, []) if value is not None]
    right_values = [] if right is None else [row.get(right_on) for row in right.rows if row.get(right_on) is not None]
    buckets: list[str] = []
    if right is None or (not left_values and not right_values):
        return 0.0, buckets

    left_set = set(left_values)
    right_set = set(right_values)
    union = left_set | right_set
    overlap = len(left_set & right_set) / max(1, len(union))
    partial_overlap = 1.0 - abs(overlap - 0.5) * 2.0
    if overlap == 0.0:
        buckets.append("join:no-overlap")
    elif overlap >= 0.95:
        buckets.append("join:full-overlap")
    else:
        buckets.append("join:partial-overlap")
    if len(left_values) != len(left_set) or len(right_values) != len(right_set):
        buckets.append("join:duplicate-keys")
    if any(value is None for value in samples.get(left_on, [])) or any(row.get(right_on) is None for row in getattr(right, "rows", [])):
        buckets.append("join:null-keys")
    return min(1.0, 0.35 + 0.45 * max(0.0, partial_overlap) + 0.10 * int("join:duplicate-keys" in buckets) + 0.05 * int("join:null-keys" in buckets)), buckets


def _groupby_frontier_score(samples: dict[str, list[Any]], op: dict[str, Any]) -> tuple[float, list[str]]:
    keys = [str(key) for key in op.get("keys", []) if str(key) in samples]
    buckets: list[str] = []
    if not keys:
        return 0.0, buckets
    row_count = min((len(samples[key]) for key in keys), default=0)
    if row_count <= 0:
        return 0.0, buckets
    tuples = [tuple(samples[key][idx] for key in keys) for idx in range(row_count)]
    distinct = len(set(tuples))
    distinct_ratio = distinct / max(1, row_count)
    mixed = 1.0 - abs(distinct_ratio - 0.5) * 2.0
    if distinct == 1:
        buckets.append("groupby:single-group")
    elif distinct == row_count:
        buckets.append("groupby:high-cardinality")
    else:
        buckets.append("groupby:mixed-cardinality")
    if any(any(value is None for value in group) for group in tuples):
        buckets.append("groupby:null-key")
    if len(op.get("aggs", [])) > 1:
        buckets.append("groupby:multi-agg")
    if _has_null_aggregate_output(samples, op, tuples):
        buckets.append("groupby:null-agg-output")
    return min(1.0, 0.35 + 0.45 * max(0.0, mixed) + 0.10 * int("groupby:multi-agg" in buckets) + 0.05 * int("groupby:null-key" in buckets) + 0.08 * int("groupby:null-agg-output" in buckets)), buckets


def _groupby_output_samples(samples: dict[str, list[Any]], op: dict[str, Any]) -> dict[str, list[Any]]:
    keys = [str(key) for key in op.get("keys", []) if str(key) in samples]
    row_count = min((len(samples[key]) for key in keys), default=0)
    if row_count <= 0:
        return {key: [] for key in keys}
    groups: dict[tuple[Any, ...], list[int]] = {}
    for idx in range(row_count):
        key_tuple = tuple(samples[key][idx] for key in keys)
        groups.setdefault(key_tuple, []).append(idx)

    out: dict[str, list[Any]] = {key: [] for key in keys}
    for key_tuple in groups:
        for idx, key in enumerate(keys):
            out[key].append(key_tuple[idx])
    for agg in op.get("aggs", []):
        alias = str(agg.get("as", ""))
        source = str(agg.get("column", ""))
        func = str(agg.get("func", ""))
        if not alias:
            continue
        source_values = samples.get(source, [])
        values = []
        for indices in groups.values():
            group_values = [source_values[idx] for idx in indices if idx < len(source_values)]
            non_null = [value for value in group_values if value is not None]
            if func == "count":
                values.append(len(non_null))
            elif not non_null:
                values.append(None)
            elif func == "sum":
                values.append(sum(non_null))
            elif func == "min":
                values.append(min(non_null))
            elif func == "max":
                values.append(max(non_null))
            else:
                values.append(None)
        out[alias] = values
    return out


def _has_null_aggregate_output(
    samples: dict[str, list[Any]],
    op: dict[str, Any],
    tuples: list[tuple[Any, ...]],
) -> bool:
    if not tuples:
        return False
    groups: dict[tuple[Any, ...], list[int]] = {}
    for idx, key_tuple in enumerate(tuples):
        groups.setdefault(key_tuple, []).append(idx)
    for agg in op.get("aggs", []):
        if agg.get("func") == "count":
            continue
        source_values = samples.get(str(agg.get("column", "")), [])
        for indices in groups.values():
            if all(idx >= len(source_values) or source_values[idx] is None for idx in indices):
                return True
    return False


def _mutate_frontier_score(samples: dict[str, list[Any]], op: dict[str, Any]) -> tuple[float, list[str], list[Any]]:
    expr = op.get("expr", {})
    kind = str(expr.get("kind", ""))
    source = str(expr.get("source", ""))
    values = list(samples.get(source, []))
    buckets: list[str] = []
    if not values:
        return 0.0, buckets, values

    if kind in {"add_const", "arith_const", "cast"}:
        numeric_values = _numeric_values(values)
        if any(value is None for value in values):
            buckets.append("mutate:null-propagation")
        if any(value < 0 for value in numeric_values):
            buckets.append("mutate:negative")
        if any(value == 0 for value in numeric_values):
            buckets.append("mutate:zero")
        if any(not float(value).is_integer() for value in numeric_values):
            buckets.append("mutate:fractional")
        if kind == "arith_const":
            buckets.append(f"mutate:arith:{expr.get('op', 'unknown')}")
        if kind == "cast":
            buckets.append("mutate:cast")
        score = 0.35 + 0.15 * int("mutate:null-propagation" in buckets) + 0.15 * int("mutate:negative" in buckets) + 0.15 * int("mutate:zero" in buckets) + 0.10 * int("mutate:fractional" in buckets)
        if kind == "arith_const" and expr.get("op") in {"div", "mod"}:
            score += 0.10
        return min(1.0, score), buckets, _evaluate_mutate_values(values, expr)

    string_values = [value for value in values if isinstance(value, str)]
    if any(value == "" for value in string_values):
        buckets.append("mutate:empty-string")
    if any(" " in value for value in string_values):
        buckets.append("mutate:space-string")
    if any(any(ord(ch) > 127 for ch in value) for value in string_values):
        buckets.append("mutate:unicode-string")
    if any(_has_mixed_case(value) for value in string_values):
        buckets.append("mutate:mixed-case")
    score = 0.35 + 0.15 * int("mutate:empty-string" in buckets) + 0.10 * int("mutate:space-string" in buckets) + 0.15 * int("mutate:unicode-string" in buckets) + 0.15 * int("mutate:mixed-case" in buckets)
    return min(1.0, score), buckets, _evaluate_mutate_values(values, expr)


def _sort_frontier_score(samples: dict[str, list[Any]], op: dict[str, Any]) -> tuple[float, list[str]]:
    columns = [str(column) for column in op.get("columns", []) if str(column) in samples]
    buckets: list[str] = []
    if not columns:
        return 0.0, buckets
    values = samples[columns[0]]
    non_null = [value for value in values if value is not None]
    if len(non_null) != len(set(non_null)):
        buckets.append("sort:duplicate-key")
    if any(value is None for value in values):
        buckets.append("sort:null-order")
    if not buckets:
        return 0.0, buckets
    return min(1.0, 0.30 + 0.20 * len(buckets)), buckets


def _limit_frontier_score(samples: dict[str, list[Any]], op: dict[str, Any]) -> tuple[float, list[str]]:
    row_count = max((len(values) for values in samples.values()), default=0)
    try:
        limit = int(op.get("n", 0))
    except (TypeError, ValueError):
        return 0.0, []
    buckets: list[str] = []
    if limit == 0:
        buckets.append("limit:zero")
    if row_count and abs(limit - row_count) <= 1:
        buckets.append("limit:row-boundary")
    if row_count and abs(limit - (row_count + 1)) <= 1:
        buckets.append("limit:overflow-boundary")
    if not buckets:
        return 0.0, buckets
    return min(1.0, 0.30 + 0.20 * len(buckets)), buckets


def _evaluate_mutate_values(values: list[Any], expr: dict[str, Any]) -> list[Any]:
    kind = str(expr.get("kind", ""))
    out: list[Any] = []
    for value in values:
        if value is None:
            out.append(None)
            continue
        try:
            if kind == "add_const":
                out.append(value + expr.get("value", 0))
            elif kind == "arith_const":
                operand = expr.get("value", 0)
                op = expr.get("op")
                if op == "sub":
                    out.append(value - operand)
                elif op == "mul":
                    out.append(value * operand)
                elif op == "div":
                    out.append(value / operand)
                elif op == "mod":
                    out.append(value % operand)
                else:
                    out.append(None)
            elif kind == "cast":
                out.append(float(value))
            elif kind == "string_length":
                out.append(len(value) if isinstance(value, str) else None)
            elif kind == "string_lower":
                out.append(value.lower() if isinstance(value, str) else None)
            else:
                out.append(None)
        except Exception:
            out.append(None)
    return out


def _numeric_values(values: list[Any]) -> list[float]:
    out = []
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def _has_mixed_case(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    return any(ch.islower() for ch in letters) and any(ch.isupper() for ch in letters)


def _predicted_roots(features: set[str]) -> set[str]:
    roots = set()
    if "has:special_float" in features:
        roots.add("nan_inf_semantics")
    if "op:join" in features:
        roots.add("join_semantics")
    if "op:groupby" in features:
        roots.add("float_group_key_instability" if "pattern:float_group_key" in features else "groupby_aggregation")
    if "op:filter" in features:
        roots.add("filter_predicate")
    if "op:mutate" in features:
        if features & {"expr:string_length", "expr:string_lower"}:
            roots.add("string_expression")
        elif "expr:cast" in features:
            roots.add("type_cast")
        else:
            roots.add("arithmetic_expression")
    if features & {"op:sort", "op:limit"}:
        roots.add("ordering_or_limit")
    if "has:null" in features:
        roots.add("null_semantics")
    return roots


def _has_null_groupby_topk_pattern(op_names: list[str], frontier_buckets: list[str]) -> bool:
    if "groupby:null-key" not in frontier_buckets or "sort:null-order" not in frontier_buckets:
        return False
    try:
        groupby_idx = op_names.index("groupby")
        sort_idx = next(idx for idx, name in enumerate(op_names[groupby_idx + 1 :], start=groupby_idx + 1) if name == "sort")
        next(idx for idx, name in enumerate(op_names[sort_idx + 1 :], start=sort_idx + 1) if name == "limit")
    except (StopIteration, ValueError):
        return False
    return True


def _has_null_agg_topk_pattern(ops: list[dict[str, Any]], frontier_buckets: list[str]) -> bool:
    if "groupby:null-agg-output" not in frontier_buckets or "sort:null-order" not in frontier_buckets:
        return False
    for groupby_idx, op in enumerate(ops):
        if op.get("op") != "groupby":
            continue
        agg_aliases = {str(agg.get("as", "")) for agg in op.get("aggs", []) if agg.get("as")}
        if not agg_aliases:
            continue
        for sort_idx in range(groupby_idx + 1, len(ops)):
            sort_op = ops[sort_idx]
            if sort_op.get("op") != "sort":
                continue
            if not (agg_aliases & {str(column) for column in sort_op.get("columns", [])}):
                continue
            if any(later.get("op") == "limit" for later in ops[sort_idx + 1 :]):
                return True
    return False


def _has_float_group_key_pattern(ops: list[dict[str, Any]]) -> bool:
    div_columns: set[str] = set()
    for op in ops:
        kind = op.get("op")
        if kind == "mutate":
            expr = op.get("expr", {})
            if expr.get("kind") == "arith_const" and expr.get("op") == "div":
                div_columns.add(str(op.get("column", "")))
        elif kind == "groupby":
            keys = {str(key) for key in op.get("keys", [])}
            return bool(keys & div_columns)
    return False
