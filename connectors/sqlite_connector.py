from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from connectors.base import BaseConnector


class SQLiteConnector(BaseConnector):

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {self.db_path}")

        self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA query_only=ON")
        self.conn.execute("PRAGMA case_sensitive_like=OFF")

    def inspect_schema(self) -> str:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
              AND sql IS NOT NULL
            ORDER BY name
            """
        )
        statements = [row[0].strip().rstrip(";") + ";" for row in cursor.fetchall()]
        if not statements:
            raise RuntimeError(f"No user tables found in SQLite database: {self.db_path}")
        return "\n\n".join(statements)

    def inspect_schema_metadata(self, db_id: str | None = None) -> dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        table_names = [row[0] for row in cursor.fetchall()]
        if not table_names:
            raise RuntimeError(f"No user tables found in SQLite database: {self.db_path}")

        tables: list[dict[str, Any]] = []
        for table_name in table_names:
            cursor.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})")
            pragma_cols = cursor.fetchall()
            columns = []
            primary_keys = []
            for row in pragma_cols:
                col = {
                    "name": row[1],
                    "type": row[2] or "TEXT",
                    "nullable": not bool(row[3]),
                    "default": row[4],
                    "is_primary_key": bool(row[5]),
                    "db_comment": "",
                }
                columns.append(col)
                if bool(row[5]):
                    primary_keys.append(row[1])

            cursor.execute(f"PRAGMA foreign_key_list({self._quote_identifier(table_name)})")
            foreign_keys = []
            for row in cursor.fetchall():
                foreign_keys.append(
                    {
                        "from_table": table_name,
                        "from_column": row[3],
                        "to_table": row[2],
                        "to_column": row[4],
                    }
                )

            tables.append(
                {
                    "name": table_name,
                    "type": "table",
                    "db_comment": "",
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                }
            )

        return {"db_id": db_id, "db_type": "sqlite", "db_path": str(self.db_path), "tables": tables}

    def profile_table(
        self,
        table_name: str,
        *,
        columns: list[str],
        sample_limit: int = 20,
        distinct_limit: int = 1000,
    ) -> dict[str, Any]:
        cursor = self.conn.cursor()
        q_table = self._quote_identifier(table_name)
        cursor.execute(f"SELECT COUNT(*) AS c FROM {q_table}")
        row_count = int(cursor.fetchone()[0])

        column_profiles = []
        for column in columns:
            q_col = self._quote_identifier(column)
            cursor.execute(f"SELECT COUNT({q_col}) AS c FROM {q_table}")
            non_null_count = int(cursor.fetchone()[0])

            cursor.execute(f"SELECT COUNT(DISTINCT {q_col}) AS c FROM {q_table}")
            distinct_count = int(cursor.fetchone()[0])

            cursor.execute(
                f"SELECT DISTINCT {q_col} AS value FROM {q_table} WHERE {q_col} IS NOT NULL LIMIT ?",
                (int(sample_limit),),
            )
            sample_values = [row[0] for row in cursor.fetchall()]

            cursor.execute(f"SELECT MIN({q_col}) AS min_v, MAX({q_col}) AS max_v FROM {q_table} WHERE {q_col} IS NOT NULL")
            min_max = cursor.fetchone()
            min_value, max_value = min_max[0], min_max[1]

            column_profiles.append(
                {
                    "name": column,
                    "row_count": row_count,
                    "non_null_count": non_null_count,
                    "null_ratio": 0.0 if row_count == 0 else round(1 - non_null_count / row_count, 6),
                    "distinct_count": distinct_count,
                    "sample_values": sample_values,
                    "min": min_value,
                    "max": max_value,
                }
            )

        return {"name": table_name, "row_count": row_count, "columns": column_profiles}

    def execute_sql(self, sql: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        clean_sql = self._clean_sql(sql)
        self._validate_readonly_select(clean_sql)

        cursor = self.conn.cursor()
        cursor.execute(clean_sql)

        rows = cursor.fetchall() if limit is None else cursor.fetchmany(limit)
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return "`" + str(identifier).replace("`", "``") + "`"

    @staticmethod
    def _clean_sql(sql: str) -> str:
        text = str(sql or "").strip()
        text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
        text = re.sub(r"--.*?(?=\n|$)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            raise ValueError("SQL 不能为空")

        return text

    @staticmethod
    def _validate_readonly_select(sql: str) -> None:
        if not re.match(r"^\s*SELECT\b", sql, flags=re.IGNORECASE):
            raise ValueError("只允许执行 SELECT 查询")

        statement_count = len([part for part in sql.split(";") if part.strip()])
        if statement_count > 1:
            raise ValueError("只允许执行单条 SQL 语句")

        forbidden = re.search(
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|PRAGMA|VACUUM)\b",
            sql,
            flags=re.IGNORECASE,
        )
        if forbidden:
            raise ValueError(f"只读查询中不允许出现关键字: {forbidden.group(1)}")
