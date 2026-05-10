from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryStore:

    RECORD_FILES = {
        "ddl": "ddl_memory.json",
        "documentation": "documentation_memory.json",
        "question_sql": "question_sql_memory.json",
        "error_fix": "error_fix_memory.json",
    }

    def __init__(self, memory_dir: str | Path) -> None:
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_record_files()

    def _ensure_record_files(self) -> None:
        for filename in self.RECORD_FILES.values():
            path = self.memory_dir / filename
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)

    def train(
        self,
        *,
        db_id: str,
        ddl: str | None = None,
        documentation: str | None = None,
        question: str | None = None,
        sql: str | None = None,
        error_message: str | None = None,
        fix_rule: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        record_ids: list[str] = []

        if ddl is not None:
            record_ids.append(self.train_ddl(db_id=db_id, ddl=ddl, metadata=metadata))

        if documentation is not None:
            record_ids.append(
                self.train_documentation(
                    db_id=db_id,
                    documentation=documentation,
                    metadata=metadata,
                )
            )

        is_error_fix = error_message is not None or fix_rule is not None

        if is_error_fix:
            if not question or not sql or not error_message or not fix_rule:
                raise ValueError("训练 error-fix memory 必须同时提供 question、sql、error_message、fix_rule")
            record_ids.append(
                self.train_error_fix(
                    db_id=db_id,
                    question=question,
                    wrong_sql=sql,
                    error_message=error_message,
                    fix_rule=fix_rule,
                    metadata=metadata,
                )
            )
        elif question is not None or sql is not None:
            if not question or not sql:
                raise ValueError("question 和 sql 必须同时提供，才能训练 question-SQL pair")
            record_ids.append(
                self.train_question_sql(
                    db_id=db_id,
                    question=question,
                    sql=sql,
                    metadata=metadata,
                )
            )

        if not record_ids:
            raise ValueError("至少需要提供 ddl、documentation、question/sql 或 error-fix 信息之一")

        return record_ids


    def upsert_schema_ddl(
        self,
        *,
        db_id: str,
        ddl: str,
        schema_fingerprint: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not str(ddl).strip():
            raise ValueError("ddl 不能为空")

        records = self._load_records("ddl")
        now = datetime.now(timezone.utc).isoformat()
        target_source = "workspace_enriched_schema"
        merged_metadata = {
            **(metadata or {}),
            "source": target_source,
            "schema_fingerprint": schema_fingerprint,
        }

        for record in records:
            if record.get("db_id") == db_id and record.get("metadata", {}).get("source") == target_source:
                record["content"] = ddl
                record["metadata"] = merged_metadata
                record["updated_at"] = now
                self._save_records("ddl", records)
                return str(record["id"])

        record_id = str(uuid.uuid4())
        records.append(
            {
                "id": record_id,
                "created_at": now,
                "db_id": db_id,
                "type": "ddl",
                "content": ddl,
                "metadata": merged_metadata,
            }
        )
        self._save_records("ddl", records)
        return record_id

    def train_ddl(self, *, db_id: str, ddl: str, metadata: dict[str, Any] | None = None) -> str:
        if not str(ddl).strip():
            raise ValueError("ddl 不能为空")
        return self._append_record(
            "ddl",
            {
                "db_id": db_id,
                "type": "ddl",
                "content": ddl,
                "metadata": metadata or {},
            },
        )

    def train_documentation(
        self,
        *,
        db_id: str,
        documentation: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not str(documentation).strip():
            raise ValueError("documentation 不能为空")
        return self._append_record(
            "documentation",
            {
                "db_id": db_id,
                "type": "documentation",
                "content": documentation.strip(),
                "metadata": metadata or {},
            },
        )

    def train_question_sql(
        self,
        *,
        db_id: str,
        question: str,
        sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not str(question).strip():
            raise ValueError("question 不能为空")
        if not str(sql).strip():
            raise ValueError("sql 不能为空")
        clean_question = str(question).strip()
        clean_sql = self._normalize_sql(sql)
        return self._append_record(
            "question_sql",
            {
                "db_id": db_id,
                "type": "question_sql",
                "question": clean_question,
                "sql": clean_sql,
                "content": f"Question: {clean_question}\nSQL: {clean_sql}",
                "metadata": metadata or {},
            },
        )

    def train_error_fix(
        self,
        *,
        db_id: str,
        question: str,
        wrong_sql: str,
        error_message: str,
        fix_rule: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        for name, value in {
            "question": question,
            "wrong_sql": wrong_sql,
            "error_message": error_message,
            "fix_rule": fix_rule,
        }.items():
            if not str(value).strip():
                raise ValueError(f"{name} 不能为空")

        clean_question = str(question).strip()
        clean_wrong_sql = self._normalize_sql(wrong_sql)
        clean_error_message = str(error_message).strip()
        clean_fix_rule = str(fix_rule).strip()
        return self._append_record(
            "error_fix",
            {
                "db_id": db_id,
                "type": "error_fix",
                "question": clean_question,
                "wrong_sql": clean_wrong_sql,
                "error_message": clean_error_message,
                "fix_rule": clean_fix_rule,
                "content": (
                    f"Question: {clean_question}\n"
                    f"Wrong SQL: {clean_wrong_sql}\n"
                    f"Error: {clean_error_message}\n"
                    f"Fix rule: {clean_fix_rule}"
                ),
                "metadata": metadata or {},
            },
        )

    def retrieve_documentation(self, *, db_id: str, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        records = [r for r in self._load_records("documentation") if r.get("db_id") == db_id]
        return self._rank_records(records=records, query=question, top_k=top_k)

    def retrieve_question_sql(self, *, db_id: str, question: str, top_k: int = 3) -> list[dict[str, Any]]:
        records = [r for r in self._load_records("question_sql") if r.get("db_id") == db_id]
        return self._rank_records(records=records, query=question, top_k=top_k)

    def retrieve_error_fixes(self, *, db_id: str, question: str, top_k: int = 3) -> list[dict[str, Any]]:
        records = [r for r in self._load_records("error_fix") if r.get("db_id") == db_id]
        return self._rank_records(records=records, query=question, top_k=top_k)

    def format_documentation(self, docs: list[dict[str, Any]]) -> str:
        if not docs:
            return ""
        lines = []
        for i, item in enumerate(docs, 1):
            lines.append(f"Documentation {i}:\n{item.get('content', '')}")
        return "\n\n".join(lines)

    def format_question_sql_examples(self, examples: list[dict[str, Any]]) -> str:
        if not examples:
            return "No valid examples found."
        lines = []
        for i, item in enumerate(examples, 1):
            lines.append(
                f"Example {i}:\n"
                f"Question: {item.get('question', '')}\n"
                f"Evidence: {item.get('metadata', {}).get('evidence', '')}\n"
                f"SQL: {item.get('sql', '')}\n"
            )
        return "\n".join(lines)

    def format_error_fixes(self, fixes: list[dict[str, Any]]) -> str:
        if not fixes:
            return ""
        lines = []
        for i, item in enumerate(fixes, 1):
            lines.append(
                f"Error-Fix Example {i}:\n"
                f"Question: {item.get('question', '')}\n"
                f"Wrong SQL: {item.get('wrong_sql', '')}\n"
                f"Error: {item.get('error_message', '')}\n"
                f"Fix rule: {item.get('fix_rule', '')}"
            )
        return "\n\n".join(lines)

    def list_records(self, record_type: str | None = None) -> list[dict[str, Any]]:
        if record_type is not None:
            self._validate_record_type(record_type)
            return self._load_records(record_type)

        records: list[dict[str, Any]] = []
        for current_type in self.RECORD_FILES:
            records.extend(self._load_records(current_type))
        return records

    def delete_record(self, record_type: str, record_id: str, db_id: str | None = None) -> dict[str, Any]:
        self._validate_record_type(record_type)
        if not str(record_id).strip():
            raise ValueError("record_id 不能为空")

        records = self._load_records(record_type)
        kept: list[dict[str, Any]] = []
        deleted: dict[str, Any] | None = None

        for record in records:
            same_id = str(record.get("id", "")) == str(record_id)
            same_db = db_id is None or record.get("db_id") == db_id
            if same_id and same_db:
                deleted = record
                continue
            kept.append(record)

        if deleted is None:
            raise ValueError(f"未找到要删除的记录：{record_id}")

        self._save_records(record_type, kept)
        return deleted

    def _append_record(self, record_type: str, record: dict[str, Any]) -> str:
        self._validate_record_type(record_type)
        records = self._load_records(record_type)

        duplicate = self._find_duplicate(record_type, records, record)
        if duplicate is not None:
            raise ValueError(f"重复内容已存在，禁止重复添加。已有记录 ID: {duplicate.get('id', '')}")

        record_id = str(uuid.uuid4())
        record = {
            "id": record_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        records.append(record)
        self._save_records(record_type, records)
        return record_id

    def _find_duplicate(self, record_type: str, records: list[dict[str, Any]], record: dict[str, Any]) -> dict[str, Any] | None:
        key = self._duplicate_key(record_type, record)
        for old in records:
            if old.get("db_id") != record.get("db_id"):
                continue
            if self._duplicate_key(record_type, old) == key:
                return old
        return None

    def _duplicate_key(self, record_type: str, record: dict[str, Any]) -> str:
        if record_type == "documentation":
            return self._normalize_for_key(record.get("content", ""))
        if record_type == "question_sql":
            return "|".join([
                self._normalize_for_key(record.get("question", "")),
                self._normalize_sql(record.get("sql", "")),
            ])
        if record_type == "error_fix":
            return "|".join([
                self._normalize_for_key(record.get("question", "")),
                self._normalize_sql(record.get("wrong_sql", "")),
                self._normalize_for_key(record.get("error_message", "")),
                self._normalize_for_key(record.get("fix_rule", "")),
            ])
        if record_type == "ddl":
            return self._normalize_sql(record.get("content", ""))
        return self._normalize_for_key(json.dumps(record, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _normalize_for_key(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _normalize_sql(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
        text = re.sub(r"--.*?(?=\n|$)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text.rstrip(";").strip() + (";" if text else "")

    def _load_records(self, record_type: str) -> list[dict[str, Any]]:
        self._validate_record_type(record_type)
        path = self.memory_dir / self.RECORD_FILES[record_type]
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Memory file must contain a list: {path}")
        return data

    def _save_records(self, record_type: str, records: list[dict[str, Any]]) -> None:
        self._validate_record_type(record_type)
        path = self.memory_dir / self.RECORD_FILES[record_type]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    def _validate_record_type(self, record_type: str) -> None:
        if record_type not in self.RECORD_FILES:
            allowed = ", ".join(sorted(self.RECORD_FILES))
            raise ValueError(f"Unsupported memory type: {record_type}. Allowed: {allowed}")

    def _rank_records(self, *, records: list[dict[str, Any]], query: str, top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        query_tokens = self._tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []

        for record in records:
            text = self._record_search_text(record)
            score = self._bm25_like_score(query_tokens, self._tokenize(text))
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [record for _, record in scored[:top_k]]

    @staticmethod
    def _record_search_text(record: dict[str, Any]) -> str:
        parts = [
            str(record.get("content", "")),
            str(record.get("question", "")),
            str(record.get("sql", "")),
            str(record.get("wrong_sql", "")),
            str(record.get("error_message", "")),
            str(record.get("fix_rule", "")),
            json.dumps(record.get("metadata", {}), ensure_ascii=False),
        ]
        return "\n".join(parts)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = str(text or "").lower()
        return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text)

    @staticmethod
    def _bm25_like_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        query_counts = Counter(query_tokens)
        doc_counts = Counter(doc_tokens)
        doc_len = len(doc_tokens)

        score = 0.0
        for token, q_count in query_counts.items():
            tf = doc_counts.get(token, 0)
            if tf == 0:
                continue
            score += (1.0 + math.log(1.0 + tf)) * (1.0 + math.log(1.0 + q_count))

        return score / math.sqrt(doc_len)
