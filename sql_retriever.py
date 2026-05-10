import os
from typing import Dict

import networkx as nx
import sqlglot
import torch
import torch.nn as nn
import torch.nn.functional as F
from sqlglot import exp
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv, global_max_pool, global_mean_pool


class SQLTopologyEncoder(nn.Module):

    def __init__(self, vocab_size, hidden_dim=768):
        super(SQLTopologyEncoder, self).__init__()
        embed_dim = 128

        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.conv1 = GCNConv(embed_dim, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, hidden_dim)
        self.conv3 = GCNConv(hidden_dim, hidden_dim)
        self.fc = nn.Linear(hidden_dim * 2, hidden_dim)

    def forward(self, x, edge_index, batch=None):
        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        x = self.embedding(x.squeeze(-1))
        x = F.relu(self.conv1(x, edge_index))
        x = F.relu(self.conv2(x, edge_index))
        x = F.relu(self.conv3(x, edge_index))

        mean_pool = global_mean_pool(x, batch)
        max_pool = global_max_pool(x, batch)
        x = torch.cat([mean_pool, max_pool], dim=1)
        x = self.fc(x)
        return F.normalize(x, p=2, dim=1)


def text_to_pyg_data(sql: str, vocab: Dict[str, int]):
    try:
        ast = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None

    graph = nx.DiGraph()

    def traverse(node, parent_id=None):
        if not isinstance(node, exp.Expression):
            return

        node_id = id(node)
        node_type = node.__class__.__name__

        if node_type in ["Identifier", "Var"]:
            label = "Identifier\n(_)"
        elif node_type == "Literal":
            label = "Literal\n([VAL])"
        elif node_type == "Ordered":
            is_desc = node.args.get("desc")
            label = f"Ordered\n({'DESC' if is_desc else 'ASC'})"
        else:
            label = node_type

        graph.add_node(node_id, label=label)
        if parent_id is not None:
            graph.add_edge(parent_id, node_id)

        for value in node.args.values():
            if isinstance(value, list):
                for item in value:
                    traverse(item, node_id)
            elif isinstance(value, exp.Expression):
                traverse(value, node_id)

    traverse(ast)

    if len(graph.nodes()) == 0:
        return None

    node_mapping = {old: i for i, old in enumerate(graph.nodes())}
    x_list = [[vocab.get(graph.nodes[n]["label"], 0)] for n in graph.nodes()]
    x_tensor = torch.tensor(x_list, dtype=torch.long)

    src = []
    dst = []
    for u, v in graph.edges():
        src.append(node_mapping[u])
        dst.append(node_mapping[v])

    if len(src) == 0:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
    else:
        edge_index = torch.tensor([src, dst], dtype=torch.long)

    return Data(x=x_tensor, edge_index=edge_index)


def safe_torch_load(path: str, map_location):
    try:
        return torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        return torch.load(path, map_location=map_location)


