import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path


def quote_ident(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


def format_column_ref(table: str, col: str) -> str:
    if re.search(r"[^A-Za-z0-9_]", col):
        return f"{table}.`{col}`"
    return f"{table}.{col}"


def add_unique(items: list[str], value: str) -> None:
    value = str(value).strip()
    if value and value not in items:
        items.append(value)


def parse_active_columns(active_nodes: list[str]) -> dict[str, list[str]]:
    table_columns: dict[str, list[str]] = {}

    for node in active_nodes:
        if "." not in node:
            continue

        table, col = node.split(".", 1)
        table = table.strip()
        col = col.strip()

        if not table or not col:
            continue

        if table not in table_columns:
            table_columns[table] = []

        if col not in table_columns[table]:
            table_columns[table].append(col)

    return table_columns


def get_pk_fk_columns(conn: sqlite3.Connection) -> dict[str, set[str]]:
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    excluded: dict[str, set[str]] = {table: set() for table in tables}

    for table in tables:
        cursor.execute(f"PRAGMA table_info({quote_ident(table)})")
        for row in cursor.fetchall():
            col_name = row[1]
            is_pk = row[5] > 0
            if is_pk:
                excluded[table].add(col_name)

    for table in tables:
        cursor.execute(f"PRAGMA foreign_key_list({quote_ident(table)})")
        for fk in cursor.fetchall():
            target_table = fk[2]
            source_col = fk[3]
            target_col = fk[4]

            if source_col:
                excluded[table].add(source_col)

            if target_table in excluded and target_col:
                excluded[target_table].add(target_col)

    return excluded


def fetch_top_distinct_values(
    conn: sqlite3.Connection,
    table: str,
    col: str,
    limit: int,
) -> list[str]:
    cursor = conn.cursor()

    sql = f"""
    SELECT {quote_ident(col)}, COUNT(*) AS cnt
    FROM {quote_ident(table)}
    WHERE {quote_ident(col)} IS NOT NULL
      AND TRIM(CAST({quote_ident(col)} AS TEXT)) != ''
    GROUP BY {quote_ident(col)}
    ORDER BY cnt DESC, CAST({quote_ident(col)} AS TEXT) ASC
    LIMIT ?
    """

    cursor.execute(sql, (limit,))
    return [str(row[0]) for row in cursor.fetchall()]


def fetch_distinct_values_for_matching(
    conn: sqlite3.Connection,
    table: str,
    col: str,
    max_scan: int,
) -> list[str]:
    cursor = conn.cursor()

    sql = f"""
    SELECT {quote_ident(col)}, COUNT(*) AS cnt
    FROM {quote_ident(table)}
    WHERE {quote_ident(col)} IS NOT NULL
      AND TRIM(CAST({quote_ident(col)} AS TEXT)) != ''
    GROUP BY {quote_ident(col)}
    ORDER BY cnt DESC, CAST({quote_ident(col)} AS TEXT) ASC
    LIMIT ?
    """

    cursor.execute(sql, (max_scan,))
    return [str(row[0]) for row in cursor.fetchall()]


def normalize_literal_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_question_literals(question: str, evidence: str) -> list[str]:
    text = normalize_literal_text(f"{question} {evidence}")
    candidates: list[str] = []

               
    for pattern in [
        r'"([^"]{1,120})"',
        r"'([^']{1,120})'",
        r"“([^”]{1,120})”",
    ]:
        for value in re.findall(pattern, text):
            add_unique(candidates, value)

           
    for value in re.findall(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", text):
        add_unique(candidates, value)

    for value in re.findall(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", text):
        add_unique(candidates, value)

                                            
    for value in re.findall(r"\b[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+\b", text):
        add_unique(candidates, value)

                             
    for value in re.findall(r"\b\d+\b", text):
        add_unique(candidates, value)

                                                                
    cap_phrase_pattern = r"\b[A-Z][A-Za-z0-9.&'-]*(?:\s+[A-Z][A-Za-z0-9.&'-]*|\s+\d+){0,5}\b"
    for phrase in re.findall(cap_phrase_pattern, text):
        add_unique(candidates, phrase)

        parts = phrase.split()
        if len(parts) > 2:
            for i in range(len(parts)):
                for j in range(i + 1, min(len(parts), i + 4) + 1):
                    sub_phrase = " ".join(parts[i:j])
                    if len(sub_phrase) >= 2:
                        add_unique(candidates, sub_phrase)

                                                              
    stopwords = {
        "what", "which", "who", "when", "where", "how",
        "is", "are", "was", "were", "be", "been",
        "the", "a", "an", "of", "in", "on", "for", "to", "by",
        "with", "and", "or", "from", "that", "this", "these", "those",
        "list", "show", "give", "find", "please",
        "school", "schools", "student", "students",
        "free", "eligible", "meal", "meals", "enrollment",
        "highest", "lowest", "top", "bottom", "first", "last",
        "rate", "rates", "ratio", "percentage", "percent",
        "number", "count", "average", "avg", "sum",
        "name", "names", "type", "types",
    }

    tokens = re.findall(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)?", text)
    clean_tokens = [t for t in tokens if t.lower() not in stopwords]

    for n in range(1, 5):
        for i in range(0, len(clean_tokens) - n + 1):
            phrase = " ".join(clean_tokens[i:i + n])
            if len(phrase) >= 2:
                add_unique(candidates, phrase)

    return candidates[:120]


def normalize_text(value: str) -> str:
    value = str(value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value))


def is_integer_text(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", str(value or "").strip()))


def normalize_integer_text(value: str) -> str:
    value = str(value or "").strip()
    if is_integer_text(value):
        return value.lstrip("0") or "0"
    return value


def token_overlap_score(a: str, b: str) -> float:
    a_tokens = set(normalize_text(a).split())
    b_tokens = set(normalize_text(b).split())

    if not a_tokens or not b_tokens:
        return 0.0

    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def string_similarity(a: str, b: str) -> float:
    a_raw = str(a or "").strip()
    b_raw = str(b or "").strip()

    if not a_raw or not b_raw:
        return 0.0

                         
    if is_integer_text(a_raw) and is_integer_text(b_raw):
        if normalize_integer_text(a_raw) == normalize_integer_text(b_raw):
            return 1.0

    a_norm = normalize_text(a_raw)
    b_norm = normalize_text(b_raw)

    if not a_norm or not b_norm:
        return 0.0

                     
    if a_norm == b_norm:
        return 1.0

             
    if compact_text(a_raw) == compact_text(b_raw):
        return 0.98

          
    if len(a_norm) >= 3 and a_norm in b_norm:
        return 0.94

    if len(b_norm) >= 3 and b_norm in a_norm:
        return 0.92

    overlap = token_overlap_score(a_norm, b_norm)
    seq_score = SequenceMatcher(None, a_norm, b_norm).ratio()

    return max(overlap, seq_score)


def match_literals_to_db_values(
    literals: list[str],
    db_values: list[str],
    *,
    threshold: float,
    limit: int,
) -> list[str]:
    scored: list[tuple[str, float]] = []

    for value in db_values:
        best_score = 0.0

        for literal in literals:
            score = string_similarity(literal, value)
            if score > best_score:
                best_score = score

        if best_score >= threshold:
            scored.append((value, best_score))

    scored.sort(key=lambda x: (-x[1], len(str(x[0])), str(x[0])))

    result: list[str] = []
    for value, _ in scored:
        add_unique(result, value)
        if len(result) >= limit:
            break

    return result


def format_value_list(values: list[str]) -> str:
    return ", ".join(repr(str(v)) for v in values)


def build_column_value_hints(
    db_path: str | Path,
    active_nodes: list[str],
    *,
    question: str,
    evidence: str,
    value_limit_per_column: int = 5,
    matched_value_limit_per_column: int = 8,
    max_distinct_scan_per_column: int = 5000,
    match_threshold: float = 0.82,
) -> str:
    db_path = Path(db_path)

    conn = sqlite3.connect(db_path)
    try:
        table_columns = parse_active_columns(active_nodes)
        excluded_columns = get_pk_fk_columns(conn)
        literals = extract_question_literals(question, evidence)

        lines: list[str] = []

        for table, columns in table_columns.items():
            table_excluded = excluded_columns.get(table, set())

            for col in columns:
                if col in table_excluded:
                    continue

                frequent_values = fetch_top_distinct_values(
                    conn=conn,
                    table=table,
                    col=col,
                    limit=value_limit_per_column,
                )

                candidate_values = fetch_distinct_values_for_matching(
                    conn=conn,
                    table=table,
                    col=col,
                    max_scan=max_distinct_scan_per_column,
                )

                matched_values = match_literals_to_db_values(
                    literals=literals,
                    db_values=candidate_values,
                    threshold=match_threshold,
                    limit=matched_value_limit_per_column,
                )

                if not frequent_values and not matched_values:
                    continue

                parts: list[str] = []

                if matched_values:
                    parts.append(f"question-matched values: {format_value_list(matched_values)}")

                if frequent_values:
                    parts.append(f"frequent values: {format_value_list(frequent_values)}")

                lines.append(f"- {format_column_ref(table, col)}: " + "; ".join(parts))

        if not lines:
            return "No column value hints."

        return "\n".join(lines)

    finally:
        conn.close()
                                                                               
                                                                             
                                                                               

def _raw_schema_pk_fk_columns(raw_schema: dict) -> dict[str, set[str]]:
    excluded: dict[str, set[str]] = {}
    for table in raw_schema.get("tables", []) or []:
        table_name = str(table.get("name", ""))
        if not table_name:
            continue
        excluded.setdefault(table_name, set())
        for pk in table.get("primary_keys", []) or []:
            excluded[table_name].add(str(pk))
        for fk in table.get("foreign_keys", []) or []:
            if fk.get("from_column"):
                excluded[table_name].add(str(fk.get("from_column")))
            to_table = str(fk.get("to_table") or "")
            if to_table and fk.get("to_column"):
                excluded.setdefault(to_table, set()).add(str(fk.get("to_column")))
    return excluded


def _raw_schema_column_types(raw_schema: dict) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for table in raw_schema.get("tables", []) or []:
        table_name = str(table.get("name", ""))
        if not table_name:
            continue
        result.setdefault(table_name, {})
        for col in table.get("columns", []) or []:
            result[table_name][str(col.get("name", ""))] = str(col.get("type", ""))
    return result


def _is_value_hint_column_type(col_type: str) -> bool:
    text = str(col_type or "").lower()
    if any(x in text for x in ["blob", "binary", "json", "geometry", "point", "polygon", "text[]"]):
        return False
    return True


def _generic_fetch_top_distinct_values(connector, table: str, col: str, limit: int) -> list[str]:
    sql = f"""
    SELECT {quote_ident(col)} AS value, COUNT(*) AS cnt
    FROM {quote_ident(table)}
    WHERE {quote_ident(col)} IS NOT NULL
      AND TRIM(CAST({quote_ident(col)} AS CHAR)) != ''
    GROUP BY {quote_ident(col)}
    ORDER BY cnt DESC, CAST({quote_ident(col)} AS CHAR) ASC
    LIMIT {int(limit)}
    """
    rows = connector.execute_sql(sql, limit=None)
    return [str(row.get("value")) for row in rows if row.get("value") is not None]


def _generic_fetch_distinct_values_for_matching(connector, table: str, col: str, max_scan: int) -> list[str]:
    sql = f"""
    SELECT {quote_ident(col)} AS value, COUNT(*) AS cnt
    FROM {quote_ident(table)}
    WHERE {quote_ident(col)} IS NOT NULL
      AND TRIM(CAST({quote_ident(col)} AS CHAR)) != ''
    GROUP BY {quote_ident(col)}
    ORDER BY cnt DESC, CAST({quote_ident(col)} AS CHAR) ASC
    LIMIT {int(max_scan)}
    """
    rows = connector.execute_sql(sql, limit=None)
    return [str(row.get("value")) for row in rows if row.get("value") is not None]


def build_connector_column_value_hints(
    connector,
    raw_schema: dict,
    active_nodes: list[str],
    *,
    question: str,
    evidence: str,
    value_limit_per_column: int = 5,
    matched_value_limit_per_column: int = 8,
    max_distinct_scan_per_column: int = 5000,
    match_threshold: float = 0.82,
) -> str:
    table_columns = parse_active_columns(active_nodes)
    if not table_columns:
        return "没有可用于列值提示的激活字段。"

    excluded_columns = _raw_schema_pk_fk_columns(raw_schema)
    column_types = _raw_schema_column_types(raw_schema)
    literals = extract_question_literals(question, evidence)
    lines: list[str] = []

    for table, columns in table_columns.items():
        table_excluded = excluded_columns.get(table, set())
        for col in columns:
            if col in table_excluded:
                continue
            if not _is_value_hint_column_type(column_types.get(table, {}).get(col, "")):
                continue

            frequent_values = _generic_fetch_top_distinct_values(
                connector=connector,
                table=table,
                col=col,
                limit=value_limit_per_column,
            )
            candidate_values = _generic_fetch_distinct_values_for_matching(
                connector=connector,
                table=table,
                col=col,
                max_scan=max_distinct_scan_per_column,
            )
            matched_values = match_literals_to_db_values(
                literals=literals,
                db_values=candidate_values,
                threshold=match_threshold,
                limit=matched_value_limit_per_column,
            )

            if not frequent_values and not matched_values:
                continue

            parts: list[str] = []
            if matched_values:
                parts.append(f"question-matched values: {format_value_list(matched_values)}")
            if frequent_values:
                parts.append(f"frequent values: {format_value_list(frequent_values)}")
            lines.append(f"- {format_column_ref(table, col)}: " + "; ".join(parts))

    return "\n".join(lines) if lines else "没有匹配到列值提示。"
