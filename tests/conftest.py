import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SQ_PROVIDERS", "sim")

import pytest


@pytest.fixture()
def tmp_store():
    from sportsquant.data.store import Store
    return Store(os.path.join(tempfile.mkdtemp(), "test.db"))
