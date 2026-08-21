"""Run BUILD-2's live OpenAI smoke tests without printing any secret values."""

import json
import sys
from pathlib import Path

# Support the documented direct invocation from the repository root without
# relying on a caller's PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agents.v2.model_gateway import MissingModelCredentialError, OpenAIModelGateway  # noqa: E402
from backend.config import get_settings  # noqa: E402


def main() -> int:
    gateway = OpenAIModelGateway.from_settings(get_settings())
    try:
        results = gateway.smoke_all()
    except MissingModelCredentialError as error:
        print(json.dumps({"status": "BLOCKED", "required_credentials": str(error).split(", ")}))
        return 2

    payload = [
        {
            "role": result.role,
            "model": result.model,
            "passed": result.passed,
            "latency_ms": round(result.latency_ms, 2),
            "input_tokens": result.usage.input_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
            "output_tokens": result.usage.output_tokens,
            "request_id": result.request_id,
            "error": result.error,
        }
        for result in results
    ]
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
