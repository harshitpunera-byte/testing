import io
import os
import re

import pdfplumber

try:
    import pymupdf4llm
except Exception:
    pymupdf4llm = None

try:
    from docling.document_converter import DocumentConverter
    from docling_core.types.io import DocumentStream
except Exception:
    DocumentConverter = None
    DocumentStream = None

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except Exception:
    pytesseract = None
    Image = None

from app.models.document_pages import ExtractedDocument, PageText


converter = DocumentConverter() if DocumentConverter else None


def _to_page_records(text_parts: list[str]) -> list[PageText]:
    pages = []

    for index, text in enumerate(text_parts, start=1):
        clean_text = (text or "").strip()
        if clean_text:
            pages.append(PageText(page=index, text=clean_text))

    return pages


def flatten_pages(pages: list[PageText]) -> str:
    return "\n\n".join(page.text for page in pages if page.text).strip()


def _flattened_length(pages: list[PageText]) -> int:
    return len(flatten_pages(pages))


def _has_meaningful_text(pages: list[PageText], minimum_chars: int = 50) -> bool:
    if not pages:
        return False

    meaningful_pages = 0
    total_chars = 0
    
    for page in pages:
        text = page.text or ""
        total_chars += len(text)
        
        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = re.sub(
            r"==>\s*picture\s*\[[^\]]+\]\s*intentionally omitted\s*<==",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"picture\s+\d+\s+x\s+\d+\s+intentionally omitted",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"[^A-Za-z\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        if len(normalized) <= 20: 
            continue
            
        tokens = normalized.split()
        meaningful_tokens = [
            token
            for token in tokens
            if len(token) > 2 and token.lower() not in {"picture", "intentionally", "omitted"}
        ]
        
        if len(meaningful_tokens) >= 8:
            meaningful_pages += 1
            
    if total_chars <= minimum_chars:
        return False
        
    if len(pages) > 3 and (meaningful_pages / len(pages)) < 0.3:
        return False
        
    return meaningful_pages > 0


def _page_number_from_chunk(page_chunk: dict, fallback_page: int) -> int:
    metadata = page_chunk.get("metadata") or {}

    for value in (
        metadata.get("page_number"),
        page_chunk.get("page_number"),
        metadata.get("page"),
        page_chunk.get("page"),
    ):
        try:
            page_number = int(value)
        except (TypeError, ValueError):
            continue

        if page_number > 0:
            return page_number

    return fallback_page


def _extract_with_pymupdf4llm_pages(pdf_bytes: bytes, document_name: str) -> list[PageText]:
    if not fitz or pymupdf4llm is None:
        return []

    pdf_doc = None

    try:
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        try:
            markdown_output = pymupdf4llm.to_markdown(
                pdf_doc,
                page_chunks=True,
                filename=document_name,
                use_ocr=False,
            )
        except TypeError:
            markdown_output = pymupdf4llm.to_markdown(
                pdf_doc,
                page_chunks=True,
                filename=document_name,
            )

        if isinstance(markdown_output, str):
            return _to_page_records([markdown_output])

        pages = []
        for index, chunk in enumerate(markdown_output or [], start=1):
            if not isinstance(chunk, dict):
                continue

            text = (chunk.get("text") or "").strip()
            if not text:
                continue

            pages.append(
                PageText(
                    page=_page_number_from_chunk(chunk, index),
                    text=text,
                )
            )

        return pages
    except Exception as e:
        print("PyMuPDF4LLM extraction failed:", str(e))
        return []
    finally:
        if pdf_doc is not None:
            pdf_doc.close()


def _extract_with_docling_pages(pdf_bytes: bytes, document_name: str) -> list[PageText]:
    if converter is None or DocumentStream is None:
        return []

    try:
        result = converter.convert(
            DocumentStream(
                name=document_name or "document.pdf",
                stream=io.BytesIO(pdf_bytes),
            )
        )
        text = result.document.export_to_markdown()
        return _to_page_records([text])
    except Exception as e:
        print("Docling extraction failed:", str(e))
        return []


def _extract_with_pdfplumber_pages(pdf_bytes: bytes) -> list[PageText]:
    try:
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

        return _to_page_records(text_parts)
    except Exception as e:
        print("pdfplumber extraction failed:", str(e))
        return []


def _extract_with_pymupdf_pages(pdf_bytes: bytes) -> list[PageText]:
    if not fitz:
        return []

    try:
        text_parts = []
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page in pdf_doc:
            text_parts.append(page.get_text("text") or "")

        return _to_page_records(text_parts)
    except Exception as e:
        print("PyMuPDF extraction failed:", str(e))
        return []


def _extract_with_pymupdf_family_pages(pdf_bytes: bytes, document_name: str) -> tuple[list[PageText], str | None]:
    llm_pages = _extract_with_pymupdf4llm_pages(pdf_bytes, document_name)
    if _flattened_length(llm_pages) > 50:
        return llm_pages, "pymupdf4llm"

    plain_pages = _extract_with_pymupdf_pages(pdf_bytes)
    if _flattened_length(plain_pages) >= _flattened_length(llm_pages):
        return plain_pages, "pymupdf"

    return llm_pages, "pymupdf4llm"


def _extract_with_ocr_pages(pdf_bytes: bytes) -> list[PageText]:
    if not fitz or not pytesseract or not Image:
        print("OCR dependencies not available")
        return []

    try:
        text_parts = []
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(pdf_doc)):
            page = pdf_doc.load_page(page_num)
            pix = page.get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            page_text = pytesseract.image_to_string(img) or ""
            text_parts.append(page_text)

        return _to_page_records(text_parts)
    except Exception as e:
        print("OCR extraction failed:", str(e))
        return []


def load_pdf_pages(file_obj_or_bytes, document_name: str | None = None) -> ExtractedDocument:
    try:
        if isinstance(file_obj_or_bytes, bytes):
            pdf_bytes = file_obj_or_bytes
        else:
            file_obj_or_bytes.seek(0)
            pdf_bytes = file_obj_or_bytes.read()

        resolved_name = document_name or os.path.basename(
            getattr(file_obj_or_bytes, "name", "") or ""
        ) or "document.pdf"

        if not pdf_bytes:
            return ExtractedDocument(pages=[], backend=None)

        pymupdf_pages, pymupdf_backend = _extract_with_pymupdf_family_pages(pdf_bytes, resolved_name)
        if _has_meaningful_text(pymupdf_pages) and pymupdf_backend:
            print(f"Text extracted using {pymupdf_backend}")
            return ExtractedDocument(pages=pymupdf_pages, backend=pymupdf_backend)

        extraction_pipeline = [
            ("pdfplumber", _extract_with_pdfplumber_pages),
            ("docling", lambda raw_bytes: _extract_with_docling_pages(raw_bytes, resolved_name)),
            ("ocr", _extract_with_ocr_pages),
        ]

        for backend, extractor in extraction_pipeline:
            pages = extractor(pdf_bytes)
            if _has_meaningful_text(pages):
                print(f"Text extracted using {backend}")
                return ExtractedDocument(pages=pages, backend=backend)

        return ExtractedDocument(pages=[], backend=None)
    except Exception as e:
        print("load_pdf_pages failed:", str(e))
        return ExtractedDocument(pages=[], backend=None)


def load_pdf(file_obj):
    extracted = load_pdf_pages(file_obj)
    return flatten_pages(extracted.pages)
