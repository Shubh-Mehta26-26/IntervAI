"""HTTP only: the API and worker never launch candidate code or compilers."""

import httpx

from app.core.config import get_settings
from app.schemas.coding import ExecutionResult


class ExecutionError(Exception):
    pass


class ExecutionProvider:
    def __init__(self):
        self.url = get_settings().code_runner_url.rstrip("/")
        key = get_settings().code_runner_api_key
        self.headers = (
            {"Authorization": "Bearer " + key.get_secret_value()}
            if key and key.get_secret_value()
            else {}
        )

    async def readiness(self):
        try:
            async with httpx.AsyncClient(timeout=6, headers=self.headers) as client:
                response = await client.get(self.url + "/health")
                response.raise_for_status()
                value = response.json()
                if value.get("ready") is not True or set(value.get("languages", [])) != {
                    "python",
                    "cpp",
                    "java",
                }:
                    raise ExecutionError("Sandbox is not ready")
                return value
        except httpx.HTTPError as exc:
            raise ExecutionError("Sandbox is unavailable") from exc

    async def execute(self, payload):
        try:
            async with httpx.AsyncClient(timeout=100, headers=self.headers) as client:
                response = await client.post(self.url + "/execute", json=payload)
                response.raise_for_status()
                value = ExecutionResult.model_validate(response.json()).model_dump()
                total, passed = value.get("tests_total"), value.get("tests_passed")
                if (
                    type(total) is not int
                    or type(passed) is not int
                    or total != len(payload["tests"])
                    or not 0 <= passed <= total
                ):
                    raise ExecutionError("Invalid sandbox test counts")
                return value
        except (httpx.HTTPError, ValueError) as exc:
            raise ExecutionError("Sandbox execution failed") from exc

    async def cancel(self, identifier):
        try:
            async with httpx.AsyncClient(timeout=6, headers=self.headers) as client:
                response = await client.post(self.url + "/cancel", json={"id": str(identifier)})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExecutionError("Sandbox cancellation is pending") from exc
