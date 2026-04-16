import os
import re
from datetime import datetime
from pathlib import Path
from uuid import UUID

from kimi_cli.knowledge.models import Category, DocumentStatus


def get_kb_root() -> Path:
    """Get the root directory for the knowledge base.

    Defaults to ~/.kimi/knowledge/, but can be overridden by the KIMI_KB_ROOT
    environment variable.
    """
    env_root = os.getenv("KIMI_KB_ROOT")
    if env_root:
        return Path(env_root)
    return Path.home() / ".kimi" / "knowledge"


def ensure_kb_dirs(root: Path) -> None:
    """Ensure all required knowledge base directories exist.

    Creates raw/, knowledge/, wiki/, and log_archive/ under root.
    Also creates category-specific subdirectories under knowledge/.
    """
    # Top level dirs
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "knowledge").mkdir(parents=True, exist_ok=True)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "log_archive").mkdir(parents=True, exist_ok=True)

    # Category dirs under knowledge/
    for cat in Category:
        (root / "knowledge" / cat.value).mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug (lowercase, alphanumeric, hyphens)."""
    text = text.lower()
    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Strip leading/trailing hyphens and multiple consecutive hyphens
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def generate_slug(title: str, document_id: UUID) -> str:
    """Generate a slug in the format {YYYYMMDD}_{Title_Slug}_{Short_ID}."""
    date_str = datetime.now().strftime("%Y%m%d")
    title_slug = _slugify(title)
    short_id = str(document_id)[:8]
    # Ensure slug is not empty if title is empty
    if not title_slug:
        title_slug = "untitled"
    return f"{date_str}_{title_slug}_{short_id}"


def get_document_dir(
    root: Path,
    slug: str,
    status: DocumentStatus,
    category: Category | None = None,
    subcategory: str | None = None,
) -> Path:
    """Get the correct directory path for a document based on its status and category.

    Each document lives in its own directory named after the slug.
    """
    if status == DocumentStatus.raw:
        return root / "raw" / slug

    base = root / "knowledge"
    if category:
        base = base / category.value
        if subcategory:
            base = base / _slugify(subcategory)

    return base / slug
