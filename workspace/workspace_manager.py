from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Config


class WorkspaceManager:

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or Config.WORKSPACE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.base_dir / "registry.json"
        if not self.registry_path.exists():
            self._write_json(self.registry_path, {"databases": {}})

    @staticmethod
    def normalize_db_id(db_id: str) -> str:
        text = str(db_id or "").strip()
        if not text:
            raise ValueError("db_id 不能为空")
        text = re.sub(r"[^0-9A-Za-z_\-.\u4e00-\u9fff]+", "_", text)
        return text.strip("_") or "database"

    def workspace_path(self, db_id: str) -> Path:
        return self.base_dir / self.normalize_db_id(db_id)

    def memory_dir(self, db_id: str) -> Path:
        path = self.workspace_path(db_id) / "memory"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def schema_dir(self, db_id: str) -> Path:
        path = self.workspace_path(db_id) / "schema"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def logs_dir(self, db_id: str) -> Path:
        path = self.workspace_path(db_id) / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_workspace(self, db_id: str) -> Path:
        root = self.workspace_path(db_id)
        (root / "schema").mkdir(parents=True, exist_ok=True)
        (root / "memory").mkdir(parents=True, exist_ok=True)
        (root / "vector_index").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        return root

    def has_workspace(self, db_id: str) -> bool:
        root = self.workspace_path(db_id)
        return root.exists() and (root / "manifest.json").exists()

    def load_registry(self) -> dict[str, Any]:
        return self._read_json(self.registry_path, default={"databases": {}})

    def save_registry(self, registry: dict[str, Any]) -> None:
        self._write_json(self.registry_path, registry)

    def list_workspaces(self) -> list[dict[str, Any]]:
        registry = self.load_registry()
        databases = registry.get("databases", {})
        items = []
        for db_id, info in sorted(databases.items()):
            manifest = self.load_manifest(db_id)
            merged = {"db_id": db_id, **info}
            if manifest:
                merged.update(
                    {
                        "db_type": manifest.get("db_type", merged.get("db_type")),
                        "schema_fingerprint": manifest.get("schema_fingerprint"),
                        "profile_done": manifest.get("profile_done", False),
                        "auto_annotation_done": manifest.get("auto_annotation_done", False),
                        "enriched_schema_built": manifest.get("enriched_schema_built", False),
                        "last_built_at": manifest.get("last_built_at"),
                    }
                )
            items.append(merged)
        return items

    def load_manifest(self, db_id: str) -> dict[str, Any]:
        return self._read_json(self.workspace_path(db_id) / "manifest.json", default={})

    def save_manifest(self, db_id: str, manifest: dict[str, Any]) -> None:
        self.ensure_workspace(db_id)
        now = datetime.now(timezone.utc).isoformat()
        old_manifest = self.load_manifest(db_id)
        merged = {
            **old_manifest,
            **manifest,
            "db_id": db_id,
            "updated_at": now,
        }
        if "created_at" not in merged:
            merged["created_at"] = now
        self._write_json(self.workspace_path(db_id) / "manifest.json", merged)

    def update_registry(self, db_id: str, info: dict[str, Any]) -> None:
        registry = self.load_registry()
        databases = registry.setdefault("databases", {})
        old = databases.get(db_id, {})
        safe_info = self._sanitize_connection_info(info)
        databases[db_id] = {
            **old,
            **safe_info,
            "db_id": db_id,
            "workspace_path": str(self.workspace_path(db_id)),
            "last_connected_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_registry(registry)

    def is_workspace_current(self, db_id: str, schema_fingerprint: str) -> bool:
        manifest = self.load_manifest(db_id)
        if not manifest:
            return False
        schema_dir = self.schema_dir(db_id)
        required = [
            schema_dir / "raw_schema.json",
            schema_dir / "table_profile.json",
            schema_dir / "auto_annotations.json",
            schema_dir / "enriched_schema.json",
            schema_dir / "enriched_schema.sql",
            schema_dir / "enriched_schema.md",
        ]
        return (
            manifest.get("schema_fingerprint") == schema_fingerprint
            and all(path.exists() for path in required)
            and bool(manifest.get("enriched_schema_built"))
        )

    def write_schema_artifact(self, db_id: str, name: str, data: Any) -> Path:
        path = self.schema_dir(db_id) / name
        if name.endswith(".json"):
            self._write_json(path, data)
        else:
            path.write_text(str(data), encoding="utf-8")
        return path

    def read_schema_artifact(self, db_id: str, name: str, default: Any = None) -> Any:
        path = self.schema_dir(db_id) / name
        if not path.exists():
            return default
        if name.endswith(".json"):
            return self._read_json(path, default=default)
        return path.read_text(encoding="utf-8")

    @staticmethod
    def schema_fingerprint(raw_schema_metadata: dict[str, Any]) -> str:
        normalized = WorkspaceManager._stable_schema_payload(raw_schema_metadata)
        payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _stable_schema_payload(raw_schema_metadata: dict[str, Any]) -> dict[str, Any]:
        tables_payload = []
        for table in raw_schema_metadata.get("tables", []):
            columns_payload = []
            for col in table.get("columns", []):
                columns_payload.append(
                    {
                        "name": col.get("name"),
                        "type": col.get("type"),
                        "nullable": col.get("nullable"),
                        "default": col.get("default"),
                        "is_primary_key": col.get("is_primary_key"),
                        "db_comment": col.get("db_comment", ""),
                    }
                )
            columns_payload.sort(key=lambda x: str(x.get("name", "")).lower())
            fk_payload = sorted(table.get("foreign_keys", []), key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
            tables_payload.append(
                {
                    "name": table.get("name"),
                    "type": table.get("type", "table"),
                    "db_comment": table.get("db_comment", ""),
                    "columns": columns_payload,
                    "primary_keys": sorted(table.get("primary_keys", [])),
                    "foreign_keys": fk_payload,
                }
            )
        tables_payload.sort(key=lambda x: str(x.get("name", "")).lower())
        return {"db_type": raw_schema_metadata.get("db_type"), "tables": tables_payload}

    @staticmethod
    def _sanitize_connection_info(info: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(info)
        for key in list(sanitized):
            if "password" in key.lower() or "token" in key.lower() or "secret" in key.lower():
                sanitized.pop(key)
        return sanitized

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
