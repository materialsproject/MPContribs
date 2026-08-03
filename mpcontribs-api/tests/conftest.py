import os

from dotenv import load_dotenv

# Load .env *before* setdefault calls so real credentials take precedence.
# load_dotenv is a no-op when .env doesn't exist (CI / pure unit-test runs).
load_dotenv()

# Fallbacks for any value not supplied by .env (CI, unit-only runs, etc.)
os.environ.setdefault("MPCONTRIBS_ENVIRONMENT", "dev")
os.environ.setdefault("MPCONTRIBS_MONGO__URI", "mongodb://localhost:27017")
os.environ.setdefault("MPCONTRIBS_MONGO__DB_NAME", "testdb")
os.environ.setdefault("MPCONTRIBS_REDIS__ADDRESS", "redis://localhost:6379")
os.environ.setdefault("MPCONTRIBS_REDIS__URL", "redis://localhost:6379")
os.environ.setdefault("MPCONTRIBS_MAIL_DEFAULT_SENDER", "test@example.com")
os.environ.setdefault("MPCONTRIBS_VERSION", "0.0.0-test")
# No OTLP collector in tests: keep telemetry off so the suite doesn't register providers or export.
os.environ.setdefault("MPCONTRIBS_OTEL__ENABLED", "false")
