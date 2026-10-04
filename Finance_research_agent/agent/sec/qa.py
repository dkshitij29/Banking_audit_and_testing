from pydantic_ai import Agent, RunContext
from agent.sec.retriever import BM25Retriever
from agent.config import Settings


class FilingQAIgent:
    """RAG QA over SEC filing text with section citations."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._agent = Agent(
            settings.create_model(),
            instructions=self._get_instructions(),
        )

    async def ask(self, retriever: BM25Retriever, question: str) -> str:
        context_chunks = retriever.search(question, top_k=5)

        if not context_chunks:
            return "No relevant filing text found for this question."

        context_text = self._format_context(context_chunks)
        prompt = f"{context_text}\n\nQuestion: {question}"

        try:
            result = await self._agent.run(prompt)
            return result.output
        except Exception:
            return f"Could not generate answer for: {question}"

    def _format_context(self, chunks: list[tuple[str, float, str]]) -> str:
        parts: list[str] = ["SEC FILING EXCERPTS (for reference):\n"]
        for i, (heading, score, text) in enumerate(chunks, 1):
            parts.append(f"--- [{heading}] (relevance: {score:.2f}) ---")
            parts.append(text)
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _get_instructions() -> str:
        return (
            "You are a financial analyst answering questions based on SEC filing excerpts.\n"
            "Use ONLY the provided filing text to answer. If the text doesn't contain the answer, say so.\n"
            "Cite the section name when quoting or paraphrasing.\n"
            "Be concise and precise. Do not make up information not in the filing.\n"
            "Format: Provide a direct answer first, then supporting details with citations."
        )
