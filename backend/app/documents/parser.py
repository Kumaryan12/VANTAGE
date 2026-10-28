"""Bounded parent supervisor; the child receives one private PDF and no application secrets."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app.core.config import ROOT, settings
from app.core.errors import AppError


def parse(content):
    if not isinstance(content, bytes) or not 1 <= len(content) <= 5 * 1024 * 1024:
        raise AppError("DOCUMENT_SIZE", "PDF exceeds the parser input budget.", 413)
    with tempfile.TemporaryDirectory(prefix="vantage-pdf-") as temporary:
        root = Path(temporary)
        path = root / "input.pdf"
        path.write_bytes(content)
        path.chmod(0o600)
        with (root / "bounded-output.json").open("w+b") as output:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "app.documents.extract", str(path)],
                    cwd=root,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "PYTHONPATH": str(ROOT / "backend"),
                        "PYTHONIOENCODING": "utf-8",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "VANTAGE_SANDBOX_REQUIRED": "1"
                        if settings().document_sandbox_required
                        else "0",
                    },
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                    close_fds=True,
                )
            except subprocess.TimeoutExpired:
                raise AppError(
                    "PDF_TIMEOUT",
                    "Document extraction exceeded its isolated execution budget.",
                    504,
                ) from None
            output.seek(0)
            data = output.read(4_000_001)
        if result.returncode != 0 or len(data) > 4_000_000:
            raise AppError(
                "PDF_EXTRACTION",
                "PDF could not be safely extracted; required isolation, malformed/active/encrypted/oversized or image-only content may be unsupported.",
            )
        try:
            parsed = json.loads(data)["result"]
        except (ValueError, KeyError, TypeError):
            raise AppError(
                "PDF_EXTRACTION", "Isolated parser returned an invalid bounded result."
            ) from None
        if parsed.get("input_hash") != hashlib.sha256(content).hexdigest():
            raise AppError(
                "PDF_INTEGRITY",
                "Isolated parser input hash differs from the authorized original.",
                409,
            )
        return parsed
