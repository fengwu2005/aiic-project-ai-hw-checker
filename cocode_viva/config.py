from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SESSION_DIR = DATA_DIR / "sessions"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_EXTRACTED_FILES = 80

EXPECTED_FILES = {
    "readme": "README.md",
    "final_code": "final/taskflow.py",
    "tests": "tests/test_taskflow.py",
    "initial_prompt": "ai/ai_initial_prompt.md",
    "initial_output": "ai/ai_initial_output.md",
    "interaction_log": "ai/interaction_log.md",
    "reflection": "report/reflection.md",
}


for directory in (DATA_DIR, UPLOAD_DIR, SESSION_DIR):
    directory.mkdir(parents=True, exist_ok=True)

