"""
file_extractor.py — EduCheck Academic Check
─────────────────────────────────────────────
Extract plain text from uploaded files:
  · .txt  — read directly
  · .docx — python-docx
  · .pdf  — pdfplumber (text-based) with PyMuPDF fallback

All functions return a plain str.  Raise HTTPException on bad input
so FastAPI can return a clean 400 to the frontend.
"""

from __future__ import annotations

import io
from typing import Optional

from fastapi import HTTPException, UploadFile

# ── Optional library imports with clear error messages ───────────────────────

def _require(pkg: str, install: str):
    """Lazy import helper — raises 500 with install hint if missing."""
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail=f"Server missing '{pkg}'. Run: pip install {install}",
        )


# ── Allowed extensions ────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
MAX_FILE_SIZE_MB   = 10


# ── Per-format extractors ─────────────────────────────────────────────────────

def _extract_txt(data: bytes) -> str:
    """Decode bytes as UTF-8 (fallback latin-1)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _extract_docx(data: bytes) -> str:
    """Extract text from a .docx file using python-docx."""
    docx = _require("docx", "python-docx")
    doc  = docx.Document(io.BytesIO(data))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    # Also grab text from tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text.strip())
    return "\n".join(paragraphs)


def _extract_pdf(data: bytes) -> str:
    """
    Extract text from a PDF.
    Tries pdfplumber first (better layout), falls back to PyMuPDF (fitz).
    """
    # Primary: pdfplumber
    try:
        pdfplumber = _require("pdfplumber", "pdfplumber")
        pages = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text.strip())
        if pages:
            return "\n".join(pages)
    except HTTPException:
        pass   # pdfplumber not installed — try fallback
    except Exception:
        pass   # corrupt page or layout issue — try fallback

    # Fallback: PyMuPDF
    try:
        fitz = _require("fitz", "pymupdf")
        pages = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                pages.append(page.get_text())
        return "\n".join(pages)
    except HTTPException:
        raise HTTPException(
            500,
            "PDF extraction requires pdfplumber or pymupdf. "
            "Run: pip install pdfplumber   or   pip install pymupdf",
        )


# ── Public entry point ────────────────────────────────────────────────────────

async def extract_text_from_upload(file: UploadFile) -> str:
    """
    Read an UploadFile and return its plain-text content.

    Raises HTTPException (400/413/415/500) on bad input.
    """
    import os

    # Extension check
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: .txt, .pdf, .docx",
        )

    # Read bytes
    data = await file.read()

    # Size guard
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {MAX_FILE_SIZE_MB} MB.",
        )

    if not data:
        raise HTTPException(400, "Uploaded file is empty.")

    # Extract
    if ext == ".txt":
        text = _extract_txt(data)
    elif ext == ".docx":
        text = _extract_docx(data)
    elif ext == ".pdf":
        text = _extract_pdf(data)
    else:
        raise HTTPException(415, f"Unsupported file type: {ext}")

    text = text.strip()
    if len(text) < 50:
        raise HTTPException(
            400,
            f"Extracted text is too short ({len(text)} chars). "
            "The file may be scanned/image-only or nearly empty.",
        )

    return text