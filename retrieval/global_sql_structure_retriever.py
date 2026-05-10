from __future__ import annotations

from pathlib import Path
from typing import Any

from sql_retriever import GraphRetriever


class GlobalSQLStructureRetriever:

    def __init__(
        self,
        *,
        weights_path: str | Path,
        vocab_path: str | Path,
        dataset_path: str | Path,
        device: str = "cuda",
    ) -> None:
        self.weights_path = Path(weights_path)
        self.vocab_path = Path(vocab_path)
        self.dataset_path = Path(dataset_path)
        for path, name in [
            (self.weights_path, "GNN weights"),
            (self.vocab_path, "GNN vocab"),
            (self.dataset_path, "GNN global dataset"),
        ]:
            if not path.exists():
                raise FileNotFoundError(f"{name} file not found: {path}")
        self.retriever = GraphRetriever(
            model_weights=str(self.weights_path),
            vocab_path=str(self.vocab_path),
            dataset_path=str(self.dataset_path),
            device=device,
        )

    def retrieve(self, *, query_sql: str, top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []
        raw = self.retriever.search_similar_sql(query_sql, top_k=top_k)
        if isinstance(raw, str):
            raise ValueError(raw)
        results: list[dict[str, Any]] = []
        for item in raw:
            results.append(
                {
                    "db_id": item.get("db_id"),
                    "question": item.get("question", ""),
                    "sql": item.get("sql", ""),
                    "score": item.get("score"),
                    "example_source": "C_global_sql_structure",
                    "metadata": {"source": "global_gnn_dataset", "note": "structure_only"},
                }
            )
        return results
