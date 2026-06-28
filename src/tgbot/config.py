import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    bot_token: str = os.environ["BOT_TOKEN"]
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
    db_path: str = os.getenv("DB_PATH", "tgbot.db")
    owner_user_id: int | None = int(v) if (v := os.getenv("OWNER_USER_ID")) else None
    word_threshold: int = int(os.getenv("WORD_THRESHOLD", "15"))
    agent_idle_seconds: int = int(os.getenv("AGENT_IDLE_SECONDS", "600"))
    agent_max_queries: int = int(os.getenv("AGENT_MAX_QUERIES", "50"))

    # --- Backend selection ---
    # "claude"  — use AgentSdkTranslator (default, keeps existing behavior)
    # "local"   — use LocalLlmTranslator (httpx → mlx_lm.server)
    translator_backend: str = os.getenv("TRANSLATOR_BACKEND", "claude")

    # Per-task routing override (JSON object mapping task name → backend).
    # Example: '{"translate_to_hebrew":"local"}' — HE via local, rest via TRANSLATOR_BACKEND.
    translator_task_backends: str = os.getenv("TRANSLATOR_TASK_BACKENDS", "")

    # Local LLM server (used when translator_backend == "local")
    local_llm_url: str = os.getenv("LOCAL_LLM_URL", "http://localhost:8080/v1")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "dictalm3-nemotron-12b")

    # Pronunciation script: cyrillic | latin | both
    # "both" outputs Cyrillic + Latin on separate lines — use during eval to compare side-by-side.
    pron_style: str = os.getenv("PRON_STYLE", "cyrillic")

    # Append /nothink to system prompts for local backend (disables Qwen3 chain-of-thought).
    # Harmless for models that don't support it. Default: true.
    local_llm_nothink: bool = os.getenv("LOCAL_LLM_NOTHINK", "true").lower() == "true"

    # Set to true for models that don't support the system role (e.g. DictaLM 2.0 / Zephyr).
    # System prompt is merged into the first user message instead.
    local_llm_no_system_role: bool = os.getenv("LOCAL_LLM_NO_SYSTEM_ROLE", "false").lower() == "true"


config = Config()
