"""Keep private QA totals out of publicly readable Actions logs."""
import logging
import os

def counts(**values):
    public = os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("GHUSH_PUBLIC_LOGS", "true") != "false"
    safe = {key: value if not public or key == "published" else "private" for key, value in values.items()}
    logging.info(" ".join(f"{key}={value}" for key, value in safe.items()))
