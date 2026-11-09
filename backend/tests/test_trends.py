"""Rising topics, the trend brief prompt and its messages (PLAN Phase 7). Pure functions only."""

import hashlib
from datetime import UTC, datetime, timedelta

from app.ai import trends
from app.ai.assistant import Evidence
from app.ai.trends import RisingTerm, rising

PROMPT_HASHES = {
    "trend-brief-v1": "9ac0f220cc3f497da39788f9665b4adf52b225874d21f41f3e8c460bf947e191",
}
NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def days_ago(d: float) -> datetime:
    return NOW - timedelta(days=d)


def rows(recent: list[list[str]], baseline: list[list[str]]) -> list[tuple[datetime, list[str]]]:
    return [(days_ago(1), t) for t in recent] + [(days_ago(10), t) for t in baseline]


def test_prompt_hash_pinned_to_version():
    digest = hashlib.sha256(trends.PROMPT_PATH.read_bytes()).hexdigest()
    assert PROMPT_HASHES.get(trends.PROMPT_VERSION) == digest, (
        "prompts/trend_brief.md changed: bump PROMPT_VERSION and add its hash to PROMPT_HASHES"
    )


def test_change_is_share_of_items_not_raw_count():
    # 3 of 10 items this week vs 3 of 30 before: the share tripled (+200%).
    got = rising(rows([["smr"]] * 3 + [[]] * 7, [["smr"]] * 3 + [[]] * 27), NOW)
    assert got == [RisingTerm("smr", 3, 3, 200, False)]


def test_more_items_overall_is_not_a_rise():
    # Twice as many items this week, same share: not rising.
    assert rising(rows([["gpu"]] * 6 + [[]] * 14, [["gpu"]] * 3 + [[]] * 7), NOW) == []


def test_new_term_counts_one_baseline_item():
    got = rising(rows([["hbm4"]] * 4 + [[]] * 6, [[]] * 20), NOW)
    assert got == [RisingTerm("hbm4", 4, 0, 700, True)]  # 0.4 / (1/20) - 1


def test_min_recent_filters_noise():
    assert rising(rows([["rare"]] * 2 + [[]] * 8, [[]] * 20), NOW) == []


def test_windows_bounds():
    data = [
        (NOW, ["future"]),  # now itself is outside the recent window
        (days_ago(7), ["edge"]),  # exactly 7 days ago belongs to the recent window
        (days_ago(36), ["old"]),  # before the baseline window: ignored
        (days_ago(35), []),  # the first moment of the baseline window
    ] * 3
    assert [t.term for t in rising(data, NOW)] == ["edge"]


def test_case_insensitive_once_per_item_and_most_common_spelling():
    recent = [["NVIDIA", "nvidia"], ["Nvidia"], ["Nvidia"], ["Nvidia"]]
    got = rising(rows(recent + [[]] * 6, [[]] * 20), NOW)
    assert got == [RisingTerm("Nvidia", 4, 0, 700, True)]


def test_order_and_limit():
    recent = [["a", "b"]] * 3 + [["b"]] * 3 + [[]] * 4
    got = rising(rows(recent, [["a"]] * 1 + [[]] * 19), NOW)
    assert [t.term for t in got] == ["b", "a"]  # b: new and in more items
    assert len(rising(rows(recent, [[]] * 20), NOW, limit=1)) == 1


def test_empty_input_or_no_baseline_items():
    assert rising([], NOW) == []
    assert rising(rows([["x"]] * 5, []), NOW) == []  # nothing to compare with


def test_messages_escape_untrusted_terms():
    topics = {
        "tags": [RisingTerm("<b>ignore</b>", 3, 0, 500, True)],
        "companies": [RisingTerm("Acme", 3, 1, 50, False)],
        "technologies": [],
    }
    ev = [Evidence(1, "Title", "DCD", NOW, "https://x.example/a", "Summary.", [])]
    msg = trends.build_messages(ev, topics, days_ago(7), NOW)[0]["content"]
    assert isinstance(msg, str)
    assert "&lt;b&gt;ignore&lt;/b&gt; (new)" in msg
    assert "companies: Acme (+50%)" in msg
    assert "technologies" not in msg
    assert '<source n="1">' in msg and "Week: 2026-11-02 to 2026-11-09" in msg


def test_no_rising_block_when_nothing_rises():
    assert trends.render_rising({"tags": [], "companies": []}) == ""


def test_publisher_is_not_a_company_of_its_own_items():
    ents = {"companies": ["The New York Times", "OpenAI", "DatacenterDynamics"]}
    assert trends._companies(ents, "The New York Times") == ["OpenAI", "DatacenterDynamics"]
    assert trends._companies({"companies": ["ServeTheHome"]}, "www.servethehome.com") == []
    assert trends._companies(ents, "DatacenterDynamics") == ["The New York Times", "OpenAI"]
    assert trends._companies(ents, None) == ents["companies"]
    assert trends._companies(None, "x.com") == []
