"""Turns a case into its document bundle: the only part of the repo that uses an LLM.

The model writes prose only. Every fact a document states is placed by code from
case.json (render/documents.py). Nothing here ever touches a gold label.
"""

RENDER_VERSION = "0.1.0"
