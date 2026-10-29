from pathlib import Path

import pytest
from app.core.config import ROOT, Settings
from app.providers.documents import DocumentError, IsolatedDocumentExtractor, extract_local
from app.providers.storage import LocalStorage


@pytest.mark.parametrize("working_directory", [".", "backend"])
def test_relative_storage_root_is_independent_of_working_directory(monkeypatch, working_directory):
    monkeypatch.chdir(ROOT / working_directory)
    settings = Settings(storage_root=Path("storage"))
    monkeypatch.setattr("app.providers.storage.get_settings", lambda: settings)
    store = LocalStorage()
    assert store.root == (ROOT / "storage").resolve()
    assert store.path("a" * 32 + ".pdf").parent == store.root


def test_absolute_storage_root_is_preserved(tmp_path):
    assert Settings(storage_root=tmp_path).storage_root == tmp_path.resolve()


@pytest.mark.parametrize("extractor", [extract_local, IsolatedDocumentExtractor().extract])
def test_missing_upload_is_reported_as_storage_failure(tmp_path, extractor):
    with pytest.raises(DocumentError, match="could not be read from storage"):
        extractor(tmp_path / "missing.pdf")
