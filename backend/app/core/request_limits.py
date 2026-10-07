import asyncio
import re

from starlette.responses import JSONResponse


class RequestSizeLimit:
    """Bound JSON request bodies before FastAPI parses them, including chunked requests."""

    def __init__(self, app, max_bytes=65536):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT"}:
            await self.app(scope, receive, send)
            return
        chunks = []
        size = 0
        upload = scope["method"] == "POST" and re.fullmatch(
            r"/api/v1/resumes(?:/[a-fA-F0-9-]{36}/replace)?", scope["path"]
        )
        audio = scope["method"] == "POST" and re.fullmatch(
            r"/api/v1/interviews/[a-fA-F0-9-]{36}/voice/transcribe", scope["path"]
        )
        vision = scope["method"] == "POST" and re.fullmatch(
            r"/api/v1/interviews/[a-fA-F0-9-]{36}/vision/frame", scope["path"]
        )
        limit = (131072 + 8192 if vision else 6 * 1024 * 1024 + 65536 if audio else
                 10 * 1024 * 1024 + 65536 if upload else self.max_bytes)
        try:
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > limit:
                        response = JSONResponse(
                            {
                                "error": {
                                    "code": "request_too_large",
                                    "message": "Request exceeds the upload limit."
                                    if upload or audio or vision
                                    else "Request exceeds the 64 KB limit.",
                                }
                            },
                            status_code=413,
                        )
                        await response(scope, receive, send)
                        return
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            response = JSONResponse(
                {"error": {"code": "request_timeout", "message": "Request upload timed out."}},
                status_code=408,
            )
            await response(scope, receive, send)
            return
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
