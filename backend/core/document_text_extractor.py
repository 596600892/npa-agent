from __future__ import annotations

from pathlib import Path

from .document_ingestion import DocumentExtractionError, IngestedDocument, ingest_document


def extract_document_text(path: str | Path, filename: str | None = None) -> IngestedDocument:
    return ingest_document(path, filename)
