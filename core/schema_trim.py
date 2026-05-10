import re


def parse_activated_nodes(activated_nodes: list[str]) -> dict[str, list[str]]:

    table_columns: dict[str, list[str]] = {}
    activated_tables = set()

    for node in activated_nodes:
        if "." in node:
            table_name, col_name = node.split(".", 1)
            table_name = table_name.strip()
            col_name = col_name.strip()
            activated_tables.add(table_name)
            if table_name not in table_columns:
                table_columns[table_name] = []
            if col_name not in table_columns[table_name]:
                table_columns[table_name].append(col_name)
        else:
            table_name = node.strip()
            activated_tables.add(table_name)
            if table_name not in table_columns:
                table_columns[table_name] = []

    for table_name in activated_tables:
        if table_name not in table_columns:
            table_columns[table_name] = []

    return table_columns


def extract_table_block(schema_text: str, table_name: str) -> dict | None:

    pattern = re.compile(
        rf"CREATE\s+TABLE\s+[`\"'\[]?{re.escape(table_name)}[`\"'\]]?\s*\(",
        re.IGNORECASE,
    )
    match = pattern.search(schema_text)
    if not match:
        return None

    start_idx = match.end() - 1
    paren_level = 0
    in_single_quote = False
    in_double_quote = False
    end_idx = -1

    for i in range(start_idx, len(schema_text)):
        char = schema_text[i]

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if not in_single_quote and not in_double_quote:
            if char == "(":
                paren_level += 1
            elif char == ")":
                paren_level -= 1
                if paren_level == 0:
                    end_idx = i
                    break

    if end_idx == -1:
        return None

    content = schema_text[start_idx + 1 : end_idx].strip()

    semicolon_idx = schema_text.find(";", end_idx)
    if semicolon_idx != -1:
        trailing_part = schema_text[end_idx + 1 : semicolon_idx].strip()
    else:
        trailing_part = schema_text[end_idx + 1 :].split("\n")[0].strip()

    return {
        "table_name": table_name,
        "content": content,
        "table_comment": trailing_part,
    }


def parse_table_definition(table_info: dict) -> dict:

    table_name = table_info["table_name"]
    content = table_info["content"]

    parts = []
    current_part = ""
    paren_level = 0
    in_string_single = False
    in_string_double = False

    for char in content:
        if char == "'" and not in_string_double:
            in_string_single = not in_string_single
        elif char == '"' and not in_string_single:
            in_string_double = not in_string_double
        elif char == "(" and not in_string_single and not in_string_double:
            paren_level += 1
        elif char == ")" and not in_string_single and not in_string_double:
            paren_level -= 1
        elif char == "," and paren_level == 0 and not in_string_single and not in_string_double:
            parts.append(current_part.strip())
            current_part = ""
            continue

        current_part += char

    if current_part.strip():
        parts.append(current_part.strip())

    refined_parts = []
    for part in parts:
        sub_parts = re.split(
            r"\r?\n(?=\s*(?:PRIMARY|FOREIGN)\s+KEY\s*\()",
            part,
            flags=re.IGNORECASE,
        )
        for sub_part in sub_parts:
            if sub_part.strip():
                refined_parts.append(sub_part.strip())

    columns = []
    primary_keys = []
    foreign_keys = []

    for part in refined_parts:
        part_upper = part.upper()
        if part_upper.startswith("PRIMARY KEY") or (
            part_upper.startswith("CONSTRAINT") and "PRIMARY KEY" in part_upper
        ):
            primary_keys.append(part)
        elif part_upper.startswith("FOREIGN KEY") or (
            part_upper.startswith("CONSTRAINT") and "FOREIGN KEY" in part_upper
        ):
            foreign_keys.append(part)
        else:
            if "COMMENT" in part_upper:
                single_quotes = part.count("'")
                double_quotes = part.count('"')
                if single_quotes % 2 != 0:
                    part += "'"
                elif double_quotes % 2 != 0:
                    part += '"'
            columns.append(part)

    return {
        "table_name": table_name,
        "columns": columns,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
        "table_comment": table_info["table_comment"],
    }


def generate_trimmed_schema(original_schema: str, activated_nodes: list[str]) -> str:

    table_columns = parse_activated_nodes(activated_nodes)
    trimmed_tables = []

    for table_name, required_cols in table_columns.items():
        table_info = extract_table_block(original_schema, table_name)
        if not table_info:
            continue

        table_def = parse_table_definition(table_info)
        kept_columns = []

        for col_name in required_cols:
            pattern = re.compile(
                r"^[`\"'\[]?\s*" + re.escape(col_name) + r"\s*[`\"'\]]?(?:\s+|$)",
                re.IGNORECASE,
            )

            matched_def = None
            for col_def in table_def["columns"]:
                if pattern.search(col_def):
                    matched_def = col_def
                    break

            if not matched_def:
                for col_def in table_def["columns"]:
                    if col_name.lower() in col_def.lower():
                        matched_def = col_def
                        break

            if matched_def:
                if matched_def not in kept_columns:
                    kept_columns.append(matched_def)

        if not table_def["primary_keys"]:
            for col_def in table_def["columns"]:
                if "PRIMARY KEY" in col_def.upper() and col_def not in kept_columns:
                    kept_columns.append(col_def)

        all_lines = kept_columns.copy()

        for pk in table_def["primary_keys"]:
            if pk not in all_lines:
                all_lines.append(pk)

        for fk in table_def["foreign_keys"]:
            if fk not in all_lines:
                all_lines.append(fk)

        final_lines = []
        for line in all_lines:
            clean_line = line.rstrip(",").strip()
            if clean_line:
                final_lines.append(clean_line)

        if final_lines:
            trimmed_table = f"CREATE TABLE {table_name} (\n    " + ",\n    ".join(final_lines) + "\n)"
            if table_def["table_comment"]:
                trimmed_table += f" {table_def['table_comment']};"
            else:
                trimmed_table += ";"
            trimmed_tables.append(trimmed_table)

    final_schema = "\n\n".join(trimmed_tables)
    return final_schema