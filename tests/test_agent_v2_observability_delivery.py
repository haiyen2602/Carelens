"""BUILD-18B P1: structured Agent V2 telemetry must actually reach captured
process output, not just be correctly constructed in memory.

Root cause (see backend/main.py's comment at the ``logging.basicConfig``
call): nothing in this application ever configured Python's ``logging``
module, so every ``logging.getLogger(...).info(...)`` call -- including
``backend/agents/v2/observability.py::StructuredLogSink``, BUILD-13's own
sink -- was silently dropped by logging's handler-of-last-resort (WARNING+
only), in every environment, not just Railway. This does not redesign
BUILD-13's event schema, allowlist, or redaction; it only makes the
already-correct events reach stdout.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.agents.v2.observability import StructuredLogSink, TelemetryEvent, TraceComponent, TraceContext


def test_importing_the_app_configures_a_root_log_handler_at_or_below_info():
    import backend.main  # noqa: F401  (module-level logging.basicConfig side effect)

    assert logging.root.handlers, "backend.main must configure a root logging handler"
    telemetry_logger = logging.getLogger("backend.agents.v2.telemetry")
    assert telemetry_logger.getEffectiveLevel() <= logging.INFO


def test_third_party_http_client_logging_does_not_leak_request_urls():
    """BUILD-20: the ``logging.basicConfig`` fix above is a necessary, correct
    fix for BUILD-13's own telemetry -- but it also unmuzzles every
    third-party logger with no level of its own, since the root level now
    applies to them too. ``httpx`` (used by the OpenAI SDK and Vinmec Web)
    logs one INFO line per outbound request containing the full request URL
    -- for a GET request that includes the query string, and Vinmec Web's
    search query is exactly the patient's own message. Confirmed live on
    staging during this build: "HTTP Request: GET
    https://www.vinmec.com/vie/tim-kiem/?q=<patient's own message>" was
    reaching the log stream. This must not regress: httpx/httpcore stay
    above INFO while this app's own telemetry logger is unaffected.
    """

    import backend.main  # noqa: F401  (module-level logging config side effect)

    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).getEffectiveLevel() > logging.INFO
    # The fix must be scoped to the noisy third-party loggers specifically,
    # not achieved by lowering the root/telemetry level generally (which
    # would silently reintroduce BUILD-18B's original defect).
    assert logging.getLogger("backend.agents.v2.telemetry").getEffectiveLevel() <= logging.INFO


def test_structured_agent_v2_event_reaches_a_handler_and_would_propagate_to_the_configured_root():
    """Two things must both hold for a real process: (1) emitting through the
    logger the sink uses is actually deliverable to *a* handler (checked here
    with a dedicated, test-local handler -- deterministic regardless of
    whichever earlier test in the session first imported ``backend.main``
    and thus already claimed the one-time ``logging.basicConfig`` call and
    its stdout stream reference, which makes asserting against *that specific*
    stream order-dependent and unsuitable for a shared test session); and
    (2) the logger actually propagates up to a configured root handler
    (``test_importing_the_app_configures_a_root_log_handler_at_or_below_info``
    proves part 2; ``propagate`` defaults to ``True`` and nothing in this
    codebase sets it, so both together prove delivery end to end)."""

    import backend.main  # noqa: F401  (ensure logging is configured at least once)

    logger = logging.getLogger("backend.agents.v2.telemetry")
    assert logger.propagate is True

    records: list[str] = []

    class _CollectingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _CollectingHandler()
    logger.addHandler(handler)
    try:
        sink = StructuredLogSink()
        trace = TraceContext.create()
        event = TelemetryEvent(
            name="agent_run.started",
            trace=trace,
            component=TraceComponent.RUNTIME,
            occurred_at=datetime.now(UTC),
            attributes={"terminal_status": "COMPLETED"},
        )
        sink.emit(event)
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    assert "agent_run.started" in records[0]
    assert trace.trace_id in records[0]
    assert trace.agent_run_id in records[0]
