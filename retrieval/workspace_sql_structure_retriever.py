from __future__ import annotations

from typing import Any

import torch

from memory.memory_store import MemoryStore
from retrieval.sql_structure_encoder import SQLStructureEncoder


class WorkspaceSQLStructureRetriever:

    def __init__(self, *, memory: MemoryStore, encoder: SQLStructureEncoder) -> None:
        self.memory = memory
        self.encoder = encoder

    def retrieve(self, *, db_id: str, query_sql: str, top_k: int) -> list[dict[str, Any]]:
        records = [r for r in self.memory.list_records("question_sql") if r.get("db_id") == db_id and str(r.get("sql", "")).strip()]
        if not records or top_k <= 0:
            return []

        query_vec = self.encoder.encode(query_sql)
        vectors = []
        valid_records = []
        for record in records:
            try:
                vectors.append(self.encoder.encode(record["sql"]))
                valid_records.append(record)
            except Exception:
                                                                                                        
                                                                                                                
                continue
        if not vectors:
            return []
        matrix = torch.stack(vectors, dim=0)
        scores = self.encoder.cosine(query_vec, matrix)
        k = min(int(top_k), len(valid_records))
        top_scores, top_indices = torch.topk(scores, k=k)
        results: list[dict[str, Any]] = []
        for score, idx in zip(top_scores.tolist(), top_indices.tolist()):
            record = valid_records[int(idx)]
            results.append({**record, "score": float(score), "example_source": "B_sql_structure_same_workspace"})
        return results
