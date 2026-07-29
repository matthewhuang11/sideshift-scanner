from pathlib import Path

import pytest

from ugc_analytics.db import get_connection, init_db
from ugc_analytics.ingestion.base import sync_all
from ugc_analytics.ingestion.csv_adapter import CSVIngestionAdapter

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def seeded_conn(conn):
    sync_all(conn, CSVIngestionAdapter(SAMPLE_DATA_DIR))
    return conn
