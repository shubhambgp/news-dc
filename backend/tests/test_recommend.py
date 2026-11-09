"""Phase 5 scoring and For You ranking: pure functions, deterministic inputs -> expected order."""

import pytest

from app.recommend import scoring
from app.recommend.foryou import (
    DISCOVER_EVERY,
    Candidate,
    Pick,
    build_taste,
    interleave,
    normalized,
    rank_cold_start,
    rank_personal,
)
from app.schemas import Profile

NAMES = {"cooling": "Cooling", "power-energy": "Power & Energy", "networking": "Networking"}
NAMES |= {"security": "Security", "regulation": "Regulation", "sustainability": "Sustainability"}


def order(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda k: -scores[k])


# --- trending ----------------------------------------------------------------------------------


def test_trending_formula_value():
    # (1 + 10 + 2·5 + 80/10 + 5·1) / (0 + 2)^1.5
    assert scoring.trending(10, 5, 80, 1, 0) == pytest.approx(34 / 2**1.5)


def test_trending_orders_by_engagement_age_and_coverage():
    s = {
        "hot_hn": scoring.trending(300, 120, 60, 0, 3),
        "fresh_rss": scoring.trending(0, 0, 70, 0, 1),
        "covered": scoring.trending(0, 0, 70, 4, 1),  # 4 other outlets: same story, trending
        "old_hn": scoring.trending(300, 120, 60, 0, 240),
        "old_rss": scoring.trending(0, 0, 90, 0, 240),
    }
    assert order(s) == ["hot_hn", "covered", "fresh_rss", "old_hn", "old_rss"]


def test_trending_gravity_overtakes_points():
    """A day-old story needs far more points than a fresh one to stay ahead."""
    assert scoring.trending(10, 0, 50, 0, 1) > scoring.trending(100, 0, 50, 0, 48)


# --- most relevant -----------------------------------------------------------------------------


def test_relevant_formula_and_mild_decay():
    assert scoring.relevant(100, 50, 0) == pytest.approx(80)
    assert scoring.relevant(100, 50, 30 * 24) == pytest.approx(40)  # a month: half
    # Mild: a strong 3-day-old item still beats a weak fresh one.
    assert scoring.relevant(95, 85, 72) > scoring.relevant(60, 50, 0)
    # Relevance weighs more than quality.
    assert scoring.relevant(90, 50, 0) > scoring.relevant(50, 90, 0)


# --- related -----------------------------------------------------------------------------------


def test_related_boosts_shared_categories():
    assert scoring.related(0.80, 0) == pytest.approx(0.80)
    assert scoring.related(0.75, 1) > scoring.related(0.80, 0)
    assert scoring.related(0.60, 2) == pytest.approx(0.80)


# --- For You scoring ---------------------------------------------------------------------------


def test_freshness_halves_weekly():
    assert scoring.freshness(0) == 1.0
    assert scoring.freshness(7 * 24) == pytest.approx(0.5)
    assert scoring.freshness(-5) == 1.0  # a future date is not fresher than now


def test_personal_weights():
    assert scoring.personal(1, 1, 1, 100, 0) == pytest.approx(1.0)
    assert scoring.personal(0, 0, 0, 0, 10**6) == pytest.approx(0.0)
    assert scoring.personal(1, 0, 0, 0, 10**6) == pytest.approx(0.35)
    # Category affinity outweighs embedding similarity, which outweighs tags.
    cat = scoring.personal(1, 0, 0, 50, 24)
    sim = scoring.personal(0, 1, 0, 50, 24)
    tag = scoring.personal(0, 0, 1, 50, 24)
    assert cat > sim > tag


def test_normalized_weights():
    assert normalized({"a": 10, "b": -5, "c": 0}) == {"a": 1.0, "b": -0.5}
    assert normalized({}) == {}
    assert normalized({"a": 0}) == {}


def test_taste_adds_explicit_topics_and_lowercases_tags():
    p = Profile(
        category_weights={"cooling": 5},
        explicit_topics=["power-energy"],
        tag_weights={"PUE": 2, "pue": 2},
    )
    t = build_taste(p, {"networking": 1})
    assert t.categories == {"cooling": 1.0, "power-energy": 1.0}
    assert t.tags == {"pue": 1.0}
    assert t.engaged == {"cooling", "power-energy", "networking"}


def test_profile_aliases_and_emptiness():
    p = Profile.model_validate({"categoryWeights": {"cooling": 1}, "readIds": [3]})
    assert p.category_weights == {"cooling": 1} and p.read_ids == [3]
    assert Profile().is_empty()
    assert Profile(dismissed_ids=[1, 2]).is_empty()  # dismissals alone say nothing positive
    assert Profile(category_weights={"cooling": 0}).is_empty()
    assert not Profile(explicit_topics=["cooling"]).is_empty()


