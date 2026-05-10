from __future__ import annotations

import re
from itertools import combinations
from typing import Any

import networkx as nx


class SchemaGraphBuilder:

    def __init__(
        self,
        *,
        enriched_schema: dict[str, Any],
        table_profile: dict[str, Any] | None = None,
        value_overlap_threshold: float = 0.75,
        min_overlap_values: int = 3,
    ) -> None:
        self.enriched_schema = enriched_schema or {}
        self.table_profile = table_profile or {}
        self.value_overlap_threshold = float(value_overlap_threshold)
        self.min_overlap_values = int(min_overlap_values)
        self.graph = nx.Graph()
        self.relationships: list[str] = []
        self.node_metadata: dict[str, dict[str, Any]] = {}

    def build(self) -> nx.Graph:
        self._add_tables_and_columns()
        self._add_foreign_keys()
        self._add_manual_join_rules_from_comments()
        self._add_value_overlap_edges()
        return self.graph

    def _add_tables_and_columns(self) -> None:
        for table in self.enriched_schema.get("tables", []):
            table_name = table.get("name", "")
            if not table_name:
                continue
            table_comment = table.get("final_comment", "") or table.get("db_comment", "") or ""
            self.graph.add_node(table_name, kind="table", table=table_name, comment=table_comment)
            self.node_metadata[table_name] = {
                "kind": "table",
                "table": table_name,
                "comment": table_comment,
                "text": self._normalize_text(" ".join([table_name, table_comment])),
            }

            for col in table.get("columns", []):
                col_name = col.get("name", "")
                if not col_name:
                    continue
                fq = f"{table_name}.{col_name}"
                comment = col.get("final_comment", "") or col.get("db_comment", "") or ""
                profile = col.get("profile", {}) or {}
                sample_values = profile.get("sample_values") or []
                sample_text = " ".join(map(str, sample_values[:8]))
                col_text = " ".join([table_name, col_name, col.get("type", ""), comment, sample_text])
                self.graph.add_node(
                    fq,
                    kind="column",
                    table=table_name,
                    column=col_name,
                    comment=comment,
                    col_type=col.get("type", ""),
                    profile=profile,
                )
                self.node_metadata[fq] = {
                    "kind": "column",
                    "table": table_name,
                    "column": col_name,
                    "comment": comment,
                    "type": col.get("type", ""),
                    "profile": profile,
                    "text": self._normalize_text(col_text),
                }
                self.graph.add_edge(table_name, fq, relation="table_column", weight=0.1)

    def _add_foreign_keys(self) -> None:
        for table in self.enriched_schema.get("tables", []):
            table_name = table.get("name", "")
            for fk in table.get("foreign_keys", []) or []:
                left = f"{fk.get('from_table') or table_name}.{fk.get('from_column')}"
                right = f"{fk.get('to_table')}.{fk.get('to_column')}"
                if left in self.graph and right in self.graph:
                    self.graph.add_edge(left, right, relation="foreign_key", weight=0.2)
                    self.relationships.append(f"{left} = {right}")

    def _add_manual_join_rules_from_comments(self) -> None:
        comments: list[str] = []
        for table in self.enriched_schema.get("tables", []):
            if table.get("final_comment"):
                comments.append(str(table["final_comment"]))
            for col in table.get("columns", []) or []:
                if col.get("final_comment"):
                    comments.append(str(col["final_comment"]))

        all_fq = set(self.node_metadata.keys())
        pattern = re.compile(
            r"(?:CAST\s*\(\s*)?`?([A-Za-z_][\w]*)`?\.(`?[^`\s,=)]+`?|[A-Za-z_][\w\s()\-/]*)\s*(?:AS\s+\w+\s*\))?\s*=\s*"
            r"(?:CAST\s*\(\s*)?`?([A-Za-z_][\w]*)`?\.(`?[^`\s,=)]+`?|[A-Za-z_][\w\s()\-/]*)\s*(?:AS\s+\w+\s*\))?",
            flags=re.IGNORECASE,
        )
        for comment in comments:
            for match in pattern.finditer(comment):
                lt, lc, rt, rc = match.groups()
                left = self._resolve_fq(lt, lc, all_fq)
                right = self._resolve_fq(rt, rc, all_fq)
                if left and right and left != right:
                    self.graph.add_edge(left, right, relation="manual_join_rule", weight=0.15)
                    relation_text = match.group(0).strip()
                    if relation_text not in self.relationships:
                        self.relationships.append(relation_text)

    def _add_value_overlap_edges(self) -> None:
        column_nodes = [node for node, meta in self.node_metadata.items() if meta.get("kind") == "column"]
        samples: dict[str, set[str]] = {}
        for node in column_nodes:
            profile = self.node_metadata[node].get("profile") or {}
            vals = profile.get("sample_values") or []
            normalized = {self._normalize_value(v) for v in vals if self._normalize_value(v)}
            if len(normalized) >= self.min_overlap_values:
                samples[node] = normalized

        for left, right in combinations(sorted(samples), 2):
            if self.node_metadata[left].get("table") == self.node_metadata[right].get("table"):
                continue
            inter = samples[left] & samples[right]
            if len(inter) < self.min_overlap_values:
                continue
            union = samples[left] | samples[right]
            score = len(inter) / len(union) if union else 0.0
            if score >= self.value_overlap_threshold:
                self.graph.add_edge(left, right, relation="value_overlap", weight=0.6, score=round(score, 4))
                self.relationships.append(f"{left} ~= {right} (sample value overlap {score:.3f})")

    def _resolve_fq(self, table: str, column: str, all_fq: set[str]) -> str | None:
        table_clean = table.strip("` ")
        col_clean = column.strip("` ").strip()
        exact = f"{table_clean}.{col_clean}"
        if exact in all_fq:
            return exact
        target = self._normalize_identifier(exact)
        for fq in all_fq:
            if self._normalize_identifier(fq) == target:
                return fq
        return None

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).lower())

    @staticmethod
    def _normalize_value(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9_]+", " ", str(value).lower())
