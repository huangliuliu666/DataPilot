import json
from pathlib import Path
from typing import Any

from config import Config


def load_json(path: str | Path) -> Any:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(
    path: str | Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    path = Path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)


def read_text(path: str | Path) -> str:
    path = Path(path)
    return path.read_text(encoding="utf-8")


def resolve_raw_schema_file_path(db_id: str) -> Path:
    path = Config.SCHEMA_DIR / f"{db_id}{Config.RAW_SCHEMA_SUFFIX}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Raw schema file not found: {path}")
    return path


def resolve_trim_schema_file_path(db_id: str) -> Path:
    path = Config.SCHEMA_DIR / f"{db_id}{Config.TRIM_SCHEMA_SUFFIX}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Trim schema file not found: {path}")
    return path