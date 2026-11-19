"""Tests are offline and never load the project's real credential file."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent/src"))
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@127.0.0.1:1/guardrail_test"
os.environ["AWS_ACCESS_KEY_ID"] = "test-only"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test-only"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
