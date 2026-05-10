from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Text2SQLResponse:

    question: str
    db_id: str
    sql: str
    status: str = "success"
    evidence: str = ""
    result: list[dict[str, Any]] | list[list[Any]] | None = None
    raw_llm_response: str = ""
    supplement_llm_response: str = ""
    active_schema_nodes: list[str] = field(default_factory=list)
    relationship: list[str] = field(default_factory=list)
    used_schema: str = ""
    column_value_hints: str = ""
    examples_used: str = ""
    memory_documentation: str = ""
    p_sql: str = ""
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
