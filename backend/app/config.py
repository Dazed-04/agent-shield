"""Central gateway configuration. Everything tunable is overridable via environment."""

import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentshield.db")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
# Set to 1 to skip loading the sentence-transformer (tests / constrained hosts).
DISABLE_EMBEDDINGS = _env_bool("AGENT_SHIELD_DISABLE_EMBEDDINGS", False)

# "production" (secure default): X-API-Key required, roles bound server-side.
# "development": client may declare its role; admin endpoints are open. Local use only.
DEFAULT_SECURITY_ENV = "production"
SECURITY_ENV = os.getenv("SECURITY_ENV", DEFAULT_SECURITY_ENV).lower()

# Comma-separated list of allowed browser origins. Empty => same-origin only.
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]

# Policy thresholds (inclusive upper bound of each band)
ALLOW_MAX = _env_float("ALLOW_MAX", 25)
WARN_MAX = _env_float("WARN_MAX", 55)
APPROVE_MAX = _env_float("APPROVE_MAX", 80)

# Detector weights used by the risk engine (should sum to 1.0)
WEIGHT_PROMPT = _env_float("WEIGHT_PROMPT", 0.40)
WEIGHT_JAILBREAK = _env_float("WEIGHT_JAILBREAK", 0.35)
WEIGHT_TOOL = _env_float("WEIGHT_TOOL", 0.25)

# Agent loop
MAX_AGENT_STEPS = int(_env_float("MAX_AGENT_STEPS", 6))
SPOTLIGHT_TOOL_OUTPUT = _env_bool("SPOTLIGHT_TOOL_OUTPUT", True)

# Sandboxed code execution
CODE_EXEC_TIMEOUT_S = int(_env_float("CODE_EXEC_TIMEOUT_S", 5))
CODE_EXEC_MEMORY_MB = int(_env_float("CODE_EXEC_MEMORY_MB", 256))
MAX_TOOL_OUTPUT_CHARS = int(_env_float("MAX_TOOL_OUTPUT_CHARS", 20000))
MAX_PROMPT_CHARS = int(_env_float("MAX_PROMPT_CHARS", 50000))

# Learned threat phrases (active learning). Keep this on a writable volume in containers.
THREAT_VECTORS_PATH = os.getenv(
    "THREAT_VECTORS_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "config/threat_vectors.json")),
)

# Where `python -m evaluation` writes run folders; the dashboard reads them from here (admin only).
EVAL_RESULTS_DIR = os.getenv(
    "EVAL_RESULTS_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "evaluation", "results")),
)
