from __future__ import annotations

import re
from typing import Any


class AnnotationBuilder:

    def build(self, raw_schema: dict[str, Any], table_profile: dict[str, Any]) -> dict[str, Any]:
        profile_by_table = {table["name"]: table for table in table_profile.get("tables", [])}
        table_annotations: dict[str, dict[str, Any]] = {}
        column_annotations: dict[str, dict[str, Any]] = {}

        for table in raw_schema.get("tables", []):
            table_name = table["name"]
            table_comment = table.get("db_comment") or self._humanize_identifier(table_name)
            table_annotations[table_name] = {
                "comment": self._build_table_comment(table_name, table_comment),
                "source": "auto",
                "need_review": not bool(table.get("db_comment")),
            }

            table_prof = profile_by_table.get(table_name, {})
            col_profiles = {col["name"]: col for col in table_prof.get("columns", [])}
            for col in table.get("columns", []):
                column_name = col["name"]
                key = f"{table_name}.{column_name}"
                col_profile = col_profiles.get(column_name, {})
                db_comment = col.get("db_comment", "")
                auto_comment, need_review = self._build_column_comment(
                    table_name=table_name,
                    column_name=column_name,
                    column_type=col.get("type", ""),
                    db_comment=db_comment,
                    profile=col_profile,
                )
                column_annotations[key] = {
                    "comment": auto_comment,
                    "source": "db_comment" if db_comment else "auto",
                    "need_review": need_review,
                }

        return {"tables": table_annotations, "columns": column_annotations}

    def _build_table_comment(self, table_name: str, table_comment: str) -> str:
        if table_comment and table_comment != self._humanize_identifier(table_name):
            return table_comment.strip()
        return f"Table storing {self._humanize_identifier(table_name)} records."

    def _build_column_comment(
        self,
        *,
        table_name: str,
        column_name: str,
        column_type: str,
        db_comment: str,
        profile: dict[str, Any],
    ) -> tuple[str, bool]:
        if db_comment:
            return db_comment.strip(), False

        name_text = self._humanize_identifier(column_name)
        lower = name_text.lower()
        samples = profile.get("sample_values") or []
        sample_text = ", ".join(str(v) for v in samples[:5] if v is not None)
        nullable = profile.get("null_ratio")
        distinct_count = profile.get("distinct_count")

        if self._looks_like_identifier(column_name):
            comment = f"Identifier field for {name_text}."
        elif any(token in lower for token in ["date", "time", "year", "month", "day"]):
            comment = f"Date/time related field: {name_text}."
        elif any(token in lower for token in ["count", "number", "num", "total", "enrollment", "amount", "score", "rate", "percent", "ratio"]):
            comment = f"Numeric measure for {name_text}."
        elif samples and distinct_count is not None and distinct_count <= 30:
            comment = f"Categorical field for {name_text}."
        else:
            comment = f"Field representing {name_text}."

        extras = []
        if sample_text:
            extras.append(f"Sample values: {sample_text}.")
        if nullable is not None:
            extras.append(f"Null ratio: {nullable:.2f}.")
        if extras:
            comment = comment + " " + " ".join(extras)

        need_review = True
        return comment, need_review

    @staticmethod
    def _humanize_identifier(identifier: str) -> str:
        text = str(identifier or "").strip().strip("`\"[]")
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or "unknown"

    @staticmethod
    def _looks_like_identifier(column_name: str) -> bool:
        lower = column_name.lower()
        return lower in {"id", "uid", "uuid"} or lower.endswith("_id") or lower.endswith("id") or "code" in lower
