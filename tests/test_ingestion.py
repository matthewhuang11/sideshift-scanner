from ugc_analytics.ingestion.base import sync_all
from ugc_analytics.ingestion.csv_adapter import CSVIngestionAdapter
from tests.conftest import SAMPLE_DATA_DIR


def test_csv_sync_ingests_sample_data(conn):
    result = sync_all(conn, CSVIngestionAdapter(SAMPLE_DATA_DIR))

    assert result.status == "ok"
    assert result.creators_ingested == 5
    assert result.content_items_ingested == 12
    assert result.metrics_ingested == 18

    assert conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 12


def test_csv_sync_is_idempotent(conn):
    adapter = CSVIngestionAdapter(SAMPLE_DATA_DIR)
    sync_all(conn, adapter)
    sync_all(conn, adapter)

    assert conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0] == 5


def test_csv_sync_logs_result(conn):
    sync_all(conn, CSVIngestionAdapter(SAMPLE_DATA_DIR))
    log_rows = conn.execute("SELECT * FROM sync_log").fetchall()
    assert len(log_rows) == 1
    assert log_rows[0]["status"] == "ok"
    assert log_rows[0]["method"] == "csv"


def test_csv_sync_handles_missing_source_gracefully(conn, tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = sync_all(conn, CSVIngestionAdapter(empty_dir))
    assert result.status == "ok"
    assert result.creators_ingested == 0
