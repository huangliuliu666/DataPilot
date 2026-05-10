from pathlib import Path

from config import Config
from sql_retriever import GraphRetriever
from utils.io_utils import load_json


class ExampleRetriever:

    def __init__(self) -> None:
        self.sql_to_data_map: dict[str, dict[str, str]] = {}
        self.psql_map: dict[str, str] = {}
        self.cache: dict[str, dict[str, str]] = {}

        self.sql_to_data_map = self._build_sql_to_data_map(Config.TRAIN_JSON_PATH)
        self.psql_map = self._load_psql_map(Config.P_SQL_JSON_PATH)

        self.retriever = GraphRetriever(
            Config.WEIGHTS_PATH,
            Config.VOCAB_PATH,
            Config.DATASET_PATH,
        )

    def _build_sql_to_data_map(self, train_json_path: str | Path) -> dict[str, dict[str, str]]:
        path = Path(train_json_path)
        if not path.exists():
            raise FileNotFoundError(f"TRAIN_JSON_PATH not found: {path}")

        mapping: dict[str, dict[str, str]] = {}
        for item in load_json(path):
            sql = item.get("SQL", "").strip()
            if sql:
                mapping[sql] = {
                    "question": item.get("question", ""),
                    "evidence": item.get("evidence", ""),
                }
        return mapping

    def _load_psql_map(self, psql_json_path: str | Path) -> dict[str, str]:
        path = Path(psql_json_path)
        if not path.exists():
            raise FileNotFoundError(f"P_SQL_JSON_PATH not found: {path}")

        mapping: dict[str, str] = {}
        for item in load_json(path):
            qid = item.get("question_id")
            psql = item.get("predicted_sql", "")
            if qid is None:
                raise ValueError(f"P-SQL item missing question_id: {item}")
            if not psql:
                raise ValueError(f"P-SQL item missing predicted_sql for question_id={qid}")
            mapping[qid] = psql
            mapping[str(qid)] = psql
        return mapping

    def _format_examples(self, reranked_results: list[dict]) -> str:
        if not reranked_results:
            return "No valid examples found."

        formatted = []
        for i, res in enumerate(reranked_results[: Config.RETRIEVE_TOP_K]):
            q = res.get("question", "")
            e = res.get("evidence", "")
            s = res.get("sql", "")
            formatted.append(
                f"Example {i + 1}:\n"
                f"Question: {q}\n"
                f"Evidence: {e}\n"
                f"SQL: {s}\n"
            )
        return "\n".join(formatted)

    def _get_psql_by_qid(self, question_id) -> str:
        if question_id in self.psql_map:
            return self.psql_map[question_id]
        if str(question_id) in self.psql_map:
            return self.psql_map[str(question_id)]
        raise KeyError(f"No P-SQL found for question_id={question_id}")

    def retrieve_examples(self, question_id) -> dict[str, str]:
        if question_id in self.cache:
            return self.cache[question_id]

        p_sql = self._get_psql_by_qid(question_id)
        top_candidates = self.retriever.search_similar_sql(
            p_sql,
            top_k=Config.RETRIEVE_TOP_K,
        )

        if not isinstance(top_candidates, list):
            raise TypeError(f"GraphRetriever returned non-list result: {top_candidates}")

        reranked_pool = []
        for candidate in top_candidates:
            cand_sql = candidate.get("sql", "")
            s_topo = candidate.get("score", 0.0)

            mapped_data = self.sql_to_data_map.get(cand_sql, {})
            q_candidate = mapped_data.get("question", "")
            e_candidate = mapped_data.get("evidence", "")

            reranked_pool.append(
                {
                    "sql": cand_sql,
                    "question": q_candidate,
                    "evidence": e_candidate,
                    "s_final": s_topo,
                }
            )

        reranked_pool.sort(key=lambda x: x["s_final"], reverse=True)

        result = {
            "p_sql": p_sql,
            "examples": self._format_examples(reranked_pool),
        }
        self.cache[question_id] = result
        return result
