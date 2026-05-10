from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.text2sql_agent import Text2SQLAgent
from api.schemas import (
    AskRequest,
    ConnectMySQLRequest,
    ConnectSQLiteRequest,
    ExecuteSQLRequest,
    ImportAnnotatedSchemaRequest,
    LoadWorkspaceRequest,
    TrainRequest,
)

app = FastAPI(title="企业数据问答平台 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
agent = Text2SQLAgent()


def _raise_api_error(exc: Exception) -> None:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=message) from exc
    if isinstance(exc, ValueError):
        status = 409 if any(k in message for k in ["重复", "已存在", "already exists", "duplicate"]) else 400
        raise HTTPException(status_code=status, detail=message) from exc
    raise HTTPException(status_code=500, detail=message) from exc


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        _raise_api_error(exc)


@app.get("/")
def root() -> dict:
    return {
        "name": "企业数据问答平台 API",
        "status": "running",
        "docs": "/docs",
        "front_end": "React front-end usually runs on http://127.0.0.1:5173",
        "endpoints": [
            "/connect/sqlite",
            "/connect/mysql",
            "/workspace/load",
            "/refresh_schema/{db_id}",
            "/import/annotated_schema",
            "/train",
            "/ask",
            "/execute_sql",
            "/databases",
            "/workspaces",
            "/workspace/{db_id}",
            "/memory",
        ],
    }


@app.post("/connect/sqlite")
def connect_sqlite(req: ConnectSQLiteRequest) -> dict:
    return _call(
        agent.connect_sqlite,
        db_id=req.db_id,
        db_path=req.db_path,
        auto_train_schema=req.auto_train_schema,
        force_refresh=req.force_refresh,
    )


@app.post("/connect/mysql")
def connect_mysql(req: ConnectMySQLRequest) -> dict:
    return _call(
        agent.connect_mysql,
        db_id=req.db_id,
        host=req.host,
        port=req.port,
        user=req.user,
        password=req.password,
        database=req.database,
        charset=req.charset,
        auto_train_schema=req.auto_train_schema,
        force_refresh=req.force_refresh,
    )


@app.post("/workspace/load")
def load_workspace(req: LoadWorkspaceRequest) -> dict:
    return _call(agent.load_workspace, db_id=req.db_id, mysql_password=req.mysql_password)


@app.post("/refresh_schema/{db_id}")
def refresh_schema(db_id: str, auto_train_schema: bool = True) -> dict:
    return _call(agent.refresh_schema, db_id=db_id, auto_train_schema=auto_train_schema)


@app.post("/import/annotated_schema")
def import_annotated_schema(req: ImportAnnotatedSchemaRequest) -> dict:
    return _call(agent.import_annotated_schema, db_id=req.db_id, annotated_schema_text=req.annotated_schema_text)


@app.post("/train")
def train(req: TrainRequest) -> dict:
    record_ids = _call(
        agent.train,
        db_id=req.db_id,
        ddl=req.ddl,
        documentation=req.documentation,
        question=req.question,
        sql=req.sql,
        error_message=req.error_message,
        fix_rule=req.fix_rule,
        metadata=req.metadata,
    )
    return {"status": "success", "record_ids": record_ids}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    return _call(
        agent.ask,
        db_id=req.db_id,
        question=req.question,
        evidence=req.evidence,
        run_sql=req.run_sql,
        result_limit=req.result_limit,
        memory_top_k=req.memory_top_k,
        use_topology_trimming=req.use_topology_trimming,
        use_sql_structure_retrieval=req.use_sql_structure_retrieval,
        use_global_structure_examples=req.use_global_structure_examples,
    )


@app.post("/execute_sql")
def execute_sql(req: ExecuteSQLRequest) -> dict:
    result = _call(agent.execute_sql, db_id=req.db_id, sql=req.sql, limit=req.limit)
    return {"status": "success", "result": result}


@app.get("/databases")
def databases() -> dict:
    return {"databases": _call(agent.connected_databases)}


@app.get("/workspaces")
def workspaces() -> dict:
    return {"workspaces": _call(agent.list_workspaces)}


@app.get("/workspace/{db_id}")
def workspace_status(db_id: str) -> dict:
    return _call(agent.workspace_status, db_id=db_id)




@app.get("/schema/{db_id}")
def workspace_schema(db_id: str) -> dict:
    return {
        "db_id": db_id,
        "enriched_schema_sql": _call(agent.workspace.read_schema_artifact, db_id, "enriched_schema.sql", default=""),
        "enriched_schema_md": _call(agent.workspace.read_schema_artifact, db_id, "enriched_schema.md", default=""),
        "manual_annotations": _call(agent.workspace.read_schema_artifact, db_id, "manual_annotations.json", default={"tables": {}, "columns": {}}),
        "auto_annotations": _call(agent.workspace.read_schema_artifact, db_id, "auto_annotations.json", default={"tables": {}, "columns": {}}),
    }


@app.get("/memory")
def list_memory(db_id: str | None = None, record_type: str | None = None) -> dict:
    memory = _call(agent._memory, db_id) if db_id else agent.default_memory
    return {"records": _call(memory.list_records, record_type)}


@app.delete("/memory/{db_id}/{record_type}/{record_id}")
def delete_memory_record(db_id: str, record_type: str, record_id: str) -> dict:
    deleted = _call(agent.delete_memory_record, db_id=db_id, record_type=record_type, record_id=record_id)
    return {"status": "deleted", "record": deleted}
