"""Bundle ingestion — safe unzip, file typing, size limits, grouping."""

from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import UploadFile

from agent.aoc4.models import DocumentInfo, DocType


@dataclass
class Bundle:
    """Unzipped and classified files."""
    request_id: str
    files_dir: Path
    documents: list[DocumentInfo] = field(default_factory=list)
    total_size_bytes: int = 0
    total_pages: int = 0


class BundleError(Exception):
    pass


def safe_unzip(
    uploads: list[UploadFile],
    output_base: Path,
    *,
    max_files: int = 40,
    max_total_mb: int = 150,
    max_zip_depth: int = 1,
) -> Bundle:
    """Process uploaded files: unzip safely, enumerate contents.

    Returns a ``Bundle`` with all files extracted under ``output_base/<request_id>/``.
    Callers must delete the directory after use.
    """
    request_id = uuid.uuid4().hex[:12]
    files_dir = output_base / request_id
    files_dir.mkdir(parents=True, exist_ok=True)

    flat_files: list[Path] = []
    total_size = 0

    for upload in uploads:
        content = upload.file.read()
        upload.file.seek(0)
        total_size += len(content)

        if total_size > max_total_mb * 1024 * 1024:
            shutil.rmtree(files_dir, ignore_errors=True)
            raise BundleError(f"BUNDLE_TOO_LARGE: {total_size / 1e6:.1f} MB exceeds {max_total_mb} MB limit")

        ext = (upload.filename or "").lower()

        if ext.endswith(".zip"):
            extracted = _extract_zip(
                content, files_dir,
                max_files=max_files - len(flat_files),
                max_depth=max_zip_depth,
            )
            flat_files.extend(extracted)
        else:
            dest = files_dir / (upload.filename or f"file_{len(flat_files)}")
            dest.write_bytes(content)
            flat_files.append(dest)

    if len(flat_files) > max_files:
        shutil.rmtree(files_dir, ignore_errors=True)
        raise BundleError(f"Too many files: {len(flat_files)} > {max_files}")

    # Assign doc_ids
    docs = []
    for i, path in enumerate(flat_files):
        doc_id = f"d{i + 1:02d}"
        docs.append(DocumentInfo(
            doc_id=doc_id,
            filename=path.name,
            doc_type=DocType.OTHER,
            confidence=0.0,
        ))

    return Bundle(
        request_id=request_id,
        files_dir=files_dir,
        documents=docs,
        total_size_bytes=total_size,
    )


def cleanup_bundle(bundle: Bundle):
    """Delete the temp extraction directory."""
    if bundle.files_dir.exists():
        shutil.rmtree(bundle.files_dir, ignore_errors=True)


def _extract_zip(
    content: bytes,
    target: Path,
    *,
    max_files: int,
    max_depth: int,
) -> list[Path]:
    """Extract zip safely — no zip-slip, no symlinks."""
    # Write bytes to temp file first
    temp_zip = target / "__temp__.zip"
    temp_zip.write_bytes(content)

    try:
        zf = zipfile.ZipFile(temp_zip)
    except zipfile.BadZipFile:
        raise BundleError("INVALID_ZIP")

    # Pre-validate all names
    for info in zf.infolist():
        name = info.filename
        # Zip-slip check
        if name.startswith("/") or ".." in name:
            zf.close()
            raise BundleError(f"UNSAFE_ZIP_ENTRY: {name!r}")
        # Symlink check
        if info.create_system == 3 and (info.external_attr >> 16) & 0o170000 == 0o120000:
            zf.close()
            raise BundleError(f"SYMLINK_IN_ZIP: {name!r}")
        # Depth check
        parts = name.split("/")
        if len(parts) > max_depth + 1:
            zf.close()
            raise BundleError(f"ZIP_TOO_DEEP: {name!r}")

    # Extract
    extracted: list[Path] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        dest = (target / info.filename).resolve()
        # Double-check after resolve
        if not str(dest).startswith(str(target.resolve())):
            zf.close()
            raise BundleError(f"UNSAFE_ZIP_ENTRY (after resolve): {info.filename!r}")

        if len(extracted) >= max_files:
            zf.close()
            raise BundleError(f"Too many files in zip (>{max_files})")

        with zf.open(info) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
        extracted.append(dest)

    zf.close()
    # Remove temp zip
    (target / "__temp__.zip").unlink(missing_ok=True)
    return extracted