def cand(id: int, cat: str, *, quality: int = 70, age: float = 24, **kw) -> Candidate:
    return Candidate(id=id, primary_category=cat, categories=[cat], tags=[], quality=quality,
                     age_hours=age, **kw)  # fmt: skip


def test_interleave_puts_discovery_every_fifth_slot_and_fills_gaps():
    main = [Pick(i, "personal", "", 1) for i in range(1, 9)]
    disc = [Pick(i, "discover", "", 1) for i in (101, 102, 103)]
    kinds = [p.kind for p in interleave(main, disc)]
    assert kinds[DISCOVER_EVERY - 1] == "discover" and kinds[2 * DISCOVER_EVERY - 1] == "discover"
    assert kinds.count("discover") == 3 and len(kinds) == 11
    assert kinds[:4] == ["personal"] * 4
    assert [p.id for p in interleave([], disc)] == [101, 102, 103]
    assert [p.id for p in interleave(main[:2], [])] == [1, 2]


def cooling_heavy_pool() -> list[Candidate]:
    """12 cooling, 6 power, 4 networking, 4 security (2 below discovery quality), 2 regulation."""
    pool = [cand(i, "cooling", quality=50 + i) for i in range(1, 13)]
    pool += [cand(100 + i, "power-energy", quality=80) for i in range(6)]
    pool += [cand(200 + i, "networking", quality=90 - i) for i in range(4)]
    pool += [cand(300 + i, "security", quality=40 if i < 2 else 75) for i in range(4)]
    pool += [cand(400 + i, "regulation", quality=85) for i in range(2)]
    return pool


def test_cooling_heavy_profile_gets_mostly_cooling_plus_discovery():
    """PLAN Phase 5 acceptance (pure ranking; the DB/API version is in test_recommend_db.py)."""
    profile = Profile(category_weights={"cooling": 12, "power-energy": 1})
    taste = build_taste(profile, {"cooling": 4})
    feed = rank_personal(cooling_heavy_pool(), taste, NAMES)
    top = feed[:10]
    cats = [next(c.primary_category for c in cooling_heavy_pool() if c.id == p.id) for p in top]
    assert cats.count("cooling") == 8
    assert [p.kind for p in top].count("discover") == 2
    assert top[4].kind == top[9].kind == "discover"
    # Discovery: categories without any signal, best quality first, one per category per round.
    disc = [p for p in feed if p.kind == "discover"]
    assert [p.reason for p in disc[:3]] == [
        "Discover: Networking",
        "Discover: Regulation",
        "Discover: Security",
    ]
    assert {p.id for p in disc} == {200, 201, 202, 203, 400, 401, 302, 303}  # 300/301: quality 40
    assert all(
        p.kind == "personal" for p in feed if p.id in range(100, 106)
    )  # engaged: no discover
    # Reasons explain the strongest signal.
    assert top[0].reason == "Because you read 4 Cooling articles"
    # Every candidate appears exactly once.
    assert sorted(p.id for p in feed) == sorted(c.id for c in cooling_heavy_pool())


def test_negative_weight_sinks_a_category_and_keeps_it_out_of_discovery():
    pool = [cand(1, "cooling"), cand(2, "security", quality=95), cand(3, "networking", quality=50)]
    taste = build_taste(Profile(category_weights={"cooling": 3, "security": -3}), {})
    feed = rank_personal(pool, taste, NAMES)
    assert [p.id for p in feed] == [1, 3, 2]
    assert feed[1].kind == "personal" and feed[2].kind == "personal"  # only 3 items: no 5th slot
    assert feed[1].reason == "High quality and recent"


def test_reasons_for_explicit_topic_tag_and_similarity():
    taste = build_taste(
        Profile(explicit_topics=["cooling"], tag_weights={"immersion": 5}), {}
    )  # fmt: skip
    pool = [
        cand(1, "cooling"),
        Candidate(2, "networking", ["networking"], ["Immersion"], quality=50),
        Candidate(3, "sustainability", ["sustainability"], [], quality=10, similarity=0.9),
    ]
    reasons = {p.id: p.reason for p in rank_personal(pool, taste, NAMES)}
    assert reasons == {
        1: "Because you picked Cooling",
        2: "Because you're interested in “immersion”",
        3: "Similar to articles you read or saved",
    }


def test_cold_start_alternates_trending_and_relevant_without_repeats():
    pool = [
        Candidate(1, "cooling", ["cooling"], [], relevance=95, quality=90, age_hours=200),
        Candidate(2, "cooling", ["cooling"], [], relevance=40, quality=40, points=500, age_hours=2),
        Candidate(3, "cooling", ["cooling"], [], relevance=80, quality=70, age_hours=1),
    ]
    feed = rank_cold_start(pool)
    assert [(p.id, p.kind) for p in feed] == [(2, "trending"), (3, "relevant"), (1, "relevant")]
    assert feed[0].reason == "Trending now"
