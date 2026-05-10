from __future__ import annotations

from dataclasses import dataclass, field

from datadiff.dsl import Case
from datadiff.mutator import mutate_case
from datadiff.util import CORPUS_DIR, dump_json


@dataclass(slots=True)
class FeedbackState:
    max_corpus: int = 256
    seen_signatures: set[str] = field(default_factory=set)
    interesting_cases: list[Case] = field(default_factory=list)

    def choose_case(self, seed: int, generated: Case) -> Case:
        if not self.interesting_cases or seed % 3 != 0:
            return generated
        base = self.interesting_cases[seed % len(self.interesting_cases)]
        return mutate_case(base, seed)

    def record(self, case: Case, behavior_signature: str, has_finding: bool) -> bool:
        is_new = behavior_signature not in self.seen_signatures
        self.seen_signatures.add(behavior_signature)
        if not (is_new or has_finding):
            return False
        if len(self.interesting_cases) < self.max_corpus:
            self.interesting_cases.append(case)
        elif has_finding:
            self.interesting_cases[int(behavior_signature, 16) % self.max_corpus] = case
        self._write_interesting_case(case, behavior_signature, has_finding)
        return True

    def _write_interesting_case(self, case: Case, behavior_signature: str, has_finding: bool) -> None:
        path = CORPUS_DIR / "interesting" / f"{behavior_signature}.json"
        dump_json(
            {
                "behavior_signature": behavior_signature,
                "has_finding": has_finding,
                "case": case.to_dict(),
            },
            path,
        )
