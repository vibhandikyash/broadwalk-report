import os
import tempfile

os.environ["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="irg-test-")
os.environ["APP_WORKERS"] = "2"
# Empty values deliberately override the developer's local .env during tests.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
