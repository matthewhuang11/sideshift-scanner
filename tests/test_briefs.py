import pytest

from ugc_analytics.analysis.briefs import generate_content_brief


def test_generate_content_brief_unknown_creator_raises(seeded_conn):
    with pytest.raises(ValueError):
        generate_content_brief(seeded_conn, creator_id="does-not-exist")


def test_generate_content_brief_respects_explicit_format(seeded_conn):
    brief = generate_content_brief(seeded_conn, creator_id="c5", based_on_format="skit")
    assert brief.target_format == "skit"
    assert brief.rationale == "format explicitly requested"
    assert "Sam Okafor" in brief.draft_brief


def test_generate_content_brief_picks_a_format_when_unspecified(seeded_conn):
    brief = generate_content_brief(seeded_conn, creator_id="c1")
    assert brief.target_format
    assert brief.rationale
