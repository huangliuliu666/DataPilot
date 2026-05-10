from __future__ import annotations

import re
from typing import Any


class EnrichedSchemaBuilder:

    def build(
        self,
        *,
        raw_schema: dict[str, Any],
        table_profile: dict[str, Any],
        auto_annotations: dict[str, Any],
        manual_annotations: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manual_annotations = manual_annotations or {"tables": {}, "columns": {}}
        profile_by_table = {table["name"]: table for table in table_profile.get("tables", [])}

        tables: list[dict[str, Any]] = []
        for table in raw_schema.get("tables", []):
            table_name = table["name"]
            table_auto = auto_annotations.get("tables", {}).get(table_name, {})
            table_manual = manual_annotations.get("tables", {}).get(table_name)
            table_final = table_manual or table_auto or {"comment": table.get("db_comment", ""), "source": "raw"}
            table_prof = profile_by_table.get(table_name, {})
            col_profiles = {col["name"]: col for col in table_prof.get("columns", [])}

            enriched_columns = []
            for col in table.get("columns", []):
                column_name = col["name"]
                key = f"{table_name}.{column_name}"
                col_auto = auto_annotations.get("columns", {}).get(key, {})
                col_manual = manual_annotations.get("columns", {}).get(key)
                col_final = col_manual or col_auto or {"comment": col.get("db_comment", ""), "source": "raw"}
                enriched_columns.append(
                    {
                        **col,
                        "auto_comment": col_auto.get("comment", ""),
                        "manual_comment": (col_manual or {}).get("comment", ""),
                        "final_comment": col_final.get("comment", ""),
                        "comment_source": col_final.get("source", "auto"),
                        "need_review": bool(col_auto.get("need_review", False)) and not bool(col_manual),
                        "profile": col_profiles.get(column_name, {}),
                    }
                )

            tables.append(
                {
                    **table,
                    "auto_comment": table_auto.get("comment", ""),
                    "manual_comment": (table_manual or {}).get("comment", ""),
                    "final_comment": table_final.get("comment", ""),
                    "comment_source": table_final.get("source", "auto"),
                    "profile": table_prof,
                    "columns": enriched_columns,
                }
            )

        enriched = {"db_id": raw_schema.get("db_id"), "db_type": raw_schema.get("db_type"), "tables": tables}
        enriched["sql"] = self.to_sql(enriched)
        enriched["markdown"] = self.to_markdown(enriched)
        return enriched

    def to_sql(self, enriched_schema: dict[str, Any]) -> str:
        statements: list[str] = []
        for table in enriched_schema.get("tables", []):
            lines: list[str] = []
            for col in table.get("columns", []):
                col_name = self._quote_identifier(col["name"])
                col_type = col.get("type") or "TEXT"
                comment = self._sql_escape(col.get("final_comment", ""))
                pk = " PRIMARY KEY" if col.get("is_primary_key") and not table.get("primary_keys") else ""
                line = f"{col_name} {col_type}{pk}"
                if comment:
                    line += f" COMMENT '{comment}'"
                lines.append(line)

            if table.get("primary_keys"):
                pk_cols = ", ".join(self._quote_identifier(col) for col in table.get("primary_keys", []))
                lines.append(f"PRIMARY KEY ({pk_cols})")

            for fk in table.get("foreign_keys", []):
                from_col = fk.get("from_column")
                ref_table = fk.get("to_table")
                ref_col = fk.get("to_column")
                if from_col and ref_table and ref_col:
                    lines.append(
                        f"FOREIGN KEY ({self._quote_identifier(from_col)}) REFERENCES {self._quote_identifier(ref_table)}({self._quote_identifier(ref_col)})"
                    )

            table_comment = self._sql_escape(table.get("final_comment", ""))
            suffix = f" COMMENT='{table_comment}'" if table_comment else ""
            body = ",\n    ".join(lines)
            statements.append(f"CREATE TABLE {self._quote_identifier(table['name'])} (\n    {body}\n){suffix};")
        return "\n\n".join(statements)

    def to_markdown(self, enriched_schema: dict[str, Any]) -> str:
        chunks: list[str] = []
        for table in enriched_schema.get("tables", []):
            chunks.append(f"## Table: {table['name']}")
            if table.get("final_comment"):
                chunks.append(f"Description: {table['final_comment']}")
            chunks.append("Columns:")
            for col in table.get("columns", []):
                profile = col.get("profile", {})
                sample_values = profile.get("sample_values") or []
                sample_text = f" Sample values: {', '.join(map(str, sample_values[:5]))}." if sample_values else ""
                chunks.append(
                    f"- {col['name']} ({col.get('type', '')}): {col.get('final_comment', '')}{sample_text}"
                )
            if table.get("primary_keys"):
                chunks.append(f"Primary keys: {', '.join(table['primary_keys'])}")
            if table.get("foreign_keys"):
                fk_text = []
                for fk in table.get("foreign_keys", []):
                    fk_text.append(f"{fk.get('from_column')} -> {fk.get('to_table')}.{fk.get('to_column')}")
                chunks.append(f"Foreign keys: {', '.join(fk_text)}")
            chunks.append("")
        return "\n".join(chunks).strip()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        text = str(identifier).replace("`", "``")
        return f"`{text}`"

    @staticmethod
    def _sql_escape(text: str) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        return text.replace("'", "''")
