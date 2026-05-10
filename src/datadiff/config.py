from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

OracleMode = Literal["differential", "metamorphic", "both"]
GeneratorProfile = Literal["common", "edge_float"]


@dataclass(slots=True)
class ExperimentConfig:
    enable_type_aware_generation: bool = True
    enable_normalizer: bool = True
    enable_differential_oracle: bool = True
    enable_metamorphic_oracle: bool = False
    enable_feedback: bool = True
    enable_reducer: bool = False
    enable_artifact: bool = True
    oracle_mode: OracleMode = "differential"
    generator_profile: GeneratorProfile = "common"

    def to_dict(self) -> dict:
        return asdict(self)
