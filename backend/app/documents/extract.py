"""Isolated parser entry point. Input is a server-generated private path, never a command."""

import hashlib
import json
import os
import sys

from pypdf import PdfReader

MAX_PAGES = 100
MAX_TEXT = 500_000


def extract(path):
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are unsupported.")
    root = reader.root_object
    if any(key in root for key in ("/OpenAction", "/AA")):
        raise ValueError("Active PDF actions are unsupported.")
    names = root.get("/Names", {})
    if hasattr(names, "get_object"):
        names = names.get_object()
    if any(key in names for key in ("/JavaScript", "/EmbeddedFiles")):
        raise ValueError("Active content and embedded files are unsupported.")
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        raise ValueError("PDF must contain between 1 and 100 pages.")
    result = []
    total = 0
    for i, page in enumerate(reader.pages):
        if "/AA" in page:
            raise ValueError("Page actions are unsupported.")
        contents = page.get_contents()
        if contents and len(contents.get_data()) > 8_000_000:
            raise ValueError("Decompressed page content exceeds the parsing limit.")
        text = (page.extract_text() or "").replace("\x00", "").strip()
        total += len(text)
        if len(text) > 50_000 or total > MAX_TEXT:
            raise ValueError("Extracted text exceeds the document/page limit.")
        result.append({"page": i + 1, "text": text})
    if total < 20:
        raise ValueError(
            "No usable text found. Scanned/image-only PDFs require separately verified OCR, which is not implemented."
        )
    metadata = reader.metadata or {}
    return {
        "pages": result,
        "pdf_metadata": {
            key: str(metadata[key])[:300]
            for key in ("/Title", "/Author", "/CreationDate")
            if key in metadata
        },
        "table_structure": "Unverified text extraction; no reliable table cells, units or arithmetic inferred.",
    }


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (4_000_000, 4_000_000))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        # Import trusted parser dependencies before applying irreversible kernel restrictions.
        from pathlib import Path

        from app.documents.sandbox import confine

        input_hash = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
        isolation = confine(sys.argv[1], required=os.environ.get("VANTAGE_SANDBOX_REQUIRED") == "1")
        result = extract(sys.argv[1])
        result.update(input_hash=input_hash, isolation=isolation)
        print(json.dumps({"result": result}, ensure_ascii=True))
    except Exception:
        # Never return raw parser errors/embedded text to logs or the API.
        print(
            json.dumps(
                {
                    "error": "PDF could not be safely extracted; encrypted, active, malformed, oversized or image-only input may be unsupported."
                }
            )
        )
        sys.exit(2)
