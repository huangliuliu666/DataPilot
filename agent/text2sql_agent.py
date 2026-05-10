from __future__ import annotations

from pathlib import Path
from typing import Any

from config import Config
from agent.response import Text2SQLResponse
from connectors.base import BaseConnector
from connectors.mysql_connector import MySQLConnector
from connectors.sqlite_connector import SQLiteConnector
from core.schema_trim import generate_trimmed_schema
from core.semantic_mapper import SemanticHeatMapper
from core.topology import TopologyGraphBuilder
from memory.memory_store import MemoryStore
from schema.annotation_builder import AnnotationBuilder
from schema.enriched_schema import EnrichedSchemaBuilder
from schema.manual_importer import ManualAnnotationImporter
from schema.profiler import SchemaProfiler
from schema_graph import SchemaGraphBuilder, TopologyTrimmer
from retrieval import HybridExampleRetriever
from services.modelscope_engine import ModelScopeWorkflowEngine
from utils.io_utils import read_text, resolve_raw_schema_file_path, resolve_trim_schema_file_path
from utils.value_hints import build_column_value_hints, build_connector_column_value_hints
from workspace.workspace_manager import WorkspaceManager


class Text2SQLAgent:

    def __init__(
        self,
        memory_dir: str | Path | None = None,
        workspace_dir: str | Path | None = None,
    ) -> None:
        self.engine = ModelScopeWorkflowEngine()
        self.workspace = WorkspaceManager(workspace_dir or Config.WORKSPACE_DIR)
        self.default_memory = MemoryStore(memory_dir or Config.AGENT_MEMORY_DIR)
        self.memories: dict[str, MemoryStore] = {}
        self.connectors: dict[str, BaseConnector] = {}
        self.db_types: dict[str, str] = {}
        self.sql_dialects: dict[str, str] = {}
        self.raw_schema_cache: dict[str, str] = {}
        self.trim_schema_cache: dict[str, str] = {}
        self.raw_schema_metadata_cache: dict[str, dict[str, Any]] = {}
        self.db_cache: dict[str, tuple[TopologyGraphBuilder, SemanticHeatMapper]] = {}

                                                                        
                                                
                                                                        
    def connect_sqlite(
        self,
        *,
        db_id: str,
        db_path: str | Path,
        raw_schema_path: str | Path | None = None,
        trim_schema_path: str | Path | None = None,
        schema_path: str | Path | None = None,
        auto_train_schema: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if schema_path is not None and raw_schema_path is not None:
            raise ValueError("schema_path 与 raw_schema_path 只能传一个")

        connector = SQLiteConnector(db_path)
        self._register_connector(db_id=db_id, connector=connector, db_type="sqlite", sql_dialect="SQLite")

        connection_info = {"db_type": "sqlite", "db_path": str(Path(db_path))}
        result = self._load_or_build_workspace(
            db_id=db_id,
            connector=connector,
            db_type="sqlite",
            connection_info=connection_info,
            auto_train_schema=auto_train_schema,
            force_refresh=force_refresh,
        )

                                                                                             
        final_raw_schema_path = raw_schema_path or schema_path
        if final_raw_schema_path is not None:
            raw_schema_txt = read_text(final_raw_schema_path)
            self.raw_schema_cache[db_id] = raw_schema_txt
        if trim_schema_path is not None:
            trim_schema_txt = read_text(trim_schema_path)
            self.trim_schema_cache[db_id] = trim_schema_txt

        return result

    def connect_mysql(
        self,
        *,
        db_id: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        charset: str = "utf8mb4",
        auto_train_schema: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        connector = MySQLConnector(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
        )
        self._register_connector(db_id=db_id, connector=connector, db_type="mysql", sql_dialect="MySQL")

        connection_info = {
            "db_type": "mysql",
            "host": host,
            "port": int(port),
            "user": user,
            "database": database,
            "charset": charset,
        }
        return self._load_or_build_workspace(
            db_id=db_id,
            connector=connector,
            db_type="mysql",
            connection_info=connection_info,
            auto_train_schema=auto_train_schema,
            force_refresh=force_refresh,
        )

    def load_workspace(self, *, db_id: str, mysql_password: str | None = None) -> dict[str, Any]:
        if not self.workspace.has_workspace(db_id):
            raise ValueError(f"找不到已持久化的 workspace: {db_id}。请先连接数据库并完成首次构建。")

        manifest = self.workspace.load_manifest(db_id)
        registry = self.workspace.load_registry().get("databases", {}).get(db_id, {})
        db_type = manifest.get("db_type") or registry.get("db_type")
        if not db_type:
            raise RuntimeError(f"workspace 缺少 db_type: {db_id}")

        self.memories[db_id] = MemoryStore(self.workspace.memory_dir(db_id))
        self._load_workspace_schema_into_cache(db_id)
        self.db_types[db_id] = db_type
        self.sql_dialects[db_id] = "SQLite" if db_type == "sqlite" else "MySQL" if db_type == "mysql" else db_type

        execution_available = False
        if db_type == "sqlite":
            db_path = registry.get("db_path") or self.raw_schema_metadata_cache.get(db_id, {}).get("db_path")
            if not db_path:
                raise RuntimeError(f"SQLite workspace 缺少 db_path，无法自动重新打开数据库: {db_id}")
            connector = SQLiteConnector(db_path)
            self._register_connector(db_id=db_id, connector=connector, db_type="sqlite", sql_dialect="SQLite")
            execution_available = True
        elif db_type == "mysql":
            if mysql_password:
                connector = MySQLConnector(
                    host=registry.get("host", "127.0.0.1"),
                    port=int(registry.get("port", 3306)),
                    user=registry.get("user", "root"),
                    password=mysql_password,
                    database=registry.get("database", ""),
                    charset=registry.get("charset", "utf8mb4"),
                )
                self._register_connector(db_id=db_id, connector=connector, db_type="mysql", sql_dialect="MySQL")
                execution_available = True
        else:
            raise ValueError(f"Unsupported db_type in workspace: {db_type}")

        return {
            "status": "workspace_loaded",
            "db_id": db_id,
            "db_type": db_type,
            "execution_available": execution_available,
            "schema_fingerprint": manifest.get("schema_fingerprint", ""),
            "profile_done": manifest.get("profile_done", False),
            "auto_annotation_done": manifest.get("auto_annotation_done", False),
            "enriched_schema_built": manifest.get("enriched_schema_built", False),
            "message": "MySQL workspace loaded for generation only; provide password or reconnect MySQL to execute SQL."
            if db_type == "mysql" and not execution_available else "Workspace loaded.",
        }

    def can_execute(self, db_id: str) -> bool:
        if db_id in self.connectors:
            return True
        if self._get_db_type(db_id) == "sqlite":
            try:
                return self._get_db_path(db_id).exists()
            except Exception:
                return False
        return False

    def refresh_schema(self, *, db_id: str, auto_train_schema: bool = True) -> dict[str, Any]:
        if db_id not in self.connectors:
            raise ValueError(f"数据库尚未连接: {db_id}")
        return self._load_or_build_workspace(
            db_id=db_id,
            connector=self.connectors[db_id],
            db_type=self.db_types[db_id],
            connection_info={"db_type": self.db_types[db_id]},
            auto_train_schema=auto_train_schema,
            force_refresh=True,
        )

    def _load_or_build_workspace(
        self,
        *,
        db_id: str,
        connector: BaseConnector,
        db_type: str,
        connection_info: dict[str, Any],
        auto_train_schema: bool,
        force_refresh: bool,
    ) -> dict[str, Any]:
        self.workspace.ensure_workspace(db_id)
        self.workspace.update_registry(db_id, {**connection_info, "db_type": db_type})
        self.memories[db_id] = MemoryStore(self.workspace.memory_dir(db_id))

        raw_schema_metadata = connector.inspect_schema_metadata(db_id=db_id)
        schema_fingerprint = self.workspace.schema_fingerprint(raw_schema_metadata)
        self.raw_schema_metadata_cache[db_id] = raw_schema_metadata

        if not force_refresh and self.workspace.is_workspace_current(db_id, schema_fingerprint):
            self._load_workspace_schema_into_cache(db_id)
            manifest = self.workspace.load_manifest(db_id)
            return {"status": "loaded", "db_id": db_id, "schema_fingerprint": schema_fingerprint, "manifest": manifest}

        build_result = self._build_workspace_artifacts(
            db_id=db_id,
            connector=connector,
            db_type=db_type,
            raw_schema_metadata=raw_schema_metadata,
            schema_fingerprint=schema_fingerprint,
            auto_train_schema=auto_train_schema,
        )
        return build_result

    def _build_workspace_artifacts(
        self,
        *,
        db_id: str,
        connector: BaseConnector,
        db_type: str,
        raw_schema_metadata: dict[str, Any],
        schema_fingerprint: str,
        auto_train_schema: bool,
    ) -> dict[str, Any]:
        raw_schema_sql = connector.inspect_schema()
        profile = SchemaProfiler(connector).profile(raw_schema_metadata)
        auto_annotations = AnnotationBuilder().build(raw_schema_metadata, profile)
        old_manual = self.workspace.read_schema_artifact(db_id, "manual_annotations.json", default={"tables": {}, "columns": {}, "unmatched_lines": []})
        enriched = EnrichedSchemaBuilder().build(
            raw_schema=raw_schema_metadata,
            table_profile=profile,
            auto_annotations=auto_annotations,
            manual_annotations=old_manual,
        )

        self.workspace.write_schema_artifact(db_id, "raw_schema.json", raw_schema_metadata)
        self.workspace.write_schema_artifact(db_id, "raw_schema.sql", raw_schema_sql)
        self.workspace.write_schema_artifact(db_id, "schema_fingerprint.txt", schema_fingerprint)
        self.workspace.write_schema_artifact(db_id, "table_profile.json", profile)
        self.workspace.write_schema_artifact(db_id, "auto_annotations.json", auto_annotations)
        if old_manual is None:
            old_manual = {"tables": {}, "columns": {}, "unmatched_lines": []}
            self.workspace.write_schema_artifact(db_id, "manual_annotations.json", old_manual)
        self.workspace.write_schema_artifact(db_id, "enriched_schema.json", enriched)
        self.workspace.write_schema_artifact(db_id, "enriched_schema.sql", enriched["sql"])
        self.workspace.write_schema_artifact(db_id, "enriched_schema.md", enriched["markdown"])

        self.raw_schema_cache[db_id] = enriched["sql"]
        self.trim_schema_cache[db_id] = enriched["sql"]
        self.raw_schema_metadata_cache[db_id] = raw_schema_metadata

        if auto_train_schema:
            self._memory(db_id).upsert_schema_ddl(
                db_id=db_id,
                ddl=enriched["sql"],
                schema_fingerprint=schema_fingerprint,
                metadata={"db_type": db_type, "workspace": str(self.workspace.workspace_path(db_id))},
            )

        manifest = {
            "db_id": db_id,
            "db_type": db_type,
            "schema_fingerprint": schema_fingerprint,
            "profile_done": True,
            "auto_annotation_done": True,
            "enriched_schema_built": True,
            "table_count": len(raw_schema_metadata.get("tables", [])),
            "column_count": sum(len(t.get("columns", [])) for t in raw_schema_metadata.get("tables", [])),
            "last_built_at": self.workspace.load_manifest(db_id).get("updated_at"),
        }
        self.workspace.save_manifest(db_id, manifest)
        return {"status": "built", "db_id": db_id, "schema_fingerprint": schema_fingerprint, "manifest": self.workspace.load_manifest(db_id)}

    def _load_workspace_schema_into_cache(self, db_id: str) -> None:
        raw_metadata = self.workspace.read_schema_artifact(db_id, "raw_schema.json", default={})
        enriched_sql = self.workspace.read_schema_artifact(db_id, "enriched_schema.sql", default="")
        if not raw_metadata or not enriched_sql:
            raise RuntimeError(f"Workspace schema artifacts are incomplete for db_id={db_id}")
        self.raw_schema_metadata_cache[db_id] = raw_metadata
        self.raw_schema_cache[db_id] = enriched_sql
        self.trim_schema_cache[db_id] = enriched_sql

    def _register_connector(self, *, db_id: str, connector: BaseConnector, db_type: str, sql_dialect: str) -> None:
        if db_id in self.connectors:
            self.connectors[db_id].close()
        if db_id in self.db_cache:
            self.db_cache[db_id][0].close()
            self.db_cache.pop(db_id, None)
        self.connectors[db_id] = connector
        self.db_types[db_id] = db_type
        self.sql_dialects[db_id] = sql_dialect

                                                                        
                                 
                                                                        
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
        return self._memory(db_id).train(
            db_id=db_id,
            ddl=ddl,
            documentation=documentation,
            question=question,
            sql=sql,
            error_message=error_message,
            fix_rule=fix_rule,
            metadata=metadata,
        )

    def train_database_schema(self, *, db_id: str) -> str:
        if db_id not in self.connectors:
            raise ValueError(f"数据库尚未连接: {db_id}")
        self.refresh_schema(db_id=db_id, auto_train_schema=True)
        manifest = self.workspace.load_manifest(db_id)
        return manifest.get("schema_fingerprint", "")

    def train_ddl(self, *, db_id: str, ddl: str, metadata: dict[str, Any] | None = None) -> str:
        return self._memory(db_id).train_ddl(db_id=db_id, ddl=ddl, metadata=metadata)

    def train_documentation(
        self,
        *,
        db_id: str,
        documentation: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._memory(db_id).train_documentation(db_id=db_id, documentation=documentation, metadata=metadata)

    def train_question_sql(
        self,
        *,
        db_id: str,
        question: str,
        sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._memory(db_id).train_question_sql(db_id=db_id, question=question, sql=sql, metadata=metadata)

    def import_annotated_schema(self, *, db_id: str, annotated_schema_text: str) -> dict[str, Any]:
        if not str(annotated_schema_text).strip():
            raise ValueError("annotated_schema_text 不能为空")
        raw_schema = self._get_raw_schema_metadata(db_id)
        parsed = ManualAnnotationImporter().parse(annotated_schema_text, raw_schema)
        old_manual = self.workspace.read_schema_artifact(db_id, "manual_annotations.json", default={"tables": {}, "columns": {}, "unmatched_lines": []})
        diff = ManualAnnotationImporter.diff_manual_annotations(old_manual, parsed)
        changed_count = diff["new_tables"] + diff["updated_tables"] + diff["new_columns"] + diff["updated_columns"]
        parsed_count = len(parsed.get("tables", {})) + len(parsed.get("columns", {}))
        if parsed_count == 0:
            raise ValueError("没有识别到可导入的表/字段注释，请检查格式是否为 SQL COMMENT、普通 Table/Column 文本或 JSON。")
        if changed_count == 0:
            raise ValueError("导入内容与已有手写注释完全重复，没有新的表/字段注释需要保存。")

        merged = ManualAnnotationImporter.merge_manual_annotations(old_manual, parsed)
        self.workspace.write_schema_artifact(db_id, "manual_annotations.json", merged)
        self._rebuild_enriched_schema_from_workspace(db_id)
        return {
            "status": "imported",
            "db_id": db_id,
            "table_annotations": len(parsed.get("tables", {})),
            "column_annotations": len(parsed.get("columns", {})),
            "new_tables": diff["new_tables"],
            "updated_tables": diff["updated_tables"],
            "unchanged_tables": diff["unchanged_tables"],
            "new_columns": diff["new_columns"],
            "updated_columns": diff["updated_columns"],
            "unchanged_columns": diff["unchanged_columns"],
            "unmatched_lines": parsed.get("unmatched_lines", []),
        }

    def _rebuild_enriched_schema_from_workspace(self, db_id: str) -> None:
        raw_schema = self.workspace.read_schema_artifact(db_id, "raw_schema.json", default={})
        profile = self.workspace.read_schema_artifact(db_id, "table_profile.json", default={})
        auto_annotations = self.workspace.read_schema_artifact(db_id, "auto_annotations.json", default={"tables": {}, "columns": {}})
        manual_annotations = self.workspace.read_schema_artifact(db_id, "manual_annotations.json", default={"tables": {}, "columns": {}, "unmatched_lines": []})
        if not raw_schema or not profile:
            raise RuntimeError(f"Workspace artifacts are incomplete for db_id={db_id}; connect or refresh schema first")
        enriched = EnrichedSchemaBuilder().build(
            raw_schema=raw_schema,
            table_profile=profile,
            auto_annotations=auto_annotations,
            manual_annotations=manual_annotations,
        )
        self.workspace.write_schema_artifact(db_id, "enriched_schema.json", enriched)
        self.workspace.write_schema_artifact(db_id, "enriched_schema.sql", enriched["sql"])
        self.workspace.write_schema_artifact(db_id, "enriched_schema.md", enriched["markdown"])
        self.raw_schema_cache[db_id] = enriched["sql"]
        self.trim_schema_cache[db_id] = enriched["sql"]
        manifest = self.workspace.load_manifest(db_id)
        fingerprint = manifest.get("schema_fingerprint") or self.workspace.schema_fingerprint(raw_schema)
        self._memory(db_id).upsert_schema_ddl(
            db_id=db_id,
            ddl=enriched["sql"],
            schema_fingerprint=fingerprint,
            metadata={"db_type": manifest.get("db_type", self.db_types.get(db_id, "unknown")), "source_detail": "manual_annotation_rebuild"},
        )

                                                                        
                                  
                                                                        
    def ask(
        self,
        *,
        question: str,
        db_id: str,
        evidence: str = "",
        run_sql: bool = True,
        result_limit: int | None = 100,
        memory_top_k: int = 3,
        use_topology_trimming: bool | None = None,
        use_sql_structure_retrieval: bool | None = None,
        use_global_structure_examples: bool | None = None,
    ) -> dict[str, Any]:
        response = self.generate_sql(
            question=question,
            db_id=db_id,
            evidence=evidence,
            memory_top_k=memory_top_k,
            use_topology_trimming=use_topology_trimming,
            use_sql_structure_retrieval=use_sql_structure_retrieval,
            use_global_structure_examples=use_global_structure_examples,
        )

        if run_sql:
            try:
                response.result = self.execute_sql(
                    db_id=db_id,
                    sql=response.sql,
                    limit=result_limit,
                )
            except Exception as exc:
                                                           
                response.status = "execution_error"
                response.result = None
                response.metadata = {
                    **(response.metadata or {}),
                    "execution_error": str(exc),
                    "execution_failed": True,
                }

        return response.to_dict()

    def generate_sql(
        self,
        *,
        question: str,
        db_id: str,
        evidence: str = "",
        memory_top_k: int = 3,
        use_topology_trimming: bool | None = None,
        use_sql_structure_retrieval: bool | None = None,
        use_global_structure_examples: bool | None = None,
    ) -> Text2SQLResponse:
        if not question.strip():
            raise ValueError("question 不能为空")

        db_type = self._get_db_type(db_id)
        if db_type == "sqlite":
            return self._generate_sql_for_sqlite(
                question=question,
                db_id=db_id,
                evidence=evidence,
                memory_top_k=memory_top_k,
                use_topology_trimming=use_topology_trimming,
                use_sql_structure_retrieval=use_sql_structure_retrieval,
                use_global_structure_examples=use_global_structure_examples,
            )
        if db_type == "mysql":
            return self._generate_sql_for_direct_schema(
                question=question,
                db_id=db_id,
                evidence=evidence,
                memory_top_k=memory_top_k,
                sql_dialect="MySQL",
                use_topology_trimming=use_topology_trimming,
                use_sql_structure_retrieval=use_sql_structure_retrieval,
                use_global_structure_examples=use_global_structure_examples,
            )
        raise ValueError(f"Unsupported db_type for db_id={db_id}: {db_type}")

    def execute_sql(self, *, db_id: str, sql: str, limit: int | None = 100) -> list[dict[str, Any]]:
        if db_id in self.connectors:
            return self.connectors[db_id].execute_sql(sql, limit=limit)

        db_type = self._get_db_type(db_id)
        if db_type == "sqlite":
            connector = SQLiteConnector(self._get_db_path(db_id))
            try:
                return connector.execute_sql(sql, limit=limit)
            finally:
                connector.close()

        if db_type == "mysql":
            raise RuntimeError(
                f"MySQL workspace '{db_id}' 已加载，但当前会话没有数据库连接。"
                "请在左侧输入密码点击 Connect / Load MySQL，或取消 Execute SQL 只生成 SQL。"
            )

        raise ValueError(f"Unsupported db_type for execution: {db_type}")

    def connected_databases(self) -> list[dict[str, Any]]:
        rows = []
        for db_id in sorted(self.connectors):
            manifest = self.workspace.load_manifest(db_id)
            rows.append(
                {
                    "db_id": db_id,
                    "db_type": self.db_types.get(db_id, "unknown"),
                    "sql_dialect": self.sql_dialects.get(db_id, "unknown"),
                    "workspace_status": "current" if manifest else "session_only",
                    "schema_fingerprint": manifest.get("schema_fingerprint", ""),
                    "profile_done": manifest.get("profile_done", False),
                    "enriched_schema_built": manifest.get("enriched_schema_built", False),
                }
            )
        return rows

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self.workspace.list_workspaces()

    def workspace_status(self, *, db_id: str) -> dict[str, Any]:
        manifest = self.workspace.load_manifest(db_id)
        manual = self.workspace.read_schema_artifact(db_id, "manual_annotations.json", default={"tables": {}, "columns": {}})
        return {
            "manifest": manifest,
            "manual_table_annotations": len(manual.get("tables", {})),
            "manual_column_annotations": len(manual.get("columns", {})),
            "workspace_path": str(self.workspace.workspace_path(db_id)),
        }


    def list_memory_records(self, *, db_id: str, record_type: str | None = None) -> list[dict[str, Any]]:
        return self._memory(db_id).list_records(record_type)

    def delete_memory_record(self, *, db_id: str, record_type: str, record_id: str) -> dict[str, Any]:
        return self._memory(db_id).delete_record(record_type=record_type, record_id=record_id, db_id=db_id)

    def memory_file_path(self, *, db_id: str, record_type: str) -> str:
        memory = self._memory(db_id)
        memory._validate_record_type(record_type)
        return str(memory.memory_dir / memory.RECORD_FILES[record_type])

    def close(self) -> None:
        for connector in self.connectors.values():
            connector.close()
        self.connectors.clear()
        self.db_types.clear()
        self.sql_dialects.clear()

        for builder, _ in self.db_cache.values():
            builder.close()
        self.db_cache.clear()

    def _generate_sql_for_sqlite(
        self,
        *,
        question: str,
        db_id: str,
        evidence: str,
        memory_top_k: int,
        use_topology_trimming: bool | None = None,
        use_sql_structure_retrieval: bool | None = None,
        use_global_structure_examples: bool | None = None,
    ) -> Text2SQLResponse:
        raw_schema_txt = self._get_raw_schema(db_id)
        trim_schema_txt = self._get_trim_schema(db_id)
        db_path = self._get_db_path(db_id)

        memory_context = self._build_memory_context(db_id=db_id, question=question, top_k=memory_top_k)
        enriched_evidence = self._merge_evidence(
            evidence=evidence,
            memory_documentation=memory_context["memory_documentation"],
            error_fix_context=memory_context["error_fix_context"],
        )

        should_trim = Config.USE_TOPOLOGY_TRIMMING if use_topology_trimming is None else bool(use_topology_trimming)

        grads: list[Any] = []
        raw_main = ""
        raw_supp = ""
        active_nodes: list[str] = []
        relationship: list[str] = []

        if should_trim:
            _, mapper = self._get_db_handler(db_id=db_id, db_path=db_path, raw_schema_txt=raw_schema_txt)

            grads, raw_main = self.engine.call_decomposition(
                question,
                enriched_evidence,
                raw_schema_txt,
            )
            mapper.process_and_map(raw_main)

            raw_supp = self.engine.call_supplement_workflow(
                question,
                enriched_evidence,
                raw_schema_txt,
            )
            mapper.process_supplementary_info(raw_supp)
            mapper.activate_virtual_related_nodes()

            active_nodes = mapper.execute_steiner_search()
            new_schema = generate_trimmed_schema(trim_schema_txt, active_nodes)
            relationship = mapper.relationship
            generation_route = "sqlite_semantic_mapper_topology_trim"
        else:
            new_schema = trim_schema_txt
            generation_route = "sqlite_direct_enriched_schema"

        column_value_hints = self._build_value_hints_for_generation(
            db_id=db_id,
            db_type="sqlite",
            db_path=db_path,
            active_nodes=active_nodes,
            question=question,
            evidence=enriched_evidence,
            use_topology_trimming=should_trim,
        )

        examples_info = self._build_hybrid_examples(
            db_id=db_id,
            question=question,
            evidence=enriched_evidence,
            relationship=relationship,
            new_schema=new_schema,
            semantic_examples_str=memory_context["examples_str"],
            column_value_hints=column_value_hints,
            sql_dialect="SQLite",
            memory_top_k=memory_top_k,
            use_sql_structure_retrieval=use_sql_structure_retrieval,
            use_global_structure_examples=use_global_structure_examples,
        )

        sql = self.engine.call_corrected_workflow(
            question=question,
            evidence=enriched_evidence,
            relationship=relationship,
            new_schema=new_schema,
            examples=examples_info["examples_str"],
            column_value_hints=column_value_hints,
            sql_dialect="SQLite",
        )

        return Text2SQLResponse(
            question=question,
            db_id=db_id,
            evidence=evidence,
            sql=sql,
            raw_llm_response=raw_main,
            supplement_llm_response=raw_supp,
            active_schema_nodes=active_nodes,
            relationship=relationship,
            used_schema=new_schema,
            column_value_hints=column_value_hints,
            examples_used=examples_info["examples_str"],
            memory_documentation=memory_context["memory_documentation"],
            p_sql=examples_info.get("draft_sql", ""),
            metadata={
                "grads": grads,
                "db_type": "sqlite",
                "sql_dialect": "SQLite",
                "generation_route": generation_route,
                "use_topology_trimming": should_trim,
                "example_counts": examples_info.get("counts", {}),
                "use_sql_structure_retrieval": examples_info.get("use_sql_structure_retrieval", False),
            },
        )

    def _generate_sql_for_direct_schema(
        self,
        *,
        question: str,
        db_id: str,
        evidence: str,
        memory_top_k: int,
        sql_dialect: str,
        use_topology_trimming: bool | None = None,
        use_sql_structure_retrieval: bool | None = None,
        use_global_structure_examples: bool | None = None,
    ) -> Text2SQLResponse:
        memory_context = self._build_memory_context(db_id=db_id, question=question, top_k=memory_top_k)
        enriched_evidence = self._merge_evidence(
            evidence=evidence,
            memory_documentation=memory_context["memory_documentation"],
            error_fix_context=memory_context["error_fix_context"],
        )

        should_trim = Config.USE_TOPOLOGY_TRIMMING if use_topology_trimming is None else bool(use_topology_trimming)
        if should_trim:
            schema_txt, active_nodes, relationships = self._build_generic_topology_schema(
                db_id=db_id,
                question=question,
                evidence=enriched_evidence,
            )
            generation_route = "generic_schema_graph_topology_trim"
        else:
            schema_txt = self._get_trim_schema(db_id)
            active_nodes = []
            relationships = []
            generation_route = "direct_enriched_schema"

        column_value_hints = self._build_value_hints_for_generation(
            db_id=db_id,
            db_type=self._get_db_type(db_id),
            db_path=None,
            active_nodes=active_nodes,
            question=question,
            evidence=enriched_evidence,
            use_topology_trimming=should_trim,
        )

        examples_info = self._build_hybrid_examples(
            db_id=db_id,
            question=question,
            evidence=enriched_evidence,
            relationship=relationships,
            new_schema=schema_txt,
            semantic_examples_str=memory_context["examples_str"],
            column_value_hints=column_value_hints,
            sql_dialect=sql_dialect,
            memory_top_k=memory_top_k,
            use_sql_structure_retrieval=use_sql_structure_retrieval,
            use_global_structure_examples=use_global_structure_examples,
        )

        sql = self.engine.call_corrected_workflow(
            question=question,
            evidence=enriched_evidence,
            relationship=relationships,
            new_schema=schema_txt,
            examples=examples_info["examples_str"],
            column_value_hints=column_value_hints,
            sql_dialect=sql_dialect,
        )

        return Text2SQLResponse(
            question=question,
            db_id=db_id,
            evidence=evidence,
            sql=sql,
            raw_llm_response="",
            supplement_llm_response="",
            active_schema_nodes=active_nodes,
            relationship=relationships,
            used_schema=schema_txt,
            column_value_hints=column_value_hints,
            examples_used=examples_info["examples_str"],
            memory_documentation=memory_context["memory_documentation"],
            p_sql=examples_info.get("draft_sql", ""),
            metadata={
                "db_type": self._get_db_type(db_id),
                "sql_dialect": sql_dialect,
                "generation_route": generation_route,
                "use_topology_trimming": should_trim,
                "example_counts": examples_info.get("counts", {}),
                "use_sql_structure_retrieval": examples_info.get("use_sql_structure_retrieval", False),
            },
        )

    def _build_memory_context(self, *, db_id: str, question: str, top_k: int) -> dict[str, str]:
        memory = self._memory(db_id)
        docs = memory.retrieve_documentation(db_id=db_id, question=question, top_k=top_k)
        question_sql_examples = memory.retrieve_question_sql(db_id=db_id, question=question, top_k=top_k)
        error_fixes = memory.retrieve_error_fixes(db_id=db_id, question=question, top_k=top_k)

        memory_documentation = memory.format_documentation(docs)
        a_examples = [{**item, "example_source": "A_text_same_workspace"} for item in question_sql_examples]
        examples_str = HybridExampleRetriever.format_examples(a_examples, [], [])
        error_fix_context = memory.format_error_fixes(error_fixes)

        return {
            "memory_documentation": memory_documentation,
            "examples_str": examples_str,
            "error_fix_context": error_fix_context,
        }

    def _build_hybrid_examples(
        self,
        *,
        db_id: str,
        question: str,
        evidence: str,
        relationship,
        new_schema: str,
        semantic_examples_str: str,
        column_value_hints: str,
        sql_dialect: str,
        memory_top_k: int,
        use_sql_structure_retrieval: bool | None,
        use_global_structure_examples: bool | None,
    ) -> dict[str, Any]:
        should_use_structure = Config.USE_SQL_STRUCTURE_RETRIEVAL if use_sql_structure_retrieval is None else bool(use_sql_structure_retrieval)
        should_use_global = Config.USE_GLOBAL_STRUCTURE_EXAMPLES if use_global_structure_examples is None else bool(use_global_structure_examples)
        if not should_use_structure:
            return {
                "examples_str": semantic_examples_str,
                "draft_sql": "",
                "counts": {"A": 0 if semantic_examples_str == "No valid examples found." else "text_only", "B": 0, "C": 0},
                "use_sql_structure_retrieval": False,
            }

        draft_sql = self.engine.call_draft_sql_workflow(
            question=question,
            evidence=evidence,
            relationship=relationship,
            new_schema=new_schema,
            examples=semantic_examples_str,
            column_value_hints=column_value_hints,
            sql_dialect=sql_dialect,
        )
        hybrid = HybridExampleRetriever(memory=self._memory(db_id)).retrieve(
            db_id=db_id,
            question=question,
            draft_sql=draft_sql,
            total_top_k=memory_top_k,
            text_top_k=memory_top_k,
            workspace_structure_top_k=memory_top_k,
            use_sql_structure_retrieval=True,
            use_global_structure_examples=should_use_global,
        )
        hybrid["draft_sql"] = draft_sql
        hybrid["use_sql_structure_retrieval"] = True
        return hybrid

    def _build_generic_topology_schema(self, *, db_id: str, question: str, evidence: str) -> tuple[str, list[str], list[str]]:
        enriched = self.workspace.read_schema_artifact(db_id, "enriched_schema.json", default={})
        profile = self.workspace.read_schema_artifact(db_id, "table_profile.json", default={})
        if not enriched:
            raise RuntimeError(f"Missing enriched_schema.json for db_id={db_id}; connect database first.")
        graph_builder = SchemaGraphBuilder(enriched_schema=enriched, table_profile=profile)
        graph = graph_builder.build()
        trimmer = TopologyTrimmer(graph=graph, node_metadata=graph_builder.node_metadata)
        activated = trimmer.activate_nodes(question=question, evidence=evidence, top_k=18)
        selected = trimmer.trim(activated_nodes=activated, max_nodes=90)
        schema_txt = trimmer.format_schema(
            selected_nodes=selected,
            enriched_schema=enriched,
            relationships=graph_builder.relationships,
        )
        if not schema_txt.strip():
            schema_txt = self._get_trim_schema(db_id)
        return schema_txt, selected, graph_builder.relationships

    def _build_value_hints_for_generation(
        self,
        *,
        db_id: str,
        db_type: str,
        db_path,
        active_nodes: list[str],
        question: str,
        evidence: str,
        use_topology_trimming: bool,
    ) -> str:
        if use_topology_trimming and active_nodes:
            hint_nodes = active_nodes
        else:
            hint_nodes = self._infer_value_hint_nodes_from_workspace(
                db_id=db_id,
                question=question,
                evidence=evidence,
                max_columns=24,
            )

        if db_type == "sqlite":
            if db_path is None:
                db_path = self._get_db_path(db_id)

            return build_column_value_hints(
                db_path=db_path,
                active_nodes=hint_nodes,
                question=question,
                evidence=evidence,
                value_limit_per_column=3,
                matched_value_limit_per_column=5,
                max_distinct_scan_per_column=5000,
                match_threshold=0.88,
            )

        return self._build_connector_value_hints(
            db_id=db_id,
            active_nodes=hint_nodes,
            question=question,
            evidence=evidence,
        )

    def _infer_value_hint_nodes_from_workspace(
        self,
        *,
        db_id: str,
        question: str,
        evidence: str,
        max_columns: int = 24,
    ) -> list[str]:
        raw_schema = self._get_raw_schema_metadata(db_id)
        profile = self.workspace.read_schema_artifact(db_id, "table_profile.json", default={})
        enriched = self.workspace.read_schema_artifact(db_id, "enriched_schema.json", default={})

        query_text = f"{question}\n{evidence}".lower()
        candidates: list[tuple[float, str]] = []

        profile_tables_raw = profile.get("tables", []) if isinstance(profile, dict) else []
        if isinstance(profile_tables_raw, list):
            table_profiles = {str(t.get("name", "")): t for t in profile_tables_raw if isinstance(t, dict)}
        elif isinstance(profile_tables_raw, dict):
            table_profiles = profile_tables_raw
        else:
            table_profiles = {}

        enriched_tables_raw = enriched.get("tables", []) if isinstance(enriched, dict) else []
        if isinstance(enriched_tables_raw, list):
            enriched_tables = {str(t.get("name", "")): t for t in enriched_tables_raw if isinstance(t, dict)}
        elif isinstance(enriched_tables_raw, dict):
            enriched_tables = enriched_tables_raw
        else:
            enriched_tables = {}

        for table in raw_schema.get("tables", []) or []:
            table_name = str(table.get("name", "")).strip()
            if not table_name:
                continue

            table_comment = ""
            table_enriched = enriched_tables.get(table_name, {}) if isinstance(enriched_tables, dict) else {}
            if isinstance(table_enriched, dict):
                table_comment = str(table_enriched.get("comment", ""))

            for col in table.get("columns", []) or []:
                col_name = str(col.get("name", "")).strip()
                if not col_name:
                    continue

                col_type = str(col.get("type", "")).lower()
                col_comment = str(col.get("comment", "") or col.get("db_comment", ""))

                enriched_col_comment = ""
                enriched_columns_raw = table_enriched.get("columns", {}) if isinstance(table_enriched, dict) else {}
                if isinstance(enriched_columns_raw, list):
                    enriched_columns = {str(c.get("name", "")): c for c in enriched_columns_raw if isinstance(c, dict)}
                elif isinstance(enriched_columns_raw, dict):
                    enriched_columns = enriched_columns_raw
                else:
                    enriched_columns = {}
                enriched_col = enriched_columns.get(col_name, {})
                if isinstance(enriched_col, dict):
                    enriched_col_comment = str(enriched_col.get("final_comment", "") or enriched_col.get("comment", ""))

                profile_text = ""
                table_profile = table_profiles.get(table_name, {}) if isinstance(table_profiles, dict) else {}
                column_profiles_raw = table_profile.get("columns", {}) if isinstance(table_profile, dict) else {}
                if isinstance(column_profiles_raw, list):
                    column_profiles = {str(c.get("name", "")): c for c in column_profiles_raw if isinstance(c, dict)}
                elif isinstance(column_profiles_raw, dict):
                    column_profiles = column_profiles_raw
                else:
                    column_profiles = {}
                column_profile = column_profiles.get(col_name, {})
                if isinstance(column_profile, dict):
                    sample_values = column_profile.get("sample_values", []) or column_profile.get("samples", []) or []
                    profile_text = " ".join(str(v) for v in sample_values[:8])

                searchable = " ".join(
                    [
                        table_name,
                        col_name,
                        col_type,
                        table_comment,
                        col_comment,
                        enriched_col_comment,
                        profile_text,
                    ]
                ).lower()

                score = 0.0

                for token in [table_name, col_name]:
                    token_norm = str(token).replace("_", " ").lower()
                    if token_norm and token_norm in query_text:
                        score += 5.0

                for word in set(query_text.replace("`", " ").replace(".", " ").split()):
                    if len(word) < 2:
                        continue
                    if word in searchable:
                        score += 1.0

                if any(x in col_type for x in ["char", "text", "enum", "varchar"]):
                    score += 2.0

                name_l = col_name.lower()
                if any(x in name_l for x in ["name", "type", "status", "state", "city", "county", "category", "brand", "code"]):
                    score += 2.0

                has_numeric_condition = any(
                    x in query_text
                    for x in ["more than", "less than", "not more than", ">", "<", "至少", "最多", "大于", "小于", "不超过", "不少于"]
                )
                if any(x in col_type for x in ["int", "decimal", "double", "float", "numeric", "real"]):
                    score += 1.5 if has_numeric_condition else -1.0

                if score > 0:
                    candidates.append((score, f"{table_name}.{col_name}"))

        candidates.sort(key=lambda x: (-x[0], x[1]))

        result: list[str] = []
        seen: set[str] = set()
        for _, node in candidates:
            if node in seen:
                continue
            seen.add(node)
            result.append(node)
            if len(result) >= max_columns:
                break

        return result

    def _build_connector_value_hints(
        self,
        *,
        db_id: str,
        active_nodes: list[str],
        question: str,
        evidence: str,
    ) -> str:
        connector = self.connectors.get(db_id)
        if connector is None:
            return "当前会话没有活动数据库连接，无法生成列值提示。SQLite workspace 可自动重连；MySQL 请在左侧输入密码并连接后再执行。"
        raw_schema = self._get_raw_schema_metadata(db_id)
        return build_connector_column_value_hints(
            connector=connector,
            raw_schema=raw_schema,
            active_nodes=active_nodes,
            question=question,
            evidence=evidence,
            value_limit_per_column=3,
            matched_value_limit_per_column=5,
            max_distinct_scan_per_column=3000,
            match_threshold=0.88,
        )

    @staticmethod
    def _merge_evidence(*, evidence: str, memory_documentation: str, error_fix_context: str) -> str:
        parts = [part for part in [evidence, memory_documentation, error_fix_context] if part]
        return "\n\n".join(parts)

    def _memory(self, db_id: str) -> MemoryStore:
        if db_id in self.memories:
            return self.memories[db_id]
        if self.workspace.has_workspace(db_id):
            self.memories[db_id] = MemoryStore(self.workspace.memory_dir(db_id))
            return self.memories[db_id]
        return self.default_memory

    def _get_raw_schema(self, db_id: str) -> str:
        if db_id not in self.raw_schema_cache:
            workspace_schema = self.workspace.read_schema_artifact(db_id, "enriched_schema.sql", default="")
            if workspace_schema:
                self.raw_schema_cache[db_id] = workspace_schema
            else:
                self.raw_schema_cache[db_id] = read_text(resolve_raw_schema_file_path(db_id))
        return self.raw_schema_cache[db_id]

    def _get_trim_schema(self, db_id: str) -> str:
        if db_id not in self.trim_schema_cache:
            workspace_schema = self.workspace.read_schema_artifact(db_id, "enriched_schema.sql", default="")
            if workspace_schema:
                self.trim_schema_cache[db_id] = workspace_schema
            else:
                self.trim_schema_cache[db_id] = read_text(resolve_trim_schema_file_path(db_id))
        return self.trim_schema_cache[db_id]

    def _get_raw_schema_metadata(self, db_id: str) -> dict[str, Any]:
        if db_id in self.raw_schema_metadata_cache:
            return self.raw_schema_metadata_cache[db_id]
        raw_schema = self.workspace.read_schema_artifact(db_id, "raw_schema.json", default={})
        if not raw_schema:
            raise RuntimeError(f"找不到 db_id={db_id} 的 raw_schema.json，请先连接数据库")
        self.raw_schema_metadata_cache[db_id] = raw_schema
        return raw_schema

    def _get_db_type(self, db_id: str) -> str:
        if db_id in self.db_types:
            return self.db_types[db_id]
        manifest = self.workspace.load_manifest(db_id)
        if manifest.get("db_type"):
            return manifest["db_type"]
        return "sqlite"

    def _get_db_path(self, db_id: str) -> Path:
        connector = self.connectors.get(db_id)
        if isinstance(connector, SQLiteConnector):
            return connector.db_path
        if connector is not None:
            raise ValueError(f"db_id={db_id} 不是 SQLite 连接，不能使用 SQLite 图拓扑链路")

        registry = self.workspace.load_registry().get("databases", {})
        info = registry.get(db_id, {})
        if info.get("db_type") == "sqlite" and info.get("db_path"):
            path = Path(info["db_path"])
            if path.exists():
                return path

        db_path = Config.DB_ROOT_DIR / db_id / f"{db_id}.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"SQLite database not found for db_id={db_id}: {db_path}")
        return db_path

    def _get_db_handler(
        self,
        *,
        db_id: str,
        db_path: str | Path,
        raw_schema_txt: str,
    ) -> tuple[TopologyGraphBuilder, SemanticHeatMapper]:
        if db_id in self.db_cache:
            return self.db_cache[db_id]

        builder = TopologyGraphBuilder(str(db_path), raw_schema_txt)
        builder.build_structure()
        mapper = SemanticHeatMapper(builder)
        self.db_cache[db_id] = (builder, mapper)
        return builder, mapper
