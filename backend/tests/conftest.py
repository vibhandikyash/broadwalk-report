import os
import tempfile

os.environ["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="irg-test-")
os.environ["APP_WORKERS"] = "2"
os.environ.pop("ANTHROPIC_API_KEY", None)
