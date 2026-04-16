from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pypdf
import trafilatura

from kimi_cli.utils.logging import logger

if TYPE_CHECKING:
    from kosong.message import Message


class URLConverter:
    @staticmethod
    def convert_url_to_md(url: str) -> str:
        """Convert a URL to markdown using trafilatura."""
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                result = trafilatura.extract(downloaded)
                return result or ""
        except Exception:
            logger.exception("Failed to convert URL: {url}", url=url)
        return ""


class PDFConverter:
    @staticmethod
    def convert_pdf_to_md(path: Path) -> str:
        """Convert a PDF to markdown using pypdf."""
        try:
            reader = pypdf.PdfReader(path)
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
        except Exception:
            logger.exception("Failed to convert PDF: {path}", path=path)
        return ""


class SessionConverter:
    @staticmethod
    def convert_session_to_md(messages: list[Message]) -> str:
        """Convert a list of messages to markdown."""
        formatted_messages = []
        for msg in messages:
            content = msg.extract_text()
            formatted_messages.append(f"### {msg.role}\n{content}")
        return "\n\n".join(formatted_messages)

    @staticmethod
    def convert_session_to_jsonl(messages: list[Message]) -> str:
        """Convert a list of messages to JSONL."""
        if not messages:
            return ""
        return "\n".join(msg.model_dump_json(exclude_none=True) for msg in messages) + "\n"
