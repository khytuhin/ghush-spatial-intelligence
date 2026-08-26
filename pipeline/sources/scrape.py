"""Reserved adapter. DOM ingestion is deliberately unavailable until independently verified."""
def load_scrape(url, config_path):
    raise RuntimeError(
        "DOM scraping is not production-verified and is disabled. "
        "Use an approved JSON/CSV export. Do not work around Ghush's API robots restriction by scraping."
    )
