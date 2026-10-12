import os


OLLAMA_URL = os.environ.get("ARIA_OLLAMA_URL", "http://localhost:11434")
VLM_MODEL = os.environ.get("ARIA_VLM_MODEL", "qwen3-vl:2b")
INFERENCE_BACKEND = os.environ.get("ARIA_INFERENCE_BACKEND", "llama-server")
LLAMA_SERVER_URL = os.environ.get("ARIA_LLAMA_SERVER_URL", "http://127.0.0.1:8081/v1/chat/completions")
LLAMA_MODEL = os.environ.get("ARIA_LLAMA_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m")
ENABLE_VERIFICATION = os.environ.get("ARIA_ENABLE_VERIFICATION", "1").strip().lower() in {"1", "true", "yes", "on"}
SANDBOX_WORKSPACE = os.environ.get("ARIA_SANDBOX_WORKSPACE", "research/test_workspace")
PERCEPTION_MODE = os.environ.get("ARIA_PERCEPTION_MODE", "text_grounded")
TELEGRAM_BOT_TOKEN = os.environ.get("ARIA_TELEGRAM_TOKEN", "")
SQLITE_PATH = "aria_memory.db"
SCREEN_DIFF_THRESHOLD = 0.05
TRIGGER_DEBOUNCE_SECONDS = 1.0
MAX_REPLAN_ATTEMPTS = 3
SCREENSHOT_FORMAT = "PNG"

