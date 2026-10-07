import re
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.core.config import get_settings

MAX_FILE_BYTES = 10 * 1024 * 1024


class Storage(Protocol):
    def put(self, data: bytes, suffix: str) -> str: ...
    def path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self):
        self.root = get_settings().storage_root.resolve()

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}\.(pdf|docx)", key):
            raise ValueError("Invalid storage reference")
        target = (self.root / key).resolve()
        if target.parent != self.root:
            raise ValueError("Invalid storage path")
        return target

    def put(self, data: bytes, suffix: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        key = uuid4().hex + suffix
        with self.path(key).open("xb") as output:
            output.write(data)
        return key

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def storage() -> Storage:
    return LocalStorage()
