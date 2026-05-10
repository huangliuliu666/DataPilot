from __future__ import annotations

from pathlib import Path
from typing import Any

from config import Config
from memory.memory_store import MemoryStore
from retrieval.global_sql_structure_retriever import GlobalSQLStructureRetriever
from retrieval.sql_structure_encoder import SQLStructureEncoder
from retrieval.text_example_retriever import TextExampleRetriever
from retrieval.workspace_sql_structure_retriever import WorkspaceSQLStructureRetriever


class HybridExampleRetriever:

    def __init__(self, *, memory: MemoryStore, gnn_device: str = "cuda") -> None:
        self.memory = memory
        self.gnn_device = gnn_device
        self._encoder: SQLStructureEncoder | None = None
        self._global_retriever: GlobalSQLStructureRetriever | None = None

    def retrieve(
        self,
        *,
        db_id: str,
        question: str,
        draft_sql: str | None,
        total_top_k: int = 5,
        text_top_k: int = 3,
        workspace_structure_top_k: int = 2,
        use_sql_structure_retrieval: bool = True,
        use_global_structure_examples: bool = True,
    ) -> dict[str, Any]:
        total_top_k = max(0, int(total_top_k))
        a_examples = self._dedupe_examples(
            TextExampleRetriever(self.memory).retrieve(db_id=db_id, question=question, top_k=min(text_top_k, total_top_k))
        )

        b_examples: list[dict[str, Any]] = []
        c_examples: list[dict[str, Any]] = []
        if use_sql_structure_retrieval and total_top_k > len(a_examples):
            if not draft_sql or not str(draft_sql).strip():
                raise ValueError("SQL-structure retrieval is enabled, but draft_sql is empty.")
            encoder = self._get_encoder()
            remaining_for_b = min(workspace_structure_top_k, total_top_k - len(a_examples))
            raw_b = WorkspaceSQLStructureRetriever(memory=self.memory, encoder=encoder).retrieve(
                db_id=db_id,
                query_sql=draft_sql,
                top_k=max(remaining_for_b * 3, remaining_for_b),
            )
            b_examples = self._dedupe_examples(raw_b, exclude=a_examples)[:remaining_for_b]

            remaining_for_c = total_top_k - len(a_examples) - len(b_examples)
            if remaining_for_c > 0 and use_global_structure_examples:
                raw_c = self._get_global_retriever().retrieve(query_sql=draft_sql, top_k=max(remaining_for_c * 3, remaining_for_c))
                c_examples = self._dedupe_examples(raw_c, exclude=[*a_examples, *b_examples])[:remaining_for_c]

        return {
            "A_text_examples": a_examples,
            "B_workspace_sql_structure_examples": b_examples,
            "C_global_sql_structure_examples": c_examples,
            "examples_str": self.format_examples(a_examples, b_examples, c_examples),
            "counts": {"A": len(a_examples), "B": len(b_examples), "C": len(c_examples)},
        }

    @classmethod
    def _dedupe_examples(
        cls,
        examples: list[dict[str, Any]],
        exclude: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        seen = {cls._example_key(item) for item in (exclude or [])}
        result: list[dict[str, Any]] = []
        for item in examples:
            key = cls._example_key(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _example_key(item: dict[str, Any]) -> str:
        question = str(item.get("question", "")).strip().lower()
        sql = str(item.get("sql") or item.get("content") or "").strip().lower()
        sql = " ".join(sql.rstrip(";").split())
        return question + "|" + sql

    def _get_encoder(self) -> SQLStructureEncoder:
        if self._encoder is None:
            self._encoder = SQLStructureEncoder(
                vocab_path=Config.GNN_VOCAB_PATH,
                weights_path=Config.GNN_WEIGHTS_PATH,
                device=self.gnn_device,
            )
        return self._encoder

    def _get_global_retriever(self) -> GlobalSQLStructureRetriever:
        if self._global_retriever is None:
            self._global_retriever = GlobalSQLStructureRetriever(
                weights_path=Config.GNN_WEIGHTS_PATH,
                vocab_path=Config.GNN_VOCAB_PATH,
                dataset_path=Config.GNN_DATASET_PATH,
                device=self.gnn_device,
            )
        return self._global_retriever

    @staticmethod
    def format_examples(a_examples: list[dict[str, Any]], b_examples: list[dict[str, Any]], c_examples: list[dict[str, Any]]) -> str:
        sections: list[str] = []
        if a_examples:
            sections.append(
                "## Current Database Semantic Examples (A)\n"
                "These examples come from the same database and are selected by natural-language similarity. "
                "You may learn table usage, column usage, join patterns, business formulas, and SQL style from them."
            )
            for i, item in enumerate(a_examples, 1):
                sections.append(HybridExampleRetriever._format_one(item, f"A{i}"))

        if b_examples:
            sections.append(
                "## Current Database SQL-Structure Examples (B)\n"
                "These examples come from the same database and are selected by SQL structure similarity to the draft SQL. "
                "You may learn SQL structure and current-database query patterns from them."
            )
            for i, item in enumerate(b_examples, 1):
                sections.append(HybridExampleRetriever._format_one(item, f"B{i}"))

        if c_examples:
            sections.append(
                "## Global SQL-Structure Examples (C)\n"
                "These examples may come from other databases and possibly another SQL dialect. "
                "Use them only for SQL structure. Do not copy their table names, column names, literal values, or business meanings."
            )
            for i, item in enumerate(c_examples, 1):
                sections.append(HybridExampleRetriever._format_one(item, f"C{i}"))

        return "\n\n".join(sections).strip() or "No valid examples found."

    @staticmethod
    def _format_one(item: dict[str, Any], label: str) -> str:
        score = item.get("score")
        score_text = f" | score={score:.4f}" if isinstance(score, (float, int)) else ""
        question = item.get("question") or "<question unavailable>"
        sql = item.get("sql") or item.get("content", "")
        return f"Example {label}{score_text}:\nQuestion: {question}\nSQL: {sql}"
