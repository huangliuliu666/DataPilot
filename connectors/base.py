from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    @abstractmethod
    def inspect_schema(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def inspect_schema_metadata(self, db_id: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def profile_table(
        self,
        table_name: str,
        *,
        columns: list[str],
        sample_limit: int = 20,
        distinct_limit: int = 1000,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute_sql(self, sql: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
