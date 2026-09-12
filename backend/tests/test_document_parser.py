"""PDF, DOCX and TXT parsing, validation and failure messages."""

from __future__ import annotations

import pytest

from app.services.document_parser import (
    DocumentParseError,
    extract_document,
    validate_upload,
)
from tests.conftest import STRONG_RESUME


def test_parses_text_pdf(text_pdf_bytes: bytes) -> None:
    document = extract_document("resume.pdf", text_pdf_bytes, "application/pdf")
    assert document.page_count == 1
    assert "Dana Whitfield" in document.text
    assert "PostgreSQL" in document.text


def test_parses_docx_including_table_cells(docx_bytes: bytes) -> None:
    document = extract_document(
        "resume.docx",
        docx_bytes,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert "RESTful backend services" in document.text
    # Content laid out in a table must still be extracted.
    assert "Bachelor of Science in Computer Science" in document.text


def test_parses_txt_with_utf8_and_latin1() -> None:
    utf8 = extract_document("resume.txt", STRONG_RESUME.encode("utf-8"), "text/plain")
    assert "Backend Engineer" in utf8.text

    latin1 = extract_document(
        "resume.txt", "Café backend engineer with Python and Docker.".encode("latin-1") + b"\n" * 2 + b"More than forty characters of text here.", "text/plain"
    )
    assert "backend engineer" in latin1.text.lower()


def test_empty_file_is_rejected() -> None:
    with pytest.raises(DocumentParseError) as error:
        extract_document("empty.txt", b"", "text/plain")
    assert error.value.reason_code == "empty_file"


def test_whitespace_only_document_is_rejected() -> None:
    with pytest.raises(DocumentParseError) as error:
        extract_document("blank.txt", b"   \n\n   \t  \n", "text/plain")
    assert error.value.reason_code == "empty_document"


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(DocumentParseError) as error:
        extract_document("resume.pages", b"some content here that is long enough", None)
    assert error.value.reason_code == "unsupported_extension"


def test_oversized_file_is_rejected() -> None:
    from app.config import MAX_FILE_SIZE_BYTES

    with pytest.raises(DocumentParseError) as error:
        validate_upload("big.txt", b"x" * (MAX_FILE_SIZE_BYTES + 1), "text/plain")
    assert error.value.reason_code == "file_too_large"


def test_image_only_pdf_gives_a_clear_error(image_only_pdf_bytes: bytes) -> None:
    with pytest.raises(DocumentParseError) as error:
        extract_document("scan.pdf", image_only_pdf_bytes, "application/pdf")
    assert error.value.reason_code == "image_only_pdf"
    assert "scanned or image-only" in error.value.message


def test_corrupt_pdf_gives_a_clear_error() -> None:
    with pytest.raises(DocumentParseError) as error:
        extract_document("broken.pdf", b"%PDF-1.4 this is not really a pdf file at all", "application/pdf")
    assert error.value.reason_code in {"corrupt_pdf", "image_only_pdf"}


def test_unexpected_mime_type_does_not_block_parsing() -> None:
    document = extract_document("resume.txt", STRONG_RESUME.encode("utf-8"), "application/msword")
    assert "Python" in document.text
