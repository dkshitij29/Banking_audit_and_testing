"""Rebuild the policy wording corpus from corpus/manifest.csv.

    uv run python -m corpus.fetch

Downloads each document into corpus/pdfs/<document_id>.pdf (gitignored) and
checks it against the manifest's sha256. A file already present with the right
hash is left alone. A hash mismatch means the insurer has changed the document:
the file is kept as <document_id>.new.pdf for inspection, and every rule in
corpus/mapping.yaml must be re-checked against it before the manifest is updated.

The PDFs are third-party documents: never commit them (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent
MANIFEST = CORPUS / "manifest.csv"
PDFS = CORPUS / "pdfs"
USER_AGENT = "claims-benchmark/0.1 (research corpus fetch - one request per document)"
"""Says who we are and why. No semicolon: at least one insurer's site answers 400 to a
User-Agent containing one, and a research fetcher should not have to pretend to be curl."""


def read_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(row: dict[str, str], out: Path = PDFS, timeout: float = 60) -> str:
    """Make sure one document is present and unchanged. Returns what happened."""
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{row['document_id']}.pdf"
    if target.exists() and sha256(target.read_bytes()) == row["sha256"]:
        return "present"
    request = urllib.request.Request(row["source_url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if sha256(data) != row["sha256"]:
        changed = out / f"{row['document_id']}.new.pdf"
        changed.write_bytes(data)
        return f"CHANGED: saved as {changed.name}; re-check corpus/mapping.yaml before updating the manifest"
    target.write_bytes(data)
    return "downloaded"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=PDFS)
    args = parser.parse_args(argv)
    failed = False
    for row in read_manifest():
        try:
            status = fetch(row, args.out)
        except OSError as error:  # network errors included
            status, failed = f"FAILED: {error}", True
        failed |= status.startswith("CHANGED")
        print(f"{row['document_id']}: {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
