import re
from typing import Optional
from rank_bm25 import BM25Okapi
from agent.models.filing import FilingSection


class BM25Retriever:
    """BM25-based retrieval over filing text sections."""

    def __init__(self, sections: list[FilingSection]):
        self.sections = sections
        self._tokenized: list[list[str]] = []
        self._bm25: Optional[BM25Okapi] = None

        if sections:
            for section in sections:
                chunked = self._chunk_section(section)
                self._tokenized.extend([self._tokenize_text(c.lower()) for c in chunked])

            if self._tokenized:
                self._bm25 = BM25Okapi(self._tokenized)

    @staticmethod
    def _tokenize_text(text: str) -> list[str]:
        words = text.split()
        return [re.sub(r'[^\w]', '', w) for w in words if re.sub(r'[^\w]', '', w)]

    @staticmethod
    def _chunk_section(section: FilingSection, chunk_size: int = 200, overlap: int = 30) -> list[str]:
        words = section.text.split()
        if len(words) <= chunk_size:
            return [section.text]

        chunks: list[str] = []
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start += chunk_size - overlap
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float, str]]:
        """Search filing text. Returns [(section_heading, score, text_snippet), ...]."""
        if not self._bm25:
            return []

        query_tokens = self._tokenize_text(query.lower())
        scores = self._bm25.get_scores(query_tokens)

        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

        results: list[tuple[str, float, str]] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            snippet = self._tokenized[idx]
            text_snippet = " ".join(snippet)
            heading = self._find_section_heading(idx)
            results.append((heading, float(score), text_snippet[:500]))
            if len(results) >= top_k:
                break

        return results

    def _find_section_heading(self, chunk_index: int) -> str:
        """Approximate which section a chunk belongs to."""
        chunks_per_section = max(1, len(self._tokenized) // max(len(self.sections), 1))
        section_idx = min(chunk_index // chunks_per_section, len(self.sections) - 1)
        if 0 <= section_idx < len(self.sections):
            return self.sections[section_idx].heading
        return "Unknown Section"

    @staticmethod
    def build_index(sections: list[FilingSection]) -> "BM25Retriever":
        return BM25Retriever(sections)
