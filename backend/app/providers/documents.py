"""No external links, macros, embedded objects or document instructions are executed."""

import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Protocol

from defusedxml import ElementTree
from pypdf import PdfReader

MAX_TEXT = 200000
MAX_XML = 8 * 1024 * 1024


class DocumentError(ValueError):
    pass


def validate_container(data: bytes, suffix: str):
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentError("The file is not a valid PDF.")
        return
    if suffix != ".docx" or not data.startswith(b"PK"):
        raise DocumentError("Upload a PDF or DOCX document.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            items = archive.infolist()
            names = [entry.filename for entry in items]
            if len(items) > 1000 or len(names) != len(set(names)):
                raise DocumentError("The DOCX archive has too many or duplicate entries.")
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise DocumentError("The upload is not a Word DOCX document.")
            if sum(entry.file_size for entry in items) > 50 * 1024 * 1024:
                raise DocumentError("The expanded document exceeds the safety limit.")
            for entry in items:
                name = entry.filename.lower()
                if (
                    entry.flag_bits & 1
                    or ".." in name.split("/")
                    or "\\" in name
                    or name.startswith("/")
                    or "vbaproject" in name
                    or name.startswith("word/embeddings/")
                ):
                    raise DocumentError(
                        "Encrypted, embedded or macro-enabled content is unsupported."
                    )
                if entry.file_size > MAX_XML or entry.file_size / max(1, entry.compress_size) > 200:
                    raise DocumentError("Document compression exceeds the safety limit.")
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise DocumentError("The DOCX archive is damaged or unsupported.") from exc


class DocumentExtractor(Protocol):
    def extract(self, path: Path) -> str: ...


def extract_local(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DocumentError(
            "The uploaded document could not be read from storage. Please try again or upload it again."
        ) from exc
    validate_container(data, path.suffix)
    if path.suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError(
                "Password-protected PDFs are not supported. Upload an unlocked copy."
            )
        if len(reader.pages) > 50:
            raise DocumentError("Documents must have at most 50 pages.")
        root = reader.trailer["/Root"]
        # A GoTo open action only selects a location within the PDF. Many plain
        # exports include one; it is not executed while extracting text.
        open_action = root.get("/OpenAction")
        if hasattr(open_action, "get_object"):
            open_action = open_action.get_object()
        safe_open_action = (
            open_action is None
            or (
                hasattr(open_action, "keys")
                and set(open_action.keys()) == {"/S", "/D"}
                and open_action.get("/S") == "/GoTo"
            )
        )
        if not safe_open_action or "/AA" in root or "/AcroForm" in root:
            raise DocumentError("Active or form PDF content is unsupported. Export a plain PDF.")
        names = root.get("/Names", {})
        if hasattr(names, "get_object"):
            names = names.get_object()
        if "/EmbeddedFiles" in names or "/JavaScript" in names:
            raise DocumentError("PDF scripts and embedded files are unsupported.")
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > MAX_TEXT:
                raise DocumentError("Extracted document text exceeds the limit.")
        text = "\n".join(parts)
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            parts = []
            names = ["word/document.xml"] + sorted(
                name
                for name in archive.namelist()
                if re.fullmatch(r"word/(header|footer)\d+\.xml", name)
            )
            for name in names:
                with archive.open(name) as source:
                    xml = source.read(MAX_XML + 1)
                if len(xml) > MAX_XML:
                    raise DocumentError("Document XML exceeds the safety limit.")
                root = ElementTree.fromstring(xml)
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                for paragraph in root.iter(ns + "p"):
                    parts.append("".join(node.text or "" for node in paragraph.iter(ns + "t")))
            text = "\n".join(parts)
    text = "\n".join(re.sub(r"[\t \xa0]+", " ", line).strip() for line in text.splitlines())
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32).strip()
    if len(text) > MAX_TEXT or any(len(line) > 2000 for line in text.splitlines()):
        raise DocumentError("Document text is too large or lacks readable line breaks.")
    if len(text) < 20:
        raise DocumentError(
            "No readable text found. Scanned PDFs need OCR; upload a text PDF or DOCX."
        )
    return text


class IsolatedDocumentExtractor:
    def extract(self, path: Path) -> str:
        # Child runs without application/database/provider secrets and has a hard deadline.
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
        }
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(path)],
                capture_output=True,
                timeout=25,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise DocumentError(
                "Document extraction timed out. Try a simpler text document."
            ) from exc
        if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
            raise DocumentError(
                "Document could not be safely extracted. Try exporting a plain PDF or DOCX."
            )
        payload = json.loads(result.stdout)
        if "error" in payload:
            raise DocumentError(payload["error"])
        return payload["text"]


if __name__ == "__main__":
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    try:
        value = {"text": extract_local(Path(sys.argv[1]))}
    except DocumentError as error:
        value = {"error": str(error)}
    except Exception:
        value = {"error": "Document is damaged or contains unsupported content. Export a new copy."}
    sys.stdout.buffer.write(json.dumps(value).encode("utf-8"))
