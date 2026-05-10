from tqdm import tqdm

from config import Config
from core.schema_trim import generate_trimmed_schema
from core.semantic_mapper import SemanticHeatMapper
from core.topology import TopologyGraphBuilder
from services.example_retriever import ExampleRetriever
from services.modelscope_engine import ModelScopeWorkflowEngine
from utils.io_utils import (
    load_json,
    read_text,
    resolve_raw_schema_file_path,
    resolve_trim_schema_file_path,
    save_json,
)
from utils.value_hints import build_column_value_hints

class TaskManager:
    def __init__(self) -> None:
        self.engine = ModelScopeWorkflowEngine()
        self.results_map = self._load_existing_results()
        self.db_cache: dict[str, tuple[TopologyGraphBuilder, SemanticHeatMapper]] = {}
        self.current_db_id = None
        self.example_retriever = ExampleRetriever()

    def _load_existing_results(self) -> dict:
        if not Config.FINAL_OUTPUT_PATH.exists():
            return {}

        existing = load_json(Config.FINAL_OUTPUT_PATH)
        return {item["question_id"]: item for item in existing}

    def _get_db_handler(
        self,
        db_id: str,
        raw_schema_txt: str,
    ) -> tuple[TopologyGraphBuilder, SemanticHeatMapper]:
        if db_id in self.db_cache:
            print(f"\n🔥 缓存命中: 复用[{db_id}]的拓扑结构和虚拟关联边")
            return self.db_cache[db_id]

        print(f"\n❌ 缓存未命中: 首次构建[{db_id}]的拓扑结构和虚拟关联边")

        db_path = Config.DB_ROOT_DIR / db_id / f"{db_id}.sqlite"
        builder = TopologyGraphBuilder(str(db_path), raw_schema_txt)
        builder.build_structure()

        mapper = SemanticHeatMapper(builder)

        self.db_cache[db_id] = (builder, mapper)
        return builder, mapper

    def _cleanup_cache(self) -> None:
        print(f"\n🧹 开始清理数据库缓存（共{len(self.db_cache)}个数据库）")
        for _, (builder, _) in self.db_cache.items():
            builder.close()
        self.db_cache.clear()
        print("✅ 缓存清理完成，所有数据库连接已关闭")

    @staticmethod
    def _group_questions_by_db(todo: list[dict]) -> dict[str, list[dict]]:
        db_question_map: dict[str, list[dict]] = {}
        for item in todo:
            db_id = item["db_id"]
            if db_id not in db_question_map:
                db_question_map[db_id] = []
            db_question_map[db_id].append(item)
        return db_question_map

    def _save_to_disk(self) -> None:
        final_list = sorted(
            list(self.results_map.values()),
            key=lambda x: x["question_id"],
        )
        save_json(
            Config.FINAL_OUTPUT_PATH,
            final_list,
            indent=2,
            ensure_ascii=False,
        )

    def _build_result_entry(
        self,
        item: dict,
        db_id: str,
        raw_main: str,
        raw_supp: str,
        active_nodes: list[str],
        p_sql: str,
        examples_str: str,
        relationship,
        new_schema: str,
        column_value_hints: str,
        corrected_sql: str,
        grads: dict,
    ) -> dict:
        new_entry = {
            "question_id": item["question_id"],
            "db_id": db_id,
            "question": item["question"],
            "evidence": item.get("evidence", ""),
            "raw_llm_response": raw_main,
            "supplement_llm_response": raw_supp,
            "active_schema_nodes": active_nodes,
            "p_sql": p_sql,
            "examples_used": examples_str,
            "relationship": relationship,
            "new_schema": new_schema,
            "column_value_hints": column_value_hints,
            "corrected_sql": corrected_sql,
            "SQL": item.get("SQL", ""),
        }
        new_entry.update(grads)
        return new_entry

    def _process_single_question(
        self,
        item: dict,
        db_id: str,
        raw_schema_txt: str,
        trim_schema_txt: str,
        mapper: SemanticHeatMapper | None,
    ) -> dict:
        question = item["question"]
        evidence = item.get("evidence", "")

                                                         
        grads, raw_main = self.engine.call_decomposition(
            question,
            evidence,
            raw_schema_txt,
        )
        if mapper and raw_main:
            mapper.process_and_map(raw_main)

                                                                
        raw_supp = self.engine.call_supplement_workflow(
            question,
            evidence,
            raw_schema_txt,
        )
        if mapper and raw_supp:
            mapper.process_supplementary_info(raw_supp)

                       
        if mapper:
            mapper.activate_virtual_related_nodes()

                 
        active_nodes = mapper.execute_steiner_search() if mapper else []

                                                                        
        new_schema = generate_trimmed_schema(trim_schema_txt, active_nodes)
        db_path = Config.DB_ROOT_DIR / db_id / f"{db_id}.sqlite"

        column_value_hints = build_column_value_hints(
            db_path=db_path,
            active_nodes=active_nodes,
            question=question,
            evidence=evidence,
            value_limit_per_column=3,
            matched_value_limit_per_column=3,
            max_distinct_scan_per_column=5000,
            match_threshold=0.92,
        )
        relationship = mapper.relationship if mapper else []

        retrieval_result = self.example_retriever.retrieve_examples(item["question_id"])
        p_sql = retrieval_result["p_sql"]
        examples_str = retrieval_result["examples"]

        corrected_sql = self.engine.call_corrected_workflow(
            question=question,
            evidence=evidence,
            relationship=relationship,
            new_schema=new_schema,
            examples=examples_str,
            column_value_hints=column_value_hints,
        )

        return self._build_result_entry(
            item=item,
            db_id=db_id,
            raw_main=raw_main,
            raw_supp=raw_supp,
            active_nodes=active_nodes,
            p_sql=p_sql,
            examples_str=examples_str,
            relationship=relationship,
            new_schema=new_schema,
            column_value_hints=column_value_hints,
            corrected_sql=corrected_sql,
            grads=grads,
        )
    
    def run(self) -> None:
        try:
            full_dataset = load_json(Config.INPUT_PATH)

            todo = [
                item
                for item in full_dataset
                if item["question_id"] not in self.results_map
            ][: Config.PROCESS_LIMIT]

            db_question_map = self._group_questions_by_db(todo)

            for db_id, questions in db_question_map.items():
                print(f"\n📊 开始处理数据库[{db_id}]的{len(questions)}个问题")

                raw_schema_file_path = resolve_raw_schema_file_path(db_id)
                trim_schema_file_path = resolve_trim_schema_file_path(db_id)

                print(f"🔍 [主抽取/补充抽取/拓扑构建] 读取原始Schema文件: {raw_schema_file_path}")
                print(f"🔍 [Schema裁剪] 读取GPT增强Schema文件: {trim_schema_file_path}")

                raw_schema_txt = read_text(raw_schema_file_path)
                trim_schema_txt = read_text(trim_schema_file_path)

                _, mapper = self._get_db_handler(db_id, raw_schema_txt)
                self.current_db_id = db_id

                for item in tqdm(questions, desc=f"处理[{db_id}]的问题"):
                    new_entry = self._process_single_question(
                        item=item,
                        db_id=db_id,
                        raw_schema_txt=raw_schema_txt,
                        trim_schema_txt=trim_schema_txt,
                        mapper=mapper,
                    )
                    self.results_map[item["question_id"]] = new_entry
                    self._save_to_disk()

        finally:
            self._cleanup_cache()