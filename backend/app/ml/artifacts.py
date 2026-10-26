"""Private checksummed text/JSON artifacts. Never deserialize Python pickle."""

import hashlib
import io
import platform
import re
import zipfile
from importlib.metadata import version
from pathlib import Path

from app.core.config import ROOT, settings
from app.core.errors import AppError


def runtime_versions():
    commit = settings().build_commit or None
    head = ROOT / ".git/HEAD"
    if not commit and head.is_file():
        raw = head.read_text().strip()
        if re.fullmatch(r"[a-f0-9]{40}", raw):
            commit = raw
        elif raw.startswith("ref: "):
            ref = raw[5:]
            path = ROOT / ".git" / ref
            if (
                ".." not in Path(ref).parts
                and path.is_relative_to(ROOT / ".git")
                and path.is_file()
            ):
                candidate = path.read_text().strip()
                if re.fullmatch(r"[a-f0-9]{40}", candidate):
                    commit = candidate
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_commit": commit,
        **{name: version(name) for name in ("numpy", "pandas", "scipy", "arch", "lightgbm")},
    }


def writer(experiment_id):
    root = Path(settings().model_artifact_dir).resolve()

    def write(kind, name, content):
        if not re.fullmatch(r"[a-z0-9-]+", kind) or not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
            raise AppError("ARTIFACT_NAME", "Invalid generated artifact name.")
        data = content.encode("utf-8")
        if len(data) > 10 * 1024 * 1024:
            raise AppError("ARTIFACT_SIZE", "Individual model artifact exceeds 10 MB.")
        path = root / experiment_id / kind / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        return {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }

    return write


def read_artifact(manifest):
    root = Path(settings().model_artifact_dir).resolve()
    path = (root / manifest["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AppError("ARTIFACT_UNAVAILABLE", "Saved model artifact is unavailable.", 409)
    data = path.read_bytes()
    if len(data) > 10 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise AppError("ARTIFACT_INTEGRITY", "Saved model artifact failed its checksum.", 409)
    return data


def artifact_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        for manifest in files:
            output.writestr(Path(manifest["path"]).name, read_artifact(manifest))
    return buffer.getvalue()
