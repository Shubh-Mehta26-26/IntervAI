"""Assign an account role from a trusted local operator shell."""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionFactory, engine
from app.models.identity import User


async def main(email: str, role: str):
    async with SessionFactory() as db:
        user = await db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
        if user is None:
            raise SystemExit("No existing account matches that email.")
        user.role = role
        await db.commit()
        print(f"Updated account role: {user.id} → {role}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email of an existing account")
    parser.add_argument("role", choices=("candidate", "recruiter", "admin"))
    args = parser.parse_args()
    asyncio.run(
        main(args.email, args.role),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )
