"""Telemetry rieng cho pipeline VLM (dem thuoc trong anh + doi chieu don thuoc,
backend/services/photo_verification/). THEM 2026-08-22.

Tach HOAN TOAN khoi backend/services/telemetry.py (RAG chatbot, viec cua
thanh vien khac) thay vi tham so hoa lai TelemetryService da co:
  - _LOCAL_TRACE_BUFFER cua telemetry.py la bien module-level dung chung -
    neu tai su dung, trace VLM se lan vao danh sach ma /admin/rag/* dang
    doc, pha dung yeu cau "khong dung vao RAG".
  - VLM can Langfuse client RIENG (project rieng, key rieng - xem
    settings.vlm_langfuse_* trong backend/config.py), khac han client cua
    RAG (settings.langfuse_*).

Tai dung TraceRecord/ObservationRecord/mask_sensitive_data/hash_identifier tu
telemetry.py (import, KHONG dinh nghia lai) - cac ham/dataclass do da du
tong quat cho ca 2 pipeline, chi khac o CHO chua state (buffer, client)."""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.config import get_settings
from backend.services.telemetry import (
    ObservationRecord,
    TraceRecord,
    hash_identifier,
    mask_sensitive_data,
)

logger = logging.getLogger(__name__)

# Ring buffer RIENG cho VLM - khong dung chung voi _LOCAL_TRACE_BUFFER cua
# telemetry.py, cung ly do da giai thich o docstring module.
_MAX_VLM_LOCAL_TRACES = 200
_VLM_LOCAL_TRACE_BUFFER: list[TraceRecord] = []


class VlmTelemetryService:
    """Ban sao cau truc cua TelemetryService (telemetry.py) nhung state hoan
    toan doc lap - xem docstring module ve ly do khong dung chung class."""

    def __init__(self):
        self.settings = get_settings()
        self._langfuse_client = None
        self._init_langfuse()

    def _init_langfuse(self):
        if (
            not self.settings.vlm_langfuse_enabled
            or not self.settings.vlm_langfuse_public_key
            or not self.settings.vlm_langfuse_secret_key
        ):
            return

        try:
            from langfuse import Langfuse

            self._langfuse_client = Langfuse(
                public_key=self.settings.vlm_langfuse_public_key,
                secret_key=self.settings.vlm_langfuse_secret_key,
                host=self.settings.vlm_langfuse_host,
            )
            logger.info("VLM Langfuse telemetry client initialized successfully.")
        except ImportError:
            logger.info("Langfuse SDK not installed; VLM telemetry stays local-only.")
        except Exception as exc:
            logger.warning(f"Failed to initialize VLM Langfuse client: {exc}")

    def is_langfuse_connected(self) -> bool:
        """True khi Langfuse client da init THANH CONG (qua try/except o
        tren) - khong phai chi "co set bien moi truong". Key sai/host khong
        reachable luc khoi dong van tra False du VLM_LANGFUSE_ENABLED=true."""
        return self._langfuse_client is not None

    def create_trace(
        self,
        trace_id: str,
        name: str = "vlm.count_and_match",
        session_id: str | None = None,
        user_id: str | None = None,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> TraceRecord:
        base_meta = {"environment": self.settings.app_env}
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
            tags=tags or ["vlm", "photo-verification"],
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

        _VLM_LOCAL_TRACE_BUFFER.append(trace)
        if len(_VLM_LOCAL_TRACE_BUFFER) > _MAX_VLM_LOCAL_TRACES:
            _VLM_LOCAL_TRACE_BUFFER.pop(0)

        if self._langfuse_client:
            try:
                metadata = {
                    **(trace.metadata or {}),
                    "tags": trace.tags,
                    "user_id": trace.user_id,
                    "session_id": trace.session_id,
                }
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
                        model=obs.model if obs_type == "generation" else None,
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
                logger.warning(f"Error shipping VLM trace to Langfuse: {e}")

    def flush(self):
        if self._langfuse_client:
            try:
                self._langfuse_client.flush()
            except Exception:
                pass


# Singleton instance
_vlm_telemetry_instance: VlmTelemetryService | None = None


def get_vlm_telemetry_service() -> VlmTelemetryService:
    global _vlm_telemetry_instance
    if _vlm_telemetry_instance is None:
        _vlm_telemetry_instance = VlmTelemetryService()
    return _vlm_telemetry_instance


def get_vlm_local_traces() -> list[TraceRecord]:
    """Retrieve in-memory VLM trace records for monitoring endpoints."""
    return list(_VLM_LOCAL_TRACE_BUFFER)
