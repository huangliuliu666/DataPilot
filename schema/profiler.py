from __future__ import annotations

from typing import Any

from connectors.base import BaseConnector


class SchemaProfiler:

    def __init__(self, connector: BaseConnector, *, sample_limit: int = 20, distinct_limit: int = 1000) -> None:
        self.connector = connector
        self.sample_limit = int(sample_limit)
        self.distinct_limit = int(distinct_limit)

    def profile(self, raw_schema: dict[str, Any]) -> dict[str, Any]:
        tables: list[dict[str, Any]] = []
        for table in raw_schema.get("tables", []):
            table_name = table["name"]
            table_profile = self.connector.profile_table(
                table_name,
                columns=[col["name"] for col in table.get("columns", [])],
                sample_limit=self.sample_limit,
                distinct_limit=self.distinct_limit,
            )
            tables.append(table_profile)
        return {"db_id": raw_schema.get("db_id"), "db_type": raw_schema.get("db_type"), "tables": tables}
