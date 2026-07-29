from ugc_analytics.analysis.matching import recommend_creators_for_brief
from ugc_analytics.analysis.performance import get_performance_summary, top_performers
from ugc_analytics.analysis.profiling import get_creator_profile, list_creators
from ugc_analytics.analysis.trends import detect_trending_formats
from ugc_analytics.db import upsert_content_item, upsert_performance_metric
from ugc_analytics.models import ContentItem, PerformanceMetric


def test_list_creators_filters_by_niche(seeded_conn):
    fitness = list_creators(seeded_conn, niche="fitness")
    assert {c["creator_id"] for c in fitness} == {"c3", "c5"}


def test_list_creators_filters_by_status(seeded_conn):
    applied = list_creators(seeded_conn, status="applied")
    assert [c["creator_id"] for c in applied] == ["c4"]


def test_get_creator_profile_returns_none_for_unknown(seeded_conn):
    assert get_creator_profile(seeded_conn, creator_id="does-not-exist") is None


def test_get_creator_profile_has_performance_and_formats(seeded_conn):
    profile = get_creator_profile(seeded_conn, creator_id="c3")
    assert profile.name == "Priya Nair"
    assert profile.content_count == 3
    assert profile.performance["sample_size"] == 3
    assert set(profile.best_formats) & {"hook-question", "unboxing", "voiceover", "energetic"}


def test_get_performance_summary_global(seeded_conn):
    summary = get_performance_summary(seeded_conn)
    assert summary.sample_size == 12
    assert summary.totals["views"] == 811000


def test_get_performance_summary_scoped_to_creator(seeded_conn):
    summary = get_performance_summary(seeded_conn, scope="creator", scope_id="c1")
    assert summary.sample_size == 3


def test_top_performers_ranked_desc(seeded_conn):
    top = top_performers(seeded_conn, metric="views", n=3)
    values = [row["value"] for row in top]
    assert values == sorted(values, reverse=True)
    assert top[0]["content_id"] == "ct8"


def test_top_performers_include_unlisted_toggle(seeded_conn):
    # content from a creator not in the creators table (e.g. a SideShift
    # ghost handle) -- no FK enforced on purpose, see db.py.
    upsert_content_item(
        seeded_conn,
        ContentItem(content_id="ghost1", creator_id="ghost-xyz", platform="tiktok", format_tags=["viral"]),
    )
    upsert_performance_metric(
        seeded_conn, PerformanceMetric(content_id="ghost1", snapshot_date="2025-07-01", views=999999)
    )
    seeded_conn.commit()

    included = top_performers(seeded_conn, metric="views", n=20, include_unlisted=True)
    assert any(r["content_id"] == "ghost1" for r in included)
    ghost_row = next(r for r in included if r["content_id"] == "ghost1")
    assert ghost_row["is_unlisted"]
    assert "ghost-xyz" in ghost_row["creator_name"]

    excluded = top_performers(seeded_conn, metric="views", n=20, include_unlisted=False)
    assert all(r["content_id"] != "ghost1" for r in excluded)


def test_top_performers_rejects_unknown_metric(seeded_conn):
    import pytest

    with pytest.raises(ValueError):
        top_performers(seeded_conn, metric="not_a_real_metric")


def test_detect_trending_formats_respects_min_sample_size(seeded_conn):
    trends = detect_trending_formats(seeded_conn, min_sample_size=10)
    assert trends == []


def test_detect_trending_formats_sorted_by_multiplier(seeded_conn):
    trends = detect_trending_formats(seeded_conn, min_sample_size=2)
    multipliers = [t.multiplier for t in trends]
    assert multipliers == sorted(multipliers, reverse=True)


def test_recommend_creators_for_brief_requires_input(seeded_conn):
    import pytest

    with pytest.raises(ValueError):
        recommend_creators_for_brief(seeded_conn)


def test_recommend_creators_for_brief_returns_rationale(seeded_conn):
    results = recommend_creators_for_brief(seeded_conn, brief_text="unboxing video with a hook question", n=3)
    assert results
    assert all("rationale" in r and r["rationale"] for r in results)
    assert results[0]["score"] >= results[-1]["score"]
