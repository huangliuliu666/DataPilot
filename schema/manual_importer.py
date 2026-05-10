from __future__ import annotations

import json
import re
from typing import Any


class ManualAnnotationImporter:

    TABLE_RE = re.compile(
        r"^\s*(?:Table|表)\s*[:：]\s*[`\"']?([^:`\"'：]+)[`\"']?\s*(?:[:：]\s*(.*))?$",
        re.IGNORECASE,
    )
    QUALIFIED_RE = re.compile(
        r"^\s*(?:[-*]\s*)?[`\"']?([^.`\"']+)[`\"']?\s*\.\s*[`\"']?([^:`\"']+)[`\"']?\s*[:：]\s*(.+?)\s*$"
    )
    SIMPLE_RE = re.compile(r"^\s*(?:[-*]\s*)?[`\"']?([^:`\"']+)[`\"']?\s*[:：]\s*(.+?)\s*$")

    CONSTRAINT_PREFIXES = (
        "PRIMARY", "FOREIGN", "UNIQUE", "KEY", "INDEX", "CONSTRAINT", "CHECK", "FULLTEXT", "SPATIAL"
    )

    def parse(self, text: str, raw_schema: dict[str, Any]) -> dict[str, Any]:
        table_lookup, column_lookup = self._build_schema_lookups(raw_schema)
        text = str(text or "").strip()
        if not text:
            return {"tables": {}, "columns": {}, "unmatched_lines": []}

        if text.lstrip().startswith(("{", "[")):
            return self._parse_json(text, table_lookup, column_lookup)

        sql_result = self._parse_sql_comment_schema(text, table_lookup, column_lookup)
        plain_result = self._parse_plain_text_schema(text, table_lookup, column_lookup)

                                                             
        tables = {**sql_result.get("tables", {})}
        columns = {**sql_result.get("columns", {})}
        for key, value in plain_result.get("tables", {}).items():
            tables.setdefault(key, value)
        for key, value in plain_result.get("columns", {}).items():
            columns.setdefault(key, value)

        if tables or columns:
                                                                           
            unmatched = sql_result.get("unmatched_lines", [])
        else:
            unmatched = [*sql_result.get("unmatched_lines", []), *plain_result.get("unmatched_lines", [])]

        return {"tables": tables, "columns": columns, "unmatched_lines": unmatched}

                                                                        
                 
                                                                        
    def _parse_json(
        self,
        text: str,
        table_lookup: dict[str, str],
        column_lookup: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 注释格式解析失败: {exc}") from exc

        tables: dict[str, dict[str, Any]] = {}
        columns: dict[str, dict[str, Any]] = {}
        unmatched: list[str] = []

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    unmatched.append(str(item))
                    continue
                raw_table = item.get("table") or item.get("table_name")
                raw_column = item.get("column") or item.get("column_name")
                comment = item.get("comment") or item.get("description") or item.get("annotation")
                if raw_table and comment and not raw_column:
                    table = self._resolve_table(raw_table, table_lookup)
                    if table:
                        tables[table] = self._record(comment)
                    else:
                        unmatched.append(json.dumps(item, ensure_ascii=False))
                elif raw_table and raw_column and comment:
                    table = self._resolve_table(raw_table, table_lookup)
                    column = self._resolve_column(table, raw_column, column_lookup) if table else None
                    if table and column:
                        columns[f"{table}.{column}"] = self._record(comment)
                    else:
                        unmatched.append(json.dumps(item, ensure_ascii=False))
                else:
                    unmatched.append(json.dumps(item, ensure_ascii=False))
            return {"tables": tables, "columns": columns, "unmatched_lines": unmatched}

        if not isinstance(data, dict):
            raise ValueError("JSON 注释格式必须是 object 或 list")

                                                              
        if "tables" in data or "columns" in data:
            for raw_table, value in (data.get("tables") or {}).items():
                table = self._resolve_table(raw_table, table_lookup)
                comment = self._extract_comment(value)
                if table and comment:
                    tables[table] = self._record(comment)
                elif comment:
                    unmatched.append(f"table:{raw_table}")

            for raw_key, value in (data.get("columns") or {}).items():
                comment = self._extract_comment(value)
                if not comment:
                    continue
                table, column = self._resolve_qualified_column(raw_key, table_lookup, column_lookup)
                if table and column:
                    columns[f"{table}.{column}"] = self._record(comment)
                else:
                    unmatched.append(f"column:{raw_key}")
            return {"tables": tables, "columns": columns, "unmatched_lines": unmatched}

                                                                              
        for raw_table, value in data.items():
            table = self._resolve_table(raw_table, table_lookup)
            if not table:
                unmatched.append(str(raw_table))
                continue

            if isinstance(value, str):
                tables[table] = self._record(value)
                continue

            if isinstance(value, dict):
                table_comment = self._extract_comment(value.get("comment") or value.get("table_comment") or value.get("description"))
                if table_comment:
                    tables[table] = self._record(table_comment)

                column_block = value.get("columns") if isinstance(value.get("columns"), (dict, list)) else value
                if isinstance(column_block, dict):
                    for raw_column, comment_value in column_block.items():
                        if str(raw_column).lower() in {"comment", "table_comment", "description", "columns"}:
                            continue
                        comment = self._extract_comment(comment_value)
                        column = self._resolve_column(table, raw_column, column_lookup)
                        if column and comment:
                            columns[f"{table}.{column}"] = self._record(comment)
                        elif comment:
                            unmatched.append(f"{raw_table}.{raw_column}")
                elif isinstance(column_block, list):
                    for item in column_block:
                        if not isinstance(item, dict):
                            unmatched.append(str(item))
                            continue
                        raw_column = item.get("column") or item.get("name")
                        comment = self._extract_comment(item)
                        column = self._resolve_column(table, raw_column, column_lookup) if raw_column else None
                        if column and comment:
                            columns[f"{table}.{column}"] = self._record(comment)
                        elif comment:
                            unmatched.append(json.dumps(item, ensure_ascii=False))

        return {"tables": tables, "columns": columns, "unmatched_lines": unmatched}

                                                                        
                        
                                                                        
    def _parse_sql_comment_schema(
        self,
        text: str,
        table_lookup: dict[str, str],
        column_lookup: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        tables: dict[str, dict[str, Any]] = {}
        columns: dict[str, dict[str, Any]] = {}
        unmatched: list[str] = []

        statements = self._extract_create_table_statements(text)
        for statement in statements:
            header, body, suffix = self._split_create_table_statement(statement)
            if not header or body is None:
                continue

            raw_table = self._extract_table_name_from_header(header)
            table = self._resolve_table(raw_table, table_lookup) if raw_table else None
            if not table:
                unmatched.append(header.strip())
                continue

            table_comment = self._find_comment(suffix)
            if table_comment:
                tables[table] = self._record(table_comment)

            for definition in self._split_top_level_commas(body):
                definition = definition.strip().rstrip(",")
                if not definition:
                    continue
                if self._is_table_constraint(definition):
                    continue

                raw_column = self._extract_column_name(definition)
                comment = self._find_comment(definition)
                if not comment:
                    continue

                column = self._resolve_column(table, raw_column, column_lookup) if raw_column else None
                if column:
                    columns[f"{table}.{column}"] = self._record(comment)
                else:
                    unmatched.append(definition)

                                                                  
        if not statements:
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if "COMMENT" in line.upper():
                    unmatched.append(raw_line)

        return {"tables": tables, "columns": columns, "unmatched_lines": unmatched}

    def _extract_create_table_statements(self, text: str) -> list[str]:
        pattern = re.compile(
            r"\bCREATE\s+(?:TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
            re.IGNORECASE,
        )
        statements: list[str] = []
        pos = 0
        while True:
            match = pattern.search(text, pos)
            if not match:
                break
            open_paren = text.find("(", match.end())
            if open_paren == -1:
                break
            close_paren = self._find_matching_paren(text, open_paren)
            if close_paren == -1:
                pos = match.end()
                continue
            semicolon = self._find_statement_end(text, close_paren + 1)
            end = semicolon + 1 if semicolon != -1 else close_paren + 1
            statements.append(text[match.start():end])
            pos = end
        return statements

    def _split_create_table_statement(self, statement: str) -> tuple[str, str | None, str]:
        open_paren = statement.find("(")
        if open_paren == -1:
            return statement, None, ""
        close_paren = self._find_matching_paren(statement, open_paren)
        if close_paren == -1:
            return statement[:open_paren], None, ""
        return statement[:open_paren], statement[open_paren + 1:close_paren], statement[close_paren + 1:]

    def _extract_table_name_from_header(self, header: str) -> str | None:
        header = re.sub(
            r"^\s*CREATE\s+(?:TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
            "",
            header,
            flags=re.IGNORECASE,
        ).strip()
        if not header:
            return None
        parts = self._split_qualified_identifier(header)
        return parts[-1] if parts else None

    def _extract_column_name(self, definition: str) -> str | None:
        text = definition.strip()
        if not text:
            return None
        if text[0] == "`":
            end = self._find_closing_backtick(text, 1)
            if end != -1:
                return text[1:end].replace("``", "`")
        if text[0] == '"':
            end = text.find('"', 1)
            if end != -1:
                return text[1:end]
        if text[0] == "[":
            end = text.find("]", 1)
            if end != -1:
                return text[1:end]
        match = re.match(r"([^\s,()]+)", text)
        return match.group(1).strip("`\"[]") if match else None

    def _find_comment(self, text: str) -> str | None:
                                                                    
        pattern = re.compile(r"\bCOMMENT\s*(?:=)?\s*('(?:''|[^'])*'|\"(?:\\\"|[^\"])*\")", re.IGNORECASE | re.DOTALL)
        match = pattern.search(text or "")
        if not match:
            return None
        raw = match.group(1)
        if raw.startswith("'"):
            return raw[1:-1].replace("''", "'").strip()
        if raw.startswith('"'):
            return raw[1:-1].replace('\\"', '"').strip()
        return raw.strip()

    def _is_table_constraint(self, definition: str) -> bool:
        first = definition.strip().split(None, 1)[0].strip("`\"[]").upper() if definition.strip() else ""
        return first in self.CONSTRAINT_PREFIXES

    def _split_top_level_commas(self, text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        i = 0
        while i < len(text):
            ch = text[i]
            if quote == "'":
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2
                        continue
                    quote = None
                i += 1
                continue
            if quote == '"':
                if ch == '"':
                    quote = None
                i += 1
                continue
            if quote == "`":
                if ch == "`":
                    quote = None
                i += 1
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                parts.append(text[start:i])
                start = i + 1
            i += 1
        parts.append(text[start:])
        return parts

    def _find_matching_paren(self, text: str, open_pos: int) -> int:
        depth = 0
        quote: str | None = None
        i = open_pos
        while i < len(text):
            ch = text[i]
            if quote == "'":
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2
                        continue
                    quote = None
                i += 1
                continue
            if quote == '"':
                if ch == '"':
                    quote = None
                i += 1
                continue
            if quote == "`":
                if ch == "`":
                    quote = None
                i += 1
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1

    def _find_statement_end(self, text: str, start: int) -> int:
        quote: str | None = None
        i = start
        while i < len(text):
            ch = text[i]
            if quote == "'":
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2
                        continue
                    quote = None
                i += 1
                continue
            if quote == '"':
                if ch == '"':
                    quote = None
                i += 1
                continue
            if quote == "`":
                if ch == "`":
                    quote = None
                i += 1
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
            elif ch == ";":
                return i
            i += 1
        return -1

    def _find_closing_backtick(self, text: str, start: int) -> int:
        i = start
        while i < len(text):
            if text[i] == "`":
                if i + 1 < len(text) and text[i + 1] == "`":
                    i += 2
                    continue
                return i
            i += 1
        return -1

    def _split_qualified_identifier(self, text: str) -> list[str]:
        text = text.strip()
        parts: list[str] = []
        token = []
        quote: str | None = None
        i = 0
        while i < len(text):
            ch = text[i]
            if quote == "`":
                if ch == "`":
                    if i + 1 < len(text) and text[i + 1] == "`":
                        token.append("`")
                        i += 2
                        continue
                    quote = None
                else:
                    token.append(ch)
                i += 1
                continue
            if quote in {'"', '['}:
                closing = '"' if quote == '"' else ']'
                if ch == closing:
                    quote = None
                else:
                    token.append(ch)
                i += 1
                continue
            if ch == "`":
                quote = "`"
            elif ch == '"':
                quote = '"'
            elif ch == '[':
                quote = '['
            elif ch == ".":
                if token:
                    parts.append("".join(token).strip())
                    token = []
            elif ch.isspace():
                if token:
                    parts.append("".join(token).strip())
                break
            else:
                token.append(ch)
            i += 1
        if token:
            parts.append("".join(token).strip())
        return [part for part in parts if part]

                                                                        
                       
                                                                        
    def _parse_plain_text_schema(
        self,
        text: str,
        table_lookup: dict[str, str],
        column_lookup: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        tables: dict[str, dict[str, Any]] = {}
        columns: dict[str, dict[str, Any]] = {}
        unmatched: list[str] = []
        current_table: str | None = None

        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("--"):
                continue
            if re.match(r"^\s*CREATE\s+TABLE\b", line, re.IGNORECASE):
                continue

            table_match = self.TABLE_RE.match(line)
            if table_match:
                table = self._resolve_table(table_match.group(1), table_lookup)
                if table:
                    current_table = table
                    comment = (table_match.group(2) or "").strip()
                    if comment:
                        tables[table] = self._record(comment)
                    continue
                unmatched.append(raw_line)
                continue

            qualified_match = self.QUALIFIED_RE.match(line)
            if qualified_match:
                table = self._resolve_table(qualified_match.group(1), table_lookup)
                column = self._resolve_column(table, qualified_match.group(2), column_lookup) if table else None
                if table and column:
                    columns[f"{table}.{column}"] = self._record(qualified_match.group(3).strip())
                    current_table = table
                    continue
                unmatched.append(raw_line)
                continue

            simple_match = self.SIMPLE_RE.match(line)
            if simple_match:
                lhs = simple_match.group(1).strip()
                rhs = simple_match.group(2).strip()
                table = self._resolve_table(lhs, table_lookup)
                if table and current_table is None:
                    current_table = table
                    tables[table] = self._record(rhs)
                    continue
                if current_table:
                    column = self._resolve_column(current_table, lhs, column_lookup)
                    if column:
                        columns[f"{current_table}.{column}"] = self._record(rhs)
                        continue

                                                                                     
            if "COMMENT" not in line.upper():
                unmatched.append(raw_line)

        return {"tables": tables, "columns": columns, "unmatched_lines": unmatched}

                                                                        
                          
                                                                        
    def _build_schema_lookups(self, raw_schema: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        table_lookup: dict[str, str] = {}
        column_lookup: dict[str, dict[str, str]] = {}
        for table in raw_schema.get("tables", []):
            table_name = str(table.get("name", ""))
            if not table_name:
                continue
            for key in self._lookup_keys(table_name):
                table_lookup[key] = table_name
            column_lookup[table_name] = {}
            for col in table.get("columns", []):
                col_name = str(col.get("name", ""))
                for key in self._lookup_keys(col_name):
                    column_lookup[table_name][key] = col_name
        return table_lookup, column_lookup

    def _resolve_table(self, name: Any, table_lookup: dict[str, str]) -> str | None:
        if name is None:
            return None
        for key in self._lookup_keys(str(name)):
            if key in table_lookup:
                return table_lookup[key]
        return None

    def _resolve_column(self, table: str | None, name: Any, column_lookup: dict[str, dict[str, str]]) -> str | None:
        if table is None or name is None:
            return None
        lookup = column_lookup.get(table, {})
        for key in self._lookup_keys(str(name)):
            if key in lookup:
                return lookup[key]
        return None

    def _resolve_qualified_column(
        self,
        key: str,
        table_lookup: dict[str, str],
        column_lookup: dict[str, dict[str, str]],
    ) -> tuple[str | None, str | None]:
        parts = self._split_qualified_identifier(str(key))
        if len(parts) >= 2:
            table = self._resolve_table(parts[-2], table_lookup)
            column = self._resolve_column(table, parts[-1], column_lookup) if table else None
            return table, column
        return None, None

    def _lookup_keys(self, value: str) -> list[str]:
        clean = str(value or "").strip().strip("`\"'[]")
        compact = re.sub(r"[\s_\-]+", "", clean).lower()
        return [clean.lower(), compact]

    @staticmethod
    def _record(comment: Any) -> dict[str, Any]:
        return {"comment": str(comment or "").strip(), "source": "manual"}

    @staticmethod
    def _extract_comment(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("comment", "description", "annotation", "manual_comment", "final_comment"):
                if value.get(key):
                    return str(value[key]).strip()
        return str(value).strip()

    @staticmethod
    def merge_manual_annotations(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
        old = old or {"tables": {}, "columns": {}, "unmatched_lines": []}
        old_tables = dict(old.get("tables", {}) or {})
        old_columns = dict(old.get("columns", {}) or {})
        merged_tables = {**old_tables, **(new.get("tables", {}) or {})}
        merged_columns = {**old_columns, **(new.get("columns", {}) or {})}

        unmatched: list[str] = []
        seen: set[str] = set()
        for line in [*old.get("unmatched_lines", []), *new.get("unmatched_lines", [])]:
            key = str(line).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unmatched.append(str(line))

        return {
            "tables": merged_tables,
            "columns": merged_columns,
            "unmatched_lines": unmatched,
        }

    @staticmethod
    def diff_manual_annotations(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, int]:
        old = old or {"tables": {}, "columns": {}, "unmatched_lines": []}
        stats = {"new_tables": 0, "updated_tables": 0, "unchanged_tables": 0, "new_columns": 0, "updated_columns": 0, "unchanged_columns": 0}

        for key, value in (new.get("tables", {}) or {}).items():
            old_value = (old.get("tables", {}) or {}).get(key)
            if old_value is None:
                stats["new_tables"] += 1
            elif ManualAnnotationImporter._same_comment(old_value, value):
                stats["unchanged_tables"] += 1
            else:
                stats["updated_tables"] += 1

        for key, value in (new.get("columns", {}) or {}).items():
            old_value = (old.get("columns", {}) or {}).get(key)
            if old_value is None:
                stats["new_columns"] += 1
            elif ManualAnnotationImporter._same_comment(old_value, value):
                stats["unchanged_columns"] += 1
            else:
                stats["updated_columns"] += 1
        return stats

    @staticmethod
    def _same_comment(left: Any, right: Any) -> bool:
        def extract(v: Any) -> str:
            if isinstance(v, dict):
                v = v.get("comment", "")
            return re.sub(r"\s+", " ", str(v or "").strip().lower())
        return extract(left) == extract(right)