def remove_module_prefix(state_dict: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    new_state = {}
    for key, value in state_dict.items():
        if key.startswith("module."):
            new_state[key[len("module.") :]] = value
        else:
            new_state[key] = value
    return new_state


def extract_state_dict(checkpoint) -> Dict[str, torch.Tensor]:
    if isinstance(checkpoint, dict):
        if "model_state_dict" in checkpoint:
            return checkpoint["model_state_dict"]
        if "state_dict" in checkpoint:
            return checkpoint["state_dict"]
        if all(isinstance(v, torch.Tensor) for v in checkpoint.values()):
            return checkpoint
        raise KeyError(
            "无法在 checkpoint 中找到 model_state_dict/state_dict。"
            f"checkpoint keys: {list(checkpoint.keys())}"
        )
    raise KeyError("checkpoint 不是 dict；无法提取 state_dict")


def load_state_dict_flexibly(model: nn.Module, state_dict: Dict[str, torch.Tensor], device):
    try:
        model.load_state_dict(state_dict)
        return
    except Exception as first_error:
        state2 = remove_module_prefix(state_dict)
        try:
            model.load_state_dict(state2)
            return
        except Exception as second_error:
            raise RuntimeError(
                "无法严格加载 GNN checkpoint。请检查 best_gnn_encoder.pth 与 SQLTopologyEncoder 结构是否匹配。\n"
                f"首次异常: {first_error}\n"
                f"移除 module. 前缀后异常: {second_error}"
            ) from second_error



class GraphRetriever:
    def __init__(self, model_weights, vocab_path, dataset_path, device="cuda"):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")

        self.vocab = torch.load(vocab_path, weights_only=False) if os.path.exists(vocab_path) else {}
        self.dataset = torch.load(dataset_path, weights_only=False) if os.path.exists(dataset_path) else []

        self.model = SQLTopologyEncoder(vocab_size=len(self.vocab), hidden_dim=768).to(self.device)

        if not os.path.exists(model_weights):
            raise FileNotFoundError(f"模型文件未找到: {model_weights}")

        checkpoint = safe_torch_load(model_weights, map_location=self.device)

        try:
            state_dict = extract_state_dict(checkpoint)
        except KeyError:
            print("无法从 checkpoint 提取 state_dict。请检查此 checkpoint 的内容或传入正确的文件。")
            if isinstance(checkpoint, dict):
                print(f"checkpoint keys: {list(checkpoint.keys())}")
            raise

        load_state_dict_flexibly(self.model, state_dict, self.device)
        self.model.eval()

        print(f"正在初始化特征库，编码 {len(self.dataset)} 条候选 SQL...")
        self.database_vectors = []
        with torch.no_grad():
            for data in self.dataset:
                data = data.to(self.device)
                vec = self.model(data.x, data.edge_index)
                self.database_vectors.append(vec)

        if len(self.database_vectors) == 0:
            self.database_matrix = torch.empty((0, self.model.fc.out_features), device=self.device)
        else:
            self.database_matrix = torch.cat(self.database_vectors, dim=0)

        print("✅ 向量特征库构建完毕！")

    def search_similar_sql(self, pre_sql, top_k=3):
        query_data = text_to_pyg_data(pre_sql, self.vocab)
        if query_data is None:
            return "输入的 P-SQL 无法解析为 AST（可能语法错误）"

        query_data = query_data.to(self.device)
        with torch.no_grad():
            query_vec = self.model(query_data.x, query_data.edge_index)

        if self.database_matrix.numel() == 0:
            return []

        similarities = F.cosine_similarity(query_vec, self.database_matrix)
        top_scores, top_indices = torch.topk(similarities, k=min(top_k, self.database_matrix.size(0)))

        results = []
        for score, idx in zip(top_scores, top_indices):
            data = self.dataset[idx.item()]
            results.append(
                {
                    "score": float(score.item()),
                    "sql": getattr(data, "sql", "<no-sql-field>"),
                    "db_id": getattr(data, "db_id", None),
                }
            )
        return results


if __name__ == "__main__":
    from config import Config

    vocab_p = os.getenv("TEXT2SQL_GNN_VOCAB_PATH", str(Config.GNN_VOCAB_PATH))
    dataset_p = os.getenv("TEXT2SQL_GNN_DATASET_PATH", str(Config.GNN_DATASET_PATH))
    weights_p = os.getenv("TEXT2SQL_GNN_WEIGHTS_PATH", str(Config.GNN_WEIGHTS_PATH))

    retriever = GraphRetriever(weights_p, vocab_p, dataset_p)

    p_sql = (
        "SELECT AVG(T1.A15) FROM district AS T1 "
        "INNER JOIN account AS T2 ON T1.district_id = T2.district_id "
        "WHERE STRFTIME('%Y', T2.date) >= '1997' AND T1.A15 > 4000"
    )

    res = retriever.search_similar_sql(p_sql, top_k=3)
    print("检索结果：")
    for i, r in enumerate(res):
        print(f"[{i + 1}] score={r['score']:.4f} db={r['db_id']}\n  sql={r['sql']}\n")
