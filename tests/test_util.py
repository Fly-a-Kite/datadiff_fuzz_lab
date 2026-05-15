from pathlib import Path

import pytest

from datadiff.util import JsonlWriter, append_jsonl, jsonl_log_stem, parse_duration, read_jsonl, run_meta_path, unique_preserve_order


def test_parse_duration_units():
    assert parse_duration("10s") == 10
    assert parse_duration("2m") == 120
    assert parse_duration("1.5h") == 5400


def test_parse_duration_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_duration("abc")


def test_jsonl_helpers_read_and_write_gzip(tmp_path):
    path = tmp_path / "run-x.jsonl.gz"

    append_jsonl({"case": 1, "status": "ok"}, path)
    append_jsonl({"case": 2, "status": "bug"}, path)

    assert path.read_bytes().startswith(b"\x1f\x8b")
    assert read_jsonl(path) == [
        {"case": 1, "status": "ok"},
        {"case": 2, "status": "bug"},
    ]


def test_jsonl_writer_keeps_gzip_stream_open(tmp_path):
    path = tmp_path / "run-stream.jsonl.gz"

    with JsonlWriter(path, compresslevel=1) as writer:
        writer.write({"case": 1})
        writer.write({"case": 2})

    assert read_jsonl(path) == [{"case": 1}, {"case": 2}]


def test_jsonl_log_stem_and_run_meta_path_support_plain_and_gzip():
    plain_path = Path("runs/run-x.jsonl")
    assert jsonl_log_stem(plain_path) == "run-x"
    assert run_meta_path(plain_path).name == "run-x.meta.json"

    gzip_path = Path("runs/run-y.jsonl.gz")
    assert jsonl_log_stem(gzip_path) == "run-y"
    assert run_meta_path(gzip_path).name == "run-y.meta.json"


def test_unique_preserve_order_removes_duplicates():
    assert unique_preserve_order(["x", "x", "g", "x", "m_1"]) == ["x", "g", "m_1"]
