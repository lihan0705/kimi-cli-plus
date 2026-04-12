import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from kosong.message import Message
from kimi_cli.knowledge import URLConverter, PDFConverter, SessionConverter

def test_url_converter_success():
    url = "https://example.com"
    mock_content = "This is a test content."
    with patch("trafilatura.fetch_url") as mock_fetch, \
         patch("trafilatura.extract") as mock_extract:
        mock_fetch.return_value = "<html>...</html>"
        mock_extract.return_value = mock_content
        
        result = URLConverter.convert_url_to_md(url)
        assert result == mock_content
        mock_fetch.assert_called_once_with(url)

def test_url_converter_failure():
    url = "https://invalid.url"
    with patch("trafilatura.fetch_url") as mock_fetch:
        mock_fetch.return_value = None
        result = URLConverter.convert_url_to_md(url)
        assert result == ""

def test_pdf_converter_success(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()
    
    with patch("pypdf.PdfReader") as mock_reader:
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 content."
        
        mock_instance = mock_reader.return_value
        mock_instance.pages = [mock_page1, mock_page2]
        
        result = PDFConverter.convert_pdf_to_md(pdf_path)
        assert result == "Page 1 content.\nPage 2 content."

def test_pdf_converter_failure():
    with patch("pypdf.PdfReader", side_effect=Exception("Failed to read PDF")):
        result = PDFConverter.convert_pdf_to_md(Path("nonexistent.pdf"))
        assert result == ""

def test_session_converter():
    messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there! How can I help?"),
        Message(role="user", content="Tell me a joke."),
    ]
    
    expected_output = "### user\nHello\n\n### assistant\nHi there! How can I help?\n\n### user\nTell me a joke."
    result = SessionConverter.convert_session_to_md(messages)
    assert result == expected_output
