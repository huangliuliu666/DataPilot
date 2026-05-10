from __future__ import annotations

from pathlib import Path
from typing import Any

import torch

from sql_retriever import (
    SQLTopologyEncoder,
    extract_state_dict,
    load_state_dict_flexibly,
    safe_torch_load,
    text_to_pyg_data,
)


class SQLStructureEncoder:

    def __init__(
        self,
        *,
        vocab_path: str | Path,
        weights_path: str | Path,
        device: str = "cuda",
    ) -> None:
        self.vocab_path = Path(vocab_path)
        self.weights_path = Path(weights_path)
        if not self.vocab_path.exists():
            raise FileNotFoundError(f"GNN vocab file not found: {self.vocab_path}")
        if not self.weights_path.exists():
            raise FileNotFoundError(f"GNN weights file not found: {self.weights_path}")

        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.vocab: dict[str, int] = torch.load(self.vocab_path, map_location="cpu", weights_only=False)
        self.model = SQLTopologyEncoder(vocab_size=len(self.vocab), hidden_dim=768).to(self.device)
        checkpoint = safe_torch_load(str(self.weights_path), map_location=self.device)
        state_dict = extract_state_dict(checkpoint)
        load_state_dict_flexibly(self.model, state_dict, self.device)
        self.model.eval()

    def encode(self, sql: str) -> torch.Tensor:
        data = text_to_pyg_data(sql, self.vocab)
        if data is None:
            raise ValueError(f"SQL cannot be parsed into AST for GNN structure retrieval: {sql}")
        data = data.to(self.device)
        with torch.no_grad():
            vec = self.model(data.x, data.edge_index)
        return vec.detach().cpu().squeeze(0)

    @staticmethod
    def cosine(query_vec: torch.Tensor, candidate_matrix: torch.Tensor) -> torch.Tensor:
        query = query_vec.unsqueeze(0)
        return torch.nn.functional.cosine_similarity(query, candidate_matrix)
