from pathlib import Path
import os


class Config:
    MODELSCOPE_BASE_URL = os.getenv(
        "MODELSCOPE_BASE_URL",
        "https://api-inference.modelscope.cn/v1",
    )
    MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
    MODELSCOPE_MODEL = os.getenv("MODELSCOPE_MODEL", "Qwen/Qwen3-32B")
    MODELSCOPE_ENABLE_THINKING = os.getenv("MODELSCOPE_ENABLE_THINKING", "0") == "1"

    MODELSCOPE_TEMPERATURE = float(os.getenv("MODELSCOPE_TEMPERATURE", "0.7"))
    MODELSCOPE_TOP_P = float(os.getenv("MODELSCOPE_TOP_P", "0.8"))
    MODELSCOPE_TOP_K = int(os.getenv("MODELSCOPE_TOP_K", "20"))

    MODELSCOPE_DECOMPOSE_TEMPERATURE = float(os.getenv("MODELSCOPE_DECOMPOSE_TEMPERATURE", "0.7"))
    MODELSCOPE_QUESTION_SPLIT_TEMPERATURE = float(os.getenv("MODELSCOPE_QUESTION_SPLIT_TEMPERATURE", "0.7"))
    MODELSCOPE_SUPP_EXTRACT_TEMPERATURE = float(os.getenv("MODELSCOPE_SUPP_EXTRACT_TEMPERATURE", "0.7"))
    MODELSCOPE_SQL_TEMPERATURE = float(os.getenv("MODELSCOPE_SQL_TEMPERATURE", "0.1"))

    BASE_DIR = Path(os.getenv("TEXT2SQL_BASE_DIR", Path(__file__).resolve().parent))
    AGENT_MEMORY_DIR = Path(os.getenv("TEXT2SQL_MEMORY_DIR", BASE_DIR / "data" / "agent_memory"))
    WORKSPACE_DIR = Path(os.getenv("TEXT2SQL_WORKSPACE_DIR", BASE_DIR / "data" / "workspaces"))
    AGENT_DEFAULT_RESULT_LIMIT = int(os.getenv("TEXT2SQL_RESULT_LIMIT", "100"))

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/embeddings")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "bge-m3")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
    OLLAMA_EMBEDDING_MAX_CHARS = int(os.getenv("OLLAMA_EMBEDDING_MAX_CHARS", "4000"))

                                                                                   
                                                                                             
    PROCESS_LIMIT = int(os.getenv("TEXT2SQL_PROCESS_LIMIT", "1"))
    SAVE_INTERVAL = int(os.getenv("TEXT2SQL_SAVE_INTERVAL", "1"))
    TIMEOUT = int(os.getenv("TEXT2SQL_TIMEOUT", "125"))

                                                      
                                                                                                  
    GNN_MODEL_DIR = Path(os.getenv("TEXT2SQL_GNN_MODEL_DIR", BASE_DIR / "gnn_model"))
    GNN_VOCAB_PATH = Path(os.getenv("TEXT2SQL_GNN_VOCAB_PATH", GNN_MODEL_DIR / "ast_vocab.pt"))
    GNN_DATASET_PATH = Path(os.getenv("TEXT2SQL_GNN_DATASET_PATH", GNN_MODEL_DIR / "spider_ast_dataset.pt"))
    GNN_WEIGHTS_PATH = Path(os.getenv("TEXT2SQL_GNN_WEIGHTS_PATH", GNN_MODEL_DIR / "best_gnn_encoder.pth"))

                                                                               
    VOCAB_PATH = GNN_VOCAB_PATH
    DATASET_PATH = GNN_DATASET_PATH
    WEIGHTS_PATH = GNN_WEIGHTS_PATH

    RETRIEVE_TOP_K = int(os.getenv("TEXT2SQL_RETRIEVE_TOP_K", "1"))
    HYBRID_EXAMPLE_TOP_K = int(os.getenv("TEXT2SQL_HYBRID_EXAMPLE_TOP_K", "5"))
    TEXT_EXAMPLE_TOP_K = int(os.getenv("TEXT2SQL_TEXT_EXAMPLE_TOP_K", "3"))
    WORKSPACE_STRUCTURE_EXAMPLE_TOP_K = int(os.getenv("TEXT2SQL_WORKSPACE_STRUCTURE_EXAMPLE_TOP_K", "2"))
    USE_TOPOLOGY_TRIMMING = os.getenv("TEXT2SQL_USE_TOPOLOGY_TRIMMING", "1") == "1"
    USE_SQL_STRUCTURE_RETRIEVAL = os.getenv("TEXT2SQL_USE_SQL_STRUCTURE_RETRIEVAL", "0") == "1"
    USE_GLOBAL_STRUCTURE_EXAMPLES = os.getenv("TEXT2SQL_USE_GLOBAL_STRUCTURE_EXAMPLES", "1") == "1"


VALUE_OVERLAP_CONFIG = {
    "MINHASH_PERM": 128,
    "ENUM_THRESHOLD": 4,
    "JACCARD_THRESHOLD": 0.5,
    "SPARSITY_THRESHOLD": 5.0,
    "SEED": 42,
}

PATENT_CONFIG = VALUE_OVERLAP_CONFIG
