import os
import re
import sqlite3
from itertools import combinations
from typing import Dict, List

import networkx as nx
import numpy as np
import pandas as pd

from config import VALUE_OVERLAP_CONFIG
from core.value_overlap import MinHashSignature, is_valid_overlap_candidate_column


class TopologyGraphBuilder:
    def __init__(self, db_path: str, schema_text: str) -> None:
        self.db_path = db_path
        self.schema_text = schema_text
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.G = nx.Graph()
        self.col_comments = self._extract_all_comments()
        self.virtual_edges: list[tuple[str, str]] = []

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            print(f"🔌 已关闭数据库连接: {self.db_path}")

    def _extract_all_comments(self) -> Dict[str, str]:
        comments: Dict[str, str] = {}
        table_blocks = re.split(r"CREATE TABLE", self.schema_text, flags=re.IGNORECASE)

        for block in table_blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue

            t_match = re.search(r"(\w+)", lines[0])
            if not t_match:
                continue
            table_name = t_match.group(1)

            for line in lines[1:]:
                c_match = re.search(
                    r"^\s*[`\"'\[]?([^`\"'\]\s,]+(?:\s+[^`\"'\],]+)*?)[`\"'\]]?\s+.*?COMMENT\s+['\"](.*?)['\"]",
                    line,
                    re.IGNORECASE,
                )
                if c_match:
                    col_name, comment = c_match.groups()
                    col_name = col_name.strip().strip("`\"'[]")
                    comments[f"{table_name}.{col_name}"] = comment

        return comments

    def _get_tables(self) -> List[str]:
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [row[0] for row in self.cursor.fetchall()]

    def build_structure(self) -> None:
        print(f"\n🏗️ 正在构建[{os.path.basename(self.db_path)}]图拓扑...")
        tables = self._get_tables()

        for table in tables:
            self.G.add_node(table, type="table", label=table, heat=0)
            self.cursor.execute(f"PRAGMA table_info(`{table}`)")
            for col in self.cursor.fetchall():
                col_name = col[1]
                node_id = f"{table}.{col_name}"
                is_pk = col[5] > 0

                self.G.add_node(
                    node_id,
                    type="column",
                    label=col_name,
                    comment=self.col_comments.get(node_id),
                    is_pk=is_pk,
                    heat=0,
                )
                self.G.add_edge(table, node_id, weight=0.1, relation="schema_binding")

        for table in tables:
            self.cursor.execute(f"PRAGMA foreign_key_list(`{table}`)")
            for fk in self.cursor.fetchall():
                target_table = fk[2]
                source_col = fk[3]
                target_col = fk[4]
                u = f"{table}.{source_col}"
                v = f"{target_table}.{target_col}"
                if self.G.has_node(u) and self.G.has_node(v):
                    self.G.add_edge(u, v, weight=1.0, relation="physical_fk")

        self.build_virtual_edges()

    def build_virtual_edges(self) -> None:
        print(f"🔍 正在检测[{os.path.basename(self.db_path)}]虚拟关联边（值域重叠）...")
        tables = self._get_tables()
        table_dfs: dict[str, pd.DataFrame] = {}

        for table in tables:
            table_dfs[table] = pd.read_sql_query(f"SELECT * FROM `{table}`", self.conn)

        existing_links = set()
        for table in tables:
            self.cursor.execute(f"PRAGMA foreign_key_list(`{table}`)")
            for fk in self.cursor.fetchall():
                pair_1 = (table, fk[3], fk[2], fk[4])
                pair_2 = (fk[2], fk[4], table, fk[3])
                existing_links.add(pair_1)
                existing_links.add(pair_2)

        hasher = MinHashSignature(
            num_perm=VALUE_OVERLAP_CONFIG["MINHASH_PERM"],
            seed=VALUE_OVERLAP_CONFIG["SEED"],
        )
        column_signatures: dict[tuple[str, str], np.ndarray] = {}

        for table in tables:
            df = table_dfs[table]
            for col in df.columns:
                series = df[col]
                distinct_cnt = series.nunique()
                if is_valid_overlap_candidate_column(series, distinct_cnt):
                    sig = hasher.generate_signature(series)
                    column_signatures[(table, col)] = sig

        valid_cols = list(column_signatures.keys())
        for (t_a, c_a), (t_b, c_b) in combinations(valid_cols, 2):
            if t_a == t_b:
                continue
            if (t_a, c_a, t_b, c_b) in existing_links:
                continue

            sig_a = column_signatures[(t_a, c_a)]
            sig_b = column_signatures[(t_b, c_b)]
            jaccard = MinHashSignature.compute_jaccard(sig_a, sig_b)

            if jaccard > VALUE_OVERLAP_CONFIG["JACCARD_THRESHOLD"]:
                node_a = f"{t_a}.{c_a}"
                node_b = f"{t_b}.{c_b}"
                if self.G.has_node(node_a) and self.G.has_node(node_b):
                    self.G.add_edge(
                        node_a,
                        node_b,
                        weight=np.inf,
                        relation="virtual_value_overlap",
                        jaccard=jaccard,
                    )
                    self.virtual_edges.append((node_a, node_b))
                    print(f"  🔗 虚拟边: {node_a} <==> {node_b} (Jaccard: {jaccard:.4f})")

        print(f"✅ [{os.path.basename(self.db_path)}]虚拟关联边检测完成，共发现 {len(self.virtual_edges)} 条虚拟边")
