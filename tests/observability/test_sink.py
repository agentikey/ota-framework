from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ota_core.observability import (
    FileObservabilitySink,
    NullObservabilitySink,
    ObservabilitySink,
    StdoutObservabilitySink,
)
from ota_core.trace import bind_trace


def test_protocol_satisfaction() -> None:
    assert isinstance(NullObservabilitySink(), ObservabilitySink)
    assert isinstance(StdoutObservabilitySink(), ObservabilitySink)


def test_null_sink_records_metric_in_memory() -> None:
    sink = NullObservabilitySink()
    sink.metric("tool_call.invoked", 1.0, attributes={"verb": "send_message"})
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record["kind"] == "metric"
    assert record["type"] == "counter"
    assert record["name"] == "tool_call.invoked"
    assert record["value"] == 1.0
    assert record["attributes"] == {"verb": "send_message"}


def test_metric_includes_active_trace_and_span() -> None:
    sink = NullObservabilitySink()
    trace = "01234567" * 4
    with bind_trace(trace_id=trace):
        sink.metric("llm.tokens", 42.0, kind="histogram")
    record = sink.records[0]
    assert record["trace_id"] == trace
    assert record["span_id"] is not None
    assert record["type"] == "histogram"


def test_span_records_start_and_end(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = NullObservabilitySink()
    with bind_trace():
        with sink.span("routine.run", attributes={"routine_id": "hello"}) as span:
            span.set_attribute("status", "ok")
            span.add_event("step.completed", {"step": "greet"})
    assert len(sink.records) == 1
    rec = sink.records[0]
    assert rec["kind"] == "span"
    assert rec["name"] == "routine.run"
    assert rec["attributes"] == {"routine_id": "hello", "status": "ok"}
    assert rec["events"][0]["name"] == "step.completed"
    assert rec["status"] == "ok"
    assert rec["duration_ms"] >= 0.0


def test_span_marks_error_on_exception() -> None:
    sink = NullObservabilitySink()
    with bind_trace():
        with pytest.raises(RuntimeError):
            with sink.span("routine.run"):
                raise RuntimeError("boom")
    assert sink.records[0]["status"] == "error"


def test_span_nested_parent_id() -> None:
    sink = NullObservabilitySink()
    with bind_trace() as (trace, _):
        with sink.span("outer"):
            with sink.span("inner") as inner:
                assert inner.trace_id == trace
                assert inner.parent_span_id is not None
    assert len(sink.records) == 2
    inner_rec = next(r for r in sink.records if r["name"] == "inner")
    outer_rec = next(r for r in sink.records if r["name"] == "outer")
    assert inner_rec["trace_id"] == outer_rec["trace_id"]


def test_file_sink_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "obs.jsonl"
    sink = FileObservabilitySink(path)
    with bind_trace():
        sink.metric("a", 1.0)
        with sink.span("op") as span:
            span.set_attribute("k", "v")
    sink.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    payloads = [json.loads(ln) for ln in lines]
    assert {p["kind"] for p in payloads} == {"metric", "span"}


def test_file_sink_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nest" / "obs.jsonl"
    sink = FileObservabilitySink(nested)
    sink.metric("a", 1.0)
    sink.close()
    assert nested.exists()


def test_stdout_sink_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    sink = StdoutObservabilitySink()
    sink._writer = sink._writer.__class__(captured, sink._lock)  # rebind to patched stdout
    sink.metric("stdout.ping", 1.0)
    payload = json.loads(captured.getvalue().splitlines()[0])
    assert payload["name"] == "stdout.ping"


def test_file_sink_context_manager_closes(tmp_path: Path) -> None:
    path = tmp_path / "obs.jsonl"
    with FileObservabilitySink(path) as sink:
        sink.metric("x", 1.0)
    assert path.exists()
