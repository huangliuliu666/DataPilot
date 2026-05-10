from __future__ import annotations

from typing import Any

from memory.memory_store import MemoryStore


class TextExampleRetriever:

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    def retrieve(self, *, db_id: str, question: str, top_k: int) -> list[dict[str, Any]]:
        records = self.memory.retrieve_question_sql(db_id=db_id, question=question, top_k=top_k)
        results = []
        for record in records:
            results.append({**record, "example_source": "A_text_same_workspace"})
        return results
