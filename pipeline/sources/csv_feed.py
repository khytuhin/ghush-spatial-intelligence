"""An approved public CSV full export can refresh without manual uploads."""
from io import BytesIO
import pandas as pd
from .http import assert_robots_allowed, get_bytes

def load_csv_feed(url, token=None):
    assert_robots_allowed(url)
    return pd.read_csv(BytesIO(get_bytes(url, token=token, accept="text/csv")), dtype=str, keep_default_na=False)
