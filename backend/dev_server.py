import os
from pathlib import Path

import uvicorn


BACKEND_DIR = Path(__file__).resolve().parent
RELOAD_EXCLUDE_DIRS = [
    "data",
    "processed_files",
    "profiles",
    "uploads",
]
RELOAD_EXCLUDE_PATTERNS = [
    "processed_files/*",
    "processed_files/**/*",
    "profiles/*",
    "profiles/**/*",
    "uploads/*",
    "uploads/**/*",
]


if __name__ == "__main__":
    os.chdir(BACKEND_DIR)
    uvicorn.run(
        "main:app",
        host=os.getenv("UVICORN_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", os.getenv("UVICORN_PORT", "8000"))),
        app_dir=str(BACKEND_DIR),
        reload=True,
        reload_dirs=["."],
        reload_includes=["*.py"],
        reload_excludes=[
            *RELOAD_EXCLUDE_DIRS,
            *RELOAD_EXCLUDE_PATTERNS,
        ],
    )
