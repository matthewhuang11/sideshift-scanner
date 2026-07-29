from ugc_analytics.db import row_to_creator, upsert_creator
from ugc_analytics.models import Creator


def test_init_db_creates_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"creators", "campaigns", "content_items", "performance_metrics", "sync_log"} <= tables


def test_upsert_creator_roundtrip(conn):
    creator = Creator(
        creator_id="x1",
        name="Test Creator",
        handle="@test",
        platforms={"tiktok": "@test"},
        niche_tags=["fitness"],
        tone_style_tags=["casual"],
        status="active",
        joined_date="2025-01-01",
    )
    upsert_creator(conn, creator)
    conn.commit()

    row = conn.execute("SELECT * FROM creators WHERE creator_id = ?", ("x1",)).fetchone()
    restored = row_to_creator(row)
    assert restored == creator


def test_upsert_creator_is_idempotent(conn):
    creator = Creator(creator_id="x1", name="Original")
    upsert_creator(conn, creator)
    updated = Creator(creator_id="x1", name="Renamed")
    upsert_creator(conn, updated)
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    assert count == 1
    row = conn.execute("SELECT name FROM creators WHERE creator_id='x1'").fetchone()
    assert row["name"] == "Renamed"
