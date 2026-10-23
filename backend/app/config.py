import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentshield.db")

_raw_keys = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Security Mode: "development" (allows testing bypass/role-spoofing) or "production" (strict Zero-Trust enforcement)
SECURITY_ENV = os.getenv("SECURITY_ENV", "development").lower()

# Policy Thresholds
ALLOW_MAX = 25
WARN_MAX = 55
APPROVE_MAX = 80
