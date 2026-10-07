"""Live configured-provider check with synthetic inputs and no candidate records.

Run from the repository root with PYTHONPATH=backend. Never prints credentials,
provider response bodies, request headers, or exception tracebacks.
"""

import asyncio
import json
import time

import httpx
from app.providers.llm import LLMError, get_provider, provider_status
from app.schemas.coding import ComplexityAnalysis
from app.schemas.interviews import GroundedEvaluationResult, PlanResult, QuestionResult


async def main() -> int:
    ready, provider_name, model, _ = provider_status()
    print(json.dumps({"provider": provider_name, "model": model, "configured": ready}))
    if not ready:
        print("Missing provider-specific key or model configuration.")
        return 2
    provider = get_provider()
    checks = [
        ("plan", PlanResult, "Plan one Python topic with one question, difficulty 2."),
        ("question", QuestionResult, "Ask one technical Python list-versus-tuple question."),
        (
            "evaluation",
            GroundedEvaluationResult,
            (
                "Evaluate this synthetic answer: Lists are mutable; tuples are immutable. "
                "Question: How do lists and tuples differ? No retrieved knowledge is provided. "
                "Use empty knowledge_evidence and grounding_status insufficient; invent no citations."
            ),
        ),
        (
            "complexity",
            ComplexityAnalysis,
            (
                "Estimate complexity of this Python source: def total(values): return sum(values). "
                "values is a list of n integers, n <= 10000. These are qualitative estimates, "
                "not measured runtime or memory. Give concise reasoning and edge cases."
            ),
        ),
    ]
    for name, schema, prompt in checks:
        started = time.monotonic()
        try:
            await provider.structured(
                system="You are checking an interview application's structured output. Be concise.",
                user=prompt,
                schema=schema,
                name=name,
            )
        except LLMError as exc:
            result = {"check": name, "status": "FAILED", "error": exc.code}
            cause = exc.__cause__
            if isinstance(cause, httpx.HTTPStatusError):
                result["http_status"] = cause.response.status_code
                # Allowlisted diagnostic identifiers only; never dump Google's error text.
                try:
                    status = cause.response.json().get("error", {}).get("status")
                    if status in {
                        "INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED",
                        "NOT_FOUND", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL",
                    }:
                        result["provider_status"] = status
                except (ValueError, AttributeError, TypeError):
                    pass
            elif isinstance(cause, httpx.RequestError):
                result["transport_error"] = type(cause).__name__
            print(json.dumps(result))
            return 1
        print(json.dumps({"check": name, "status": "PASSED", "seconds": round(time.monotonic() - started, 2)}))
    print("Live provider smoke passed: plan, question, evaluation, coding complexity; typed output validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
