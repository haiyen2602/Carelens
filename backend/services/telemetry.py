"""Telemetry service abstraction for LLM & RAG Observability.
Conforms to docs/langfuse_rag_admin_monitoring_spec.md §1.4, §3, §4, §5, §20.

Provides standard trace hierarchy:
  rag.chat                         [root]
  |-- query.normalize              [span]
  |-- query.embedding              [span]
  |-- retrieval.vector_search      [retriever]
  |-- retrieval.rerank             [span]
  |-- context.build                [span]
  |-- generation.answer            [generation]
  |-- safety.validate              [span]
  +-- response.finalize            [span]
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Sensitive keywords / PII markers for basic masking (§20)
_REDACT_KEYS = {"password", "secret", "token", "phone", "email", "cc", "ssn"}


def mask_sensitive_data(obj: Any) -> Any:
    """Recursively mask sensitive values from metadata and observation logs."""
    if isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            if any(s in k.lower() for s in _REDACT_KEYS) and isinstance(v, str):
                masked[k] = "[REDACTED]"
            else:
                masked[k] = mask_sensitive_data(v)
        return masked
    elif isinstance(obj, list):
        return [mask_sensitive_data(item) for item in obj]
    return obj


def hash_identifier(identifier: str | None) -> str:
    """Create opaque identifier to protect patient privacy in telemetry."""
    if not identifier:
        return "anonymous"
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:16]


@dataclass
class ObservationRecord:
    name: str
    type: str  # span, retriever, generation, event
    start_time: float
    end_time: float = 0.0
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    level: str = "DEFAULT"  # DEFAULT, WARNING, ERROR
    status_message: str | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    cost: float | None = None

    @property
    def duration_ms(self) -> float:
        if self.end_time > 0:
            return round((self.end_time - self.start_time) * 1000, 2)
        return 0.0


@dataclass
class TraceRecord:
    id: str
    name: str
    session_id: str
    user_id: str
    start_time: float
    end_time: float = 0.0
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    observations: list[ObservationRecord] = field(default_factory=list)
    scores: dict[str, float | int | str | bool] = field(default_factory=dict)
    status: str = "success"

    @property
    def duration_ms(self) -> float:
        if self.end_time > 0:
            return round((self.end_time - self.start_time) * 1000, 2)
        return 0.0


# In-memory ring buffer of recent traces for fast local monitoring / API fallback
_MAX_LOCAL_TRACES = 200
_LOCAL_TRACE_BUFFER: list[TraceRecord] = []


class TelemetryService:
    """Abstraction layer for Langfuse and internal telemetry recording."""

    def __init__(self):
        self.settings = get_settings()
        self._langfuse_client = None
        self._init_langfuse()

    def _init_langfuse(self):
        if not self.settings.langfuse_enabled or not self.settings.langfuse_public_key or not self.settings.langfuse_secret_key:
            return

        try:
            # Attempt to import and initialize Langfuse SDK if installed
            from langfuse import Langfuse

            self._langfuse_client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
            logger.info("Langfuse telemetry client initialized successfully.")
        except ImportError:
            logger.info("Langfuse SDK not installed; using local structured trace logging.")
        except Exception as exc:
            logger.warning(f"Failed to initialize Langfuse client: {exc}")

    def create_trace(
        self,
        trace_id: str,
        name: str = "rag.chat",
        session_id: str | None = None,
        user_id: str | None = None,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> TraceRecord:
        base_meta = {
            "environment": self.settings.app_env,
            "release": "backend-1.0.0",
            "model": self.settings.model_name,
            "embedding_model": self.settings.embedding_model,
            "prompt_version": self.settings.rag_prompt_version,
            "retriever_version": self.settings.rag_retriever_version,
            "index_version": self.settings.rag_index_version,
        }
        if metadata:
            base_meta.update(mask_sensitive_data(metadata))

        trace = TraceRecord(
            id=trace_id,
            name=name,
            session_id=session_id or f"session_{hash_identifier(user_id)}",
            user_id=hash_identifier(user_id),
            start_time=time.time(),
            input=mask_sensitive_data(input_data),
            metadata=base_meta,
            tags=tags or ["rag", "medication-chat"],
        )
        return trace

    def start_observation(
        self,
        trace: TraceRecord,
        name: str,
        obs_type: str = "span",
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> ObservationRecord:
        obs = ObservationRecord(
            name=name,
            type=obs_type,
            start_time=time.time(),
            input=mask_sensitive_data(input_data),
            metadata=mask_sensitive_data(metadata or {}),
        )
        trace.observations.append(obs)
        return obs

    def end_observation(
        self,
        obs: ObservationRecord,
        output_data: Any = None,
        level: str = "DEFAULT",
        status_message: str | None = None,
        usage: dict[str, int] | None = None,
        cost: float | None = None,
    ):
        if obs.end_time <= 0:
            obs.end_time = time.time()
        obs.output = mask_sensitive_data(output_data)
        obs.level = level
        obs.status_message = status_message
        obs.usage = usage
        obs.cost = cost

    def record_score(
        self,
        trace: TraceRecord,
        name: str,
        value: float | int | str | bool,
        comment: str | None = None,
    ):
        trace.scores[name] = value

    def finalize_trace(
        self,
        trace: TraceRecord,
        output_data: Any = None,
        status: str = "success",
    ):
        trace.end_time = time.time()
        trace.output = mask_sensitive_data(output_data)
        trace.status = status

        # Save to local buffer
        _LOCAL_TRACE_BUFFER.append(trace)
        if len(_LOCAL_TRACE_BUFFER) > _MAX_LOCAL_TRACES:
            _LOCAL_TRACE_BUFFER.pop(0)

        # Ship to Langfuse if available
        if self._langfuse_client:
            try:
                # Langfuse SDK v4+ observation / span tree
                metadata = {**(trace.metadata or {}), "tags": trace.tags, "user_id": trace.user_id, "session_id": trace.session_id}
                root_span = self._langfuse_client.start_observation(
                    name=trace.name,
                    as_type="span",
                    input=trace.input,
                    metadata=metadata,
                )
                
                for obs in trace.observations:
                    obs_type = "generation" if obs.type == "generation" else "span"
                    child = root_span.start_observation(
                        name=obs.name,
                        as_type=obs_type,
                        input=obs.input,
                        output=obs.output,
                        metadata=obs.metadata,
                        model=obs.model or self.settings.model_name if obs_type == "generation" else None,
                        level=obs.level if obs.level in ("DEBUG", "DEFAULT", "WARNING", "ERROR") else "DEFAULT",
                        status_message=obs.status_message,
                    )
                    child.end()

                for score_name, score_val in trace.scores.items():
                    root_span.score_trace(
                        name=score_name,
                        value=float(score_val) if isinstance(score_val, (int, float)) else 1.0,
                        comment=str(score_val) if not isinstance(score_val, (int, float)) else None,
                    )

                root_span.update(output=trace.output)
                root_span.end()
                self._langfuse_client.flush()
            except Exception as e:
                logger.warning(f"Error shipping trace to Langfuse: {e}")

    def flush(self):
        if self._langfuse_client:
            try:
                self._langfuse_client.flush()
            except Exception:
                pass


# Singleton instance
_telemetry_instance: TelemetryService | None = None


def get_telemetry_service() -> TelemetryService:
    global _telemetry_instance
    if _telemetry_instance is None:
        _telemetry_instance = TelemetryService()
    return _telemetry_instance


def get_local_traces() -> list[TraceRecord]:
    """Retrieve in-memory trace records for monitoring endpoints."""
    return list(_LOCAL_TRACE_BUFFER)
