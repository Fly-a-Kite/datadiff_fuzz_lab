from datadiff import feedback
from datadiff.dsl import Case, ColumnSpec, Program, TableData
from datadiff.feedback import FeedbackState


def _case(seed: int) -> Case:
    return Case(
        f"case-{seed}",
        seed,
        [TableData("t0", [ColumnSpec("x", "int")], [{"x": seed}])],
        Program(f"prog-{seed}", seed, []),
    )


def test_feedback_persistence_is_bounded_per_run(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "CORPUS_DIR", tmp_path / "corpus")
    state = FeedbackState(persist_to_disk=True, max_persisted=2)

    assert state.record(_case(1), "0000000000000001", False) is True
    assert state.last_persisted_to_disk is True
    assert state.record(_case(2), "0000000000000002", False) is True
    assert state.last_persisted_to_disk is True
    assert state.record(_case(3), "0000000000000003", True) is True
    assert state.last_persisted_to_disk is False

    persisted = sorted((tmp_path / "corpus" / "interesting").glob("*.json"))
    assert len(persisted) == 2
    assert state.persisted_count == 2


def test_feedback_persistence_limit_zero_disables_disk_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "CORPUS_DIR", tmp_path / "corpus")
    state = FeedbackState(persist_to_disk=True, max_persisted=0)

    assert state.record(_case(1), "0000000000000001", True) is True

    assert state.last_persisted_to_disk is False
    assert not (tmp_path / "corpus" / "interesting").exists()
