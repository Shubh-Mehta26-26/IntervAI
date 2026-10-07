"""Create or remove the narrowly labelled local browser-QA account and resume fixture."""

import io
import sys
import zipfile
from pathlib import Path

import httpx
import psycopg
from app.core.config import get_settings
from sqlalchemy.engine import make_url

EMAIL = "phase3-browser-qa@example.com"
DISPLAY_NAME = "Development Phase 3 Browser QA"
PASSWORD = "Temporary-Phase3-browser-passphrase-42"
ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "storage" / "phase3-browser-qa.docx"


def cleanup():
    dsn = (
        make_url(get_settings().database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "DELETE FROM users WHERE email=%s AND display_name=%s", (EMAIL, DISPLAY_NAME)
        )
        connection.commit()
    DOCUMENT.unlink(missing_ok=True)


def document():
    text = """Development Phase 3 Browser QA
Email: phase3-browser-qa@example.com
Location: Pune, India
Summary
Backend engineer focused on dependable web systems.
Experience
Backend Engineer at Development Example
Built REST APIs using Python and FastAPI. Deployed PostgreSQL services with Docker.
Skills
Python, FastAPI, PostgreSQL, Docker, Kubernetes
Projects
Created an interview preparation workspace using React and Next.js.
Education
MCA, Development QA Institute
"""
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + f"<w:body>{paragraphs}</w:body></w:document>",
        )
    DOCUMENT.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENT.write_bytes(output.getvalue())


if len(sys.argv) != 2 or sys.argv[1] not in {"setup", "cleanup"}:
    raise SystemExit("Usage: browser_qa.py setup|cleanup")
cleanup()
if sys.argv[1] == "setup":
    document()
    base = "http://localhost:3001"
    response = httpx.post(
        base + "/api/v1/auth/register",
        headers={"Origin": base},
        json={"email": EMAIL, "password": PASSWORD, "display_name": DISPLAY_NAME},
        timeout=20,
    )
    response.raise_for_status()
    print(str(DOCUMENT))
else:
    print("Phase 3 browser QA data removed.")
