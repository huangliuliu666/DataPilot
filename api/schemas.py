from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConnectSQLiteRequest(BaseModel):
    db_id: str
    db_path: str
    auto_train_schema: bool = True
    force_refresh: bool = False


class ConnectMySQLRequest(BaseModel):
    db_id: str
    host: str = "127.0.0.1"
    port: int = 3306
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"
    auto_train_schema: bool = True
    force_refresh: bool = False


class LoadWorkspaceRequest(BaseModel):
    db_id: str
    mysql_password: str | None = None


class TrainRequest(BaseModel):
    db_id: str
    ddl: str | None = None
    documentation: str | None = None
    question: str | None = None
    sql: str | None = None
    error_message: str | None = None
    fix_rule: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportAnnotatedSchemaRequest(BaseModel):
    db_id: str
    annotated_schema_text: str


class AskRequest(BaseModel):
    db_id: str
    question: str
    evidence: str = ""
    run_sql: bool = True
    result_limit: int | None = 100
    memory_top_k: int = 5
    use_topology_trimming: bool | None = None
    use_sql_structure_retrieval: bool | None = None
    use_global_structure_examples: bool | None = None


class ExecuteSQLRequest(BaseModel):
    db_id: str
    sql: str
    limit: int | None = 100
