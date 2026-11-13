"""Run the server: python -m app

Reads HOST, PORT and RELOAD from the environment or the repo-root .env file.
"""

import logging
import os
import threading
import webbrowser

import uvicorn
from dotenv import load_dotenv

from .config import ROOT_DIR

if __name__ == "__main__":
    load_dotenv(ROOT_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    print(f"\n  Text-to-SQL is starting: open {url}\n")
    if os.environ.get("OPEN_BROWSER", "").lower() in {"1", "true", "yes"}:
        threading.Timer(2.0, webbrowser.open, args=[url]).start()
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=os.environ.get("RELOAD", "").lower() in {"1", "true", "yes"},
    )
