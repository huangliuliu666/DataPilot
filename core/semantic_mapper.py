import re
from typing import TYPE_CHECKING

import networkx as nx
import numpy as np
import requests

from config import Config

if TYPE_CHECKING:
    from core.topology import TopologyGraphBuilder


class SemanticHeatMapper:
    def __init__(self, builder: "TopologyGraphBuilder") -> None:
        self.builder = builder
        self.cursor = builder.cursor
        self.G = builder.G
        self.ollama_url = Config.OLLAMA_URL
        self.model_name = Config.OLLAMA_MODEL
        self.relationship: list[str] = []
        self._embedding_cache: dict[str, np.ndarray] = {}

    def _reset_relationship(self) -> None:
        self.relationship = []

    def _get_embedding(self, text: str) -> np.ndarray:
        cleaned_text = str(text or "").strip()
        if not cleaned_text:
            raise ValueError("Embedding text 不能为空")

        max_chars = Config.OLLAMA_EMBEDDING_MAX_CHARS
        if max_chars > 0:
            cleaned_text = cleaned_text[:max_chars]

        if cleaned_text in self._embedding_cache:
            return self._embedding_cache[cleaned_text]

        payload = {"model": self.model_name, "prompt": cleaned_text}
        try:
            resp = requests.post(self.ollama_url, json=payload, timeout=Config.OLLAMA_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Ollama embedding 调用失败：url={self.ollama_url}, "
                f"model={self.model_name}, timeout={Config.OLLAMA_TIMEOUT}s, "
                f"text_preview={cleaned_text[:80]!r}"
            ) from exc

        if "embedding" not in data:
            raise RuntimeError(f"Ollama embedding response missing 'embedding': {data}")

        embedding = np.array(data["embedding"])
        self._embedding_cache[cleaned_text] = embedding
        return embedding

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        n1 = np.linalg.norm(vec1)
        n2 = np.linalg.norm(vec2)
        if n1 == 0 or n2 == 0:
            return 0.0
        return np.dot(vec1, vec2) / (n1 * n2)

    def _check_db_value_detail(self, table: str, col: str, value: str, exact: bool = False):
        try:
            if exact:
                query = f"SELECT `{col}` FROM `{table}` WHERE UPPER(`{col}`) = UPPER(?) LIMIT 1"
                params = (value,)
            else:
                query = f"SELECT `{col}` FROM `{table}` WHERE UPPER(`{col}`) LIKE UPPER(?) LIMIT 1"
                params = (f"%{value}%",)
            self.cursor.execute(query, params)
            res = self.cursor.fetchone()
            return res[0] if res else None
        except Exception:
            return None

    def _global_value_diffusion(self, value: str, source_node_id: str, is_exact_trigger: bool = True) -> None:
        if str(value).isdigit():
            return

        _, source_col = source_node_id.split(".")
        all_tables = self.builder._get_tables()
        candidates = []

        for table in all_tables:
            self.cursor.execute(f"PRAGMA table_info(`{table}`)")
            cols = [c[1] for c in self.cursor.fetchall()]

            for col in cols:
                target_node_id = f"{table}.{col}"
                if target_node_id == source_node_id:
                    continue

                real_val = self._check_db_value_detail(table, col, value, exact=is_exact_trigger)
                if real_val:
                    src_comment = self.G.nodes[source_node_id].get("comment")
                    tar_comment = self.G.nodes[target_node_id].get("comment")
                    score = self._cosine_similarity(
                        self._get_embedding(src_comment if src_comment else source_col),
                        self._get_embedding(tar_comment if tar_comment else col),
                    )
                    candidates.append({"node": target_node_id, "score": score})

        candidates.sort(key=lambda x: x["score"], reverse=True)
        threshold = 0.75 if is_exact_trigger else 0.6

        for item in candidates[:2]:
            if item["score"] > threshold:
                self.G.nodes[item["node"]]["heat"] = 1
                self.G.nodes[item["node"].split(".")[0]]["heat"] = 1

    def _trace_value_in_full_db(self, value: str, target_col_hint: str) -> list[str]:
        if str(value).isdigit():
            return []

        words = [w for w in re.split(r"\s+|-|_", value) if len(w) > 2]
        if not words:
            words = [value]

        all_tables = self.builder._get_tables()
        found_candidates = []

        for table in all_tables:
            self.cursor.execute(f"PRAGMA table_info(`{table}`)")
            cols = [c[1] for c in self.cursor.fetchall()]

            for col in cols:
                for word in words:
                    real_val = self._check_db_value_detail(table, col, word, exact=False)
                    if real_val:
                        node_id = f"{table}.{col}"
                        base_score = self._cosine_similarity(
                            self._get_embedding(target_col_hint),
                            self._get_embedding(col),
                        )
                        bonus = 0.5 if str(real_val).upper() == str(value).upper() else 0.1
                        final_score = base_score + bonus
                        found_candidates.append(
                            {
                                "node": node_id,
                                "score": final_score,
                                "real_val": real_val,
                            }
                        )
                        break

        found_candidates.sort(key=lambda x: x["score"], reverse=True)
        results: list[str] = []

        for item in found_candidates[:3]:
            if item["score"] > 0.5:
                self.relationship.append(f"{item['node']} = {item['real_val']}")
                results.append(item["node"])

        return results

    @staticmethod
    def _extract_involved_tables(text: str) -> list[str]:
        tables_found: list[str] = []
        for match in re.findall(r"Involved table names:\s*(.*)", text, re.IGNORECASE):
            parts = [t.strip().strip("`").strip() for t in match.split(",") if t.strip()]
            tables_found.extend(parts)
        return tables_found

    @staticmethod
    def _extract_involved_columns(text: str) -> list[str]:
        cols_found: list[str] = []
        for match in re.findall(r"Involved column names:\s*(.*)", text, re.IGNORECASE):
            parts = [c.strip().strip("`").strip() for c in match.split(",") if c.strip()]
            cols_found.extend(parts)
        return cols_found

    def process_supplementary_info(self, supp_text: str) -> None:
        tables_found = self._extract_involved_tables(supp_text)
        cols_found = self._extract_involved_columns(supp_text)

        for t_name in tables_found:
            t_node = next(
                (n for n in self.G.nodes if n.lower() == t_name.lower() and self.G.nodes[n]["type"] == "table"),
                None,
            )
            if t_node and self.G.nodes[t_node]["heat"] == 0:
                self.G.nodes[t_node]["heat"] = 1

        for col_item in cols_found:
            col_item = col_item.replace("`", "").strip()
            if "." in col_item:
                target_table, target_col = col_item.split(".", 1)
                node_id = f"{target_table}.{target_col}"
                real_node = next((n for n in self.G.nodes if n.lower() == node_id.lower()), None)
                if real_node and self.G.nodes[real_node]["heat"] == 0:
                    self.G.nodes[real_node]["heat"] = 1
                    self.G.nodes[real_node.split(".")[0]]["heat"] = 1

    def process_and_map(self, llm_text: str) -> None:
        nx.set_node_attributes(self.G, 0, "heat")
        self._reset_relationship()

        t_match = re.search(r"Involved table names:\s*(.*)", llm_text, re.IGNORECASE)
        tables_raw = [t.strip().strip("`").strip() for t in t_match.group(1).split(",")] if t_match else []

        c_match = re.search(r"Involved column names:\s*(.*)", llm_text, re.IGNORECASE)
        columns_raw = [c.strip().strip("`").strip() for c in c_match.group(1).split(",")] if c_match else []

        active_table_nodes = []
        for t_name in tables_raw:
            t_node = next(
                (n for n in self.G.nodes if n.lower() == t_name.lower() and self.G.nodes[n]["type"] == "table"),
                None,
            )
            if t_node:
                self.G.nodes[t_node]["heat"] = 1
                active_table_nodes.append(t_node)

        for col_item in columns_raw:
            col_item = col_item.replace("`", "").strip()
            if "." in col_item:
                target_table, target_col = col_item.split(".", 1)
                node_id = f"{target_table}.{target_col}"
                if self.G.has_node(node_id):
                    self.G.nodes[node_id]["heat"] = 1
                    self.G.nodes[target_table]["heat"] = 1
            else:
                for node_name, node_data in self.G.nodes(data=True):
                    if node_data.get("type") == "column" and node_data["label"].lower() == col_item.lower():
                        if node_name.split(".")[0] in active_table_nodes:
                            self.G.nodes[node_name]["heat"] = 1

        rel_pattern = r"([a-zA-Z0-9_\(\)\-\s/&%]+)\.([a-zA-Z0-9_\(\)\-\s/&%]+)\s*=\s*([^,\n\r]+)"
        if "Equivalence relations:" in llm_text:
            part = llm_text.split("Equivalence relations:")[1].strip()
            for seg in re.split(r"[,\n]", part):
                rm = re.search(rel_pattern, seg.strip().replace("`", ""))
                if not rm:
                    continue

                tbl = rm.group(1).strip()
                col = rm.group(2).strip()
                val = rm.group(3).strip()
                val_clean = str(val).strip("'").strip('"').strip()
                node_id = f"{tbl}.{col}"

                if "." in val_clean and any(t.lower() == val_clean.split(".")[0].lower() for t in tables_raw):
                    if self.G.has_node(node_id):
                        self.G.nodes[node_id]["heat"] = 1
                    rtbl_raw, rcol_raw = val_clean.split(".")[-2:]
                    r_node_id = f"{rtbl_raw}.{rcol_raw}"
                    for n in self.G.nodes:
                        if n.lower() == r_node_id.lower():
                            self.G.nodes[n]["heat"] = 1
                    continue

                real_val_exact = self._check_db_value_detail(tbl, col, val_clean, exact=True)
                if real_val_exact is not None and str(real_val_exact).upper() == val_clean.upper():
                    self.relationship.append(f"{node_id} = {val_clean}")
                    self.G.nodes[node_id]["heat"] = 1
                    self._global_value_diffusion(val_clean, node_id)
                else:
                    corrected = self._trace_value_in_full_db(val_clean, col)
                    for cn in corrected:
                        self.G.nodes[cn]["heat"] = 1
                        self.G.nodes[cn.split(".")[0]]["heat"] = 1

    def activate_virtual_related_nodes(self) -> None:
        active_nodes = [n for n, d in self.G.nodes(data=True) if d.get("heat") == 1]

        for node in active_nodes:
            for neighbor in self.G.neighbors(node):
                edge_data = self.G.get_edge_data(node, neighbor)
                if edge_data and edge_data.get("relation") == "virtual_value_overlap":
                    if self.G.nodes[neighbor]["heat"] == 0:
                        self.G.nodes[neighbor]["heat"] = 1
                        if "." in neighbor:
                            table_node = neighbor.split(".")[0]
                            if self.G.nodes[table_node]["heat"] == 0:
                                self.G.nodes[table_node]["heat"] = 1

    def execute_steiner_search(self) -> list[str]:
        terminal_nodes = [
            n
            for n, d in self.G.nodes(data=True)
            if d.get("heat") == 1 and d.get("type") in ["table", "column"]
        ]

        terminal_nodes = sorted(list(set([n for n in terminal_nodes if self.G.has_node(n)])))

        if len(terminal_nodes) >= 2:
            try:
                metric_closure_graph = nx.Graph()
                paths_cache = {}

                for i in range(len(terminal_nodes)):
                    for j in range(i + 1, len(terminal_nodes)):
                        u = terminal_nodes[i]
                        v = terminal_nodes[j]
                        try:
                            dist = nx.shortest_path_length(self.G, source=u, target=v, weight="weight")
                            path = nx.shortest_path(self.G, source=u, target=v, weight="weight")
                            metric_closure_graph.add_edge(u, v, weight=dist)
                            paths_cache[tuple(sorted((u, v)))] = path
                        except nx.NetworkXNoPath:
                            pass

                if metric_closure_graph.number_of_edges() > 0:
                    mst_edges = nx.minimum_spanning_edges(metric_closure_graph, weight="weight", data=False)

                    for u, v in mst_edges:
                        key = tuple(sorted((u, v)))
                        if key in paths_cache:
                            path = paths_cache[key]
                            for node in path:
                                self.G.nodes[node]["heat"] = 1

            except Exception as e:
                raise RuntimeError(f"Steiner search failed: {e}") from e

        for table_node in [n for n, d in self.G.nodes(data=True) if d.get("heat") == 1 and d.get("type") == "table"]:
            for neighbor in self.G.neighbors(table_node):
                if self.G.nodes[neighbor].get("is_pk"):
                    self.G.nodes[neighbor]["heat"] = 1

        final_nodes = sorted([n for n, d in self.G.nodes(data=True) if d.get("heat") == 1])
        return final_nodes