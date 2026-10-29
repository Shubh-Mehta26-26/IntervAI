"""Native development launcher; uses a psycopg-compatible Windows event loop."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the IntervAI API locally.")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("INTERVAI_API_PORT", "8000"))
    )
    args = parser.parse_args()
    server = uvicorn.Server(
        uvicorn.Config("app.main:app", host="127.0.0.1", port=args.port)
    )
    asyncio.run(
        server.serve(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
