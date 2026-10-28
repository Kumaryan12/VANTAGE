"""Linux-only hostile-operation probe, executed in a disposable non-root test container."""

import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from app.documents.extract import extract
from app.documents.sandbox import confine


def main():
    from pypdf import PdfReader  # Preload trusted imports before confinement.

    assert PdfReader
    expected = Path(sys.argv[1]).read_bytes()
    # Match the supervisor: a fresh private native temporary file, not a host bind-mount inode.
    temporary = tempfile.mkdtemp(prefix="vantage-isolation-")
    path = Path(temporary) / "input.pdf"
    path.write_bytes(expected)
    blocked = {}
    target = Path(tempfile.gettempdir()) / "vantage-isolation-probe-new-file"
    isolation = confine(path, required=True)
    checks = {
        "network_socket": lambda: socket.socket(),
        "other_document": lambda: Path("/probe/other.pdf").read_bytes(),
        "secrets_file": lambda: Path("/probe/credential-canary").read_bytes(),
        "proc_environment": lambda: Path("/proc/self/environ").read_bytes(),
        "filesystem_write": lambda: target.write_bytes(b"forbidden"),
        "subprocess": lambda: subprocess.run(["/usr/bin/true"], check=True),
    }
    for name, operation in checks.items():
        try:
            operation()
        except (PermissionError, OSError):
            blocked[name] = True
        else:
            blocked[name] = False
    assert all(blocked.values()), blocked
    assert path.read_bytes() == expected
    parsed = extract(str(path))
    assert parsed["pages"] and "SYNTHETIC" in parsed["pages"][0]["text"]
    print(
        json.dumps(
            {
                "isolation": isolation,
                "blocked": blocked,
                "parse_valid_pdf": True,
                "uid": os.getuid(),
            }
        )
    )


if __name__ == "__main__":
    main()
