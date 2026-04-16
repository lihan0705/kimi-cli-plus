from pathlib import Path
from uuid import uuid4

from kimi_cli.knowledge.models import Category, DocumentStatus
from kimi_cli.knowledge.paths import (
    ensure_kb_dirs,
    generate_slug,
    get_document_dir,
    get_kb_root,
)


def test_get_kb_root_default(monkeypatch):
    monkeypatch.delenv("KIMI_KB_ROOT", raising=False)
    root = get_kb_root()
    assert root == Path.home() / ".kimi" / "knowledge"


def test_get_kb_root_env(monkeypatch):
    monkeypatch.setenv("KIMI_KB_ROOT", "/tmp/kb")
    root = get_kb_root()
    assert root == Path("/tmp/kb")


def test_ensure_kb_dirs(tmp_path):
    ensure_kb_dirs(tmp_path)
    assert (tmp_path / "raw").is_dir()
    assert (tmp_path / "knowledge").is_dir()
    assert (tmp_path / "wiki").is_dir()
    assert (tmp_path / "log_archive").is_dir()

    for cat in Category:
        assert (tmp_path / "knowledge" / cat.value).is_dir()


def test_generate_slug():
    doc_id = uuid4()
    slug = generate_slug("Test Title 123!", doc_id)
    # Format: YYYYMMDD_test-title-123_shortid
    assert len(slug.split("_")) == 3
    assert "test-title-123" in slug
    assert str(doc_id)[:8] in slug


def test_get_document_dir_raw(tmp_path):
    root = tmp_path
    slug = "20231027_test_12345678"
    # For raw status, it should be in the raw/ directory
    path = get_document_dir(root, slug, DocumentStatus.raw)
    assert path == root / "raw" / slug


def test_get_document_dir_classified(tmp_path):
    root = tmp_path
    slug = "20231027_test_12345678"
    # For classified status, it should be in knowledge/<category>/<subcategory>/
    path = get_document_dir(root, slug, DocumentStatus.classified, Category.Concept, "Sub Category")
    assert path == root / "knowledge" / "concept" / "sub-category" / slug


def test_get_document_dir_no_subcategory(tmp_path):
    root = tmp_path
    slug = "20231027_test_12345678"
    path = get_document_dir(root, slug, DocumentStatus.reviewed, Category.Concept)
    assert path == root / "knowledge" / "concept" / slug
