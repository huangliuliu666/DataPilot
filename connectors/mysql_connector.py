from __future__ import annotations

import re
from typing import Any

from connectors.base import BaseConnector


class MySQLConnector(BaseConnector):

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 3306,
        user: str,
        password: str,
        database: str,
        charset: str = "utf8mb4",
        connect_timeout: int = 10,
    ) -> None:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as e:
            raise RuntimeError(
                "缺少 PyMySQL 依赖。请先执行："
                "python -m pip install pymysql"
            ) from e

        self.db_path = None
        self.host = host
        self.port = int(port)
        self.user = user
        self.database = database
        self.charset = charset

        self.conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            charset=charset,
            cursorclass=DictCursor,
            autocommit=True,
            read_timeout=120,
            write_timeout=120,
            connect_timeout=connect_timeout,
        )

    def inspect_schema(self) -> str:
        with self.conn.cursor() as cursor:
            cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
            rows = cursor.fetchall()

        if not rows:
            raise RuntimeError(f"No user tables found in MySQL database: {self.database}")

        ddl_statements: list[str] = []
        for row in rows:
            table_name = self._extract_table_name(row)
            with self.conn.cursor() as cursor:
                cursor.execute(f"SHOW CREATE TABLE `{self._escape_identifier(table_name)}`")
                create_row = cursor.fetchone()
            if not create_row:
                raise RuntimeError(f"SHOW CREATE TABLE returned empty result for table: {table_name}")
            create_sql = create_row.get("Create Table") or create_row.get("Create View")
            if not create_sql:
                raise RuntimeError(f"Cannot find CREATE statement for table: {table_name}")
            ddl_statements.append(str(create_sql).strip().rstrip(";") + ";")

        return "\n\n".join(ddl_statements)

    def inspect_schema_metadata(self, db_id: str | None = None) -> dict[str, Any]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
                """,
                (self.database,),
            )
            table_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       COLUMN_KEY, COLUMN_COMMENT, ORDINAL_POSITION
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                (self.database,),
            )
            column_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY TABLE_NAME, COLUMN_NAME
                """,
                (self.database,),
            )
            fk_rows = cursor.fetchall()

        if not table_rows:
            raise RuntimeError(f"No user tables found in MySQL database: {self.database}")

        columns_by_table: dict[str, list[dict[str, Any]]] = {}
        pks_by_table: dict[str, list[str]] = {}
        for row in column_rows:
            table_name = row["TABLE_NAME"]
            col = {
                "name": row["COLUMN_NAME"],
                "type": row["COLUMN_TYPE"],
                "nullable": row["IS_NULLABLE"] == "YES",
                "default": row["COLUMN_DEFAULT"],
                "is_primary_key": row["COLUMN_KEY"] == "PRI",
                "db_comment": row.get("COLUMN_COMMENT") or "",
            }
            columns_by_table.setdefault(table_name, []).append(col)
            if col["is_primary_key"]:
                pks_by_table.setdefault(table_name, []).append(col["name"])

        fks_by_table: dict[str, list[dict[str, Any]]] = {}
        for row in fk_rows:
            fks_by_table.setdefault(row["TABLE_NAME"], []).append(
                {
                    "from_table": row["TABLE_NAME"],
                    "from_column": row["COLUMN_NAME"],
                    "to_table": row["REFERENCED_TABLE_NAME"],
                    "to_column": row["REFERENCED_COLUMN_NAME"],
                }
            )

        tables = []
        for row in table_rows:
            table_name = row["TABLE_NAME"]
            tables.append(
                {
                    "name": table_name,
                    "type": "table",
                    "db_comment": row.get("TABLE_COMMENT") or "",
                    "columns": columns_by_table.get(table_name, []),
                    "primary_keys": pks_by_table.get(table_name, []),
                    "foreign_keys": fks_by_table.get(table_name, []),
                }
            )

        return {
            "db_id": db_id,
            "db_type": "mysql",
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "tables": tables,
        }

    def profile_table(
        self,
        table_name: str,
        *,
        columns: list[str],
        sample_limit: int = 20,
        distinct_limit: int = 1000,
    ) -> dict[str, Any]:
        with self.conn.cursor() as cursor:
            q_table = self._quote_identifier(table_name)
            cursor.execute(f"SELECT COUNT(*) AS c FROM {q_table}")
            row_count = int(cursor.fetchone()["c"])

            column_profiles = []
            for column in columns:
                q_col = self._quote_identifier(column)
                cursor.execute(f"SELECT COUNT({q_col}) AS c FROM {q_table}")
                non_null_count = int(cursor.fetchone()["c"])

                cursor.execute(f"SELECT COUNT(DISTINCT {q_col}) AS c FROM {q_table}")
                distinct_count = int(cursor.fetchone()["c"])

                cursor.execute(
                    f"SELECT DISTINCT {q_col} AS value FROM {q_table} WHERE {q_col} IS NOT NULL LIMIT %s",
                    (int(sample_limit),),
                )
                sample_values = [row["value"] for row in cursor.fetchall()]

                cursor.execute(f"SELECT MIN({q_col}) AS min_v, MAX({q_col}) AS max_v FROM {q_table} WHERE {q_col} IS NOT NULL")
                min_max = cursor.fetchone()
                min_value, max_value = min_max.get("min_v"), min_max.get("max_v")

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

        with self.conn.cursor() as cursor:
            cursor.execute(clean_sql)
            rows = cursor.fetchall() if limit is None else cursor.fetchmany(limit)

        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _extract_table_name(row: dict[str, Any]) -> str:
        for value in row.values():
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"Cannot extract table name from SHOW FULL TABLES row: {row}")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return "`" + str(identifier).replace("`", "``") + "`"

    @staticmethod
    def _escape_identifier(identifier: str) -> str:
        if not identifier:
            raise ValueError("identifier 不能为空")
        return identifier.replace("`", "``")

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
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|PRAGMA|VACUUM|CALL|LOAD|GRANT|REVOKE)\b",
            sql,
            flags=re.IGNORECASE,
        )
        if forbidden:
            raise ValueError(f"只读查询中不允许出现关键字: {forbidden.group(1)}")
