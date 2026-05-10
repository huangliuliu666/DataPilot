from __future__ import annotations

import re
from typing import Any

import networkx as nx


class TopologyTrimmer:

    def __init__(self, *, graph: nx.Graph, node_metadata: dict[str, dict[str, Any]]) -> None:
        self.graph = graph
        self.node_metadata = node_metadata

    def activate_nodes(self, *, question: str, evidence: str = "", top_k: int = 16) -> list[str]:
        query = self._normalize_text(" ".join([question, evidence]))
        query_tokens = set(query.split())
        scored: list[tuple[float, str]] = []

        for node, meta in self.node_metadata.items():
            text = meta.get("text", "")
            tokens = set(str(text).split())
            score = 0.0
            if node.lower() in f" {query} ":
                score += 4.0
            if meta.get("kind") == "column":
                col = str(meta.get("column", ""))
                table = str(meta.get("table", ""))
                if self._normalize_identifier(col) in self._normalize_identifier(question):
                    score += 3.0
                if self._normalize_identifier(table) in self._normalize_identifier(question):
                    score += 1.5
            else:
                table = str(meta.get("table", ""))
                if self._normalize_identifier(table) in self._normalize_identifier(question):
                    score += 3.0
            overlap = query_tokens & tokens
            score += min(len(overlap), 8) * 0.35
                                                              
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda x: (-x[0], x[1]))
        activated = [node for _, node in scored[:top_k]]

                                                      
        expanded = set(activated)
        for node in list(expanded):
            meta = self.node_metadata.get(node, {})
            if meta.get("kind") == "column" and meta.get("table"):
                expanded.add(meta["table"])
        return sorted(expanded)

    def trim(self, *, activated_nodes: list[str], max_nodes: int = 80) -> list[str]:
        valid = [node for node in activated_nodes if node in self.graph]
        if not valid:
                                                                                                 
            return [node for node, meta in self.node_metadata.items() if meta.get("kind") == "table"][: min(max_nodes, 10)]

        sub_nodes = set(valid)
                                                                                                    
        for i, left in enumerate(valid):
            for right in valid[i + 1 :]:
                if left == right:
                    continue
                try:
                    path = nx.shortest_path(self.graph, left, right, weight="weight")
                    sub_nodes.update(path)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
                if len(sub_nodes) >= max_nodes:
                    break
            if len(sub_nodes) >= max_nodes:
                break

                                                            
        for node in list(sub_nodes):
            if len(sub_nodes) >= max_nodes:
                break
            meta = self.node_metadata.get(node, {})
            if meta.get("kind") == "table":
                for nbr in self.graph.neighbors(node):
                    if len(sub_nodes) >= max_nodes:
                        break
                    edge = self.graph.get_edge_data(node, nbr, {})
                    if edge.get("relation") in {"foreign_key", "manual_join_rule"}:
                        sub_nodes.add(nbr)

        return sorted(sub_nodes)[:max_nodes]

    def format_schema(self, *, selected_nodes: list[str], enriched_schema: dict[str, Any], relationships: list[str] | None = None) -> str:
        selected = set(selected_nodes)
        lines: list[str] = []
        selected_tables = {node for node in selected if self.node_metadata.get(node, {}).get("kind") == "table"}
        for node in selected:
            meta = self.node_metadata.get(node, {})
            if meta.get("kind") == "column":
                selected_tables.add(meta.get("table", ""))

        for table in enriched_schema.get("tables", []):
            table_name = table.get("name", "")
            table_columns = []
            for col in table.get("columns", []) or []:
                fq = f"{table_name}.{col.get('name')}"
                if fq in selected:
                    table_columns.append(col)
            if table_name not in selected_tables and not table_columns:
                continue
            if not table_columns:
                                                                               
                pk_set = set(table.get("primary_keys", []) or [])
                table_columns = [col for col in table.get("columns", []) if col.get("name") in pk_set][:3]
            lines.append(f"CREATE TABLE `{table_name}` (")
            col_lines = []
            for col in table_columns:
                comment = str(col.get("final_comment", "") or "").replace("'", "''")
                line = f"    `{col.get('name')}` {col.get('type') or 'TEXT'}"
                if comment:
                    line += f" COMMENT '{comment}'"
                col_lines.append(line)
            for fk in table.get("foreign_keys", []) or []:
                from_fq = f"{table_name}.{fk.get('from_column')}"
                to_fq = f"{fk.get('to_table')}.{fk.get('to_column')}"
                if from_fq in selected or to_fq in selected:
                    col_lines.append(
                        f"    FOREIGN KEY (`{fk.get('from_column')}`) REFERENCES `{fk.get('to_table')}`(`{fk.get('to_column')}`)"
                    )
            lines.append(",\n".join(col_lines))
            suffix = ""
            if table.get("final_comment"):
                suffix = " COMMENT='" + str(table.get("final_comment", "")).replace("'", "''") + "'"
            lines.append(f"){suffix};\n")

        if relationships:
            relevant_rels = []
            for rel in relationships:
                rel_norm = self._normalize_identifier(rel)
                if any(self._normalize_identifier(node) in rel_norm for node in selected):
                    relevant_rels.append(rel)
            if relevant_rels:
                lines.append("-- Known join/value relationships:")
                for rel in relevant_rels[:20]:
                    lines.append(f"-- {rel}")
        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).lower())

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9_]+", " ", str(value).lower())
