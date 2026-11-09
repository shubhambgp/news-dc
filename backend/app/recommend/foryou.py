"""For You feed (PLAN Phase 5.5): personalised from the anonymous browser profile, with about one
item in five from a category the user hasn't engaged with ("Discover"). An empty profile falls
back to Trending + Most relevant (cold start)."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, cast, func, literal, select
from sqlalchemy.orm import Session

from app.api.common import ORDER, base
from app.models import EMBEDDING_DIM, AIAnnotation, Item
from app.recommend.scoring import (
    age_hours_sql,
    coverage_sql,
    personal,
    relevant,
    trending,
)
from app.schemas import FeedKind, Profile

# ponytail: ranks the newest 1,000 public items in Python per request; move scoring into SQL if
# the pool has to grow much beyond that.
POOL_SIZE = 1000
CENTROID_RECENT = 50  # newest reads and bookmarks that make up the "taste" embedding
EXPLICIT_TOPIC_WEIGHT = 5.0  # a topic picked at onboarding counts like a few bookmarks
DISCOVER_EVERY = 5  # every 5th slot is a discovery item (~20%)
DISCOVER_MIN_QUALITY = 60


@dataclass(frozen=True)
class Candidate:
    id: int
    primary_category: str | None
    categories: list[str]
    tags: list[str]
    relevance: int = 0
    quality: int = 0
    points: int = 0
    comments: int = 0
    coverage: int = 0
    age_hours: float = 0.0
    similarity: float = 0.0  # cosine similarity to the profile's taste embedding, 0 if none


@dataclass(frozen=True)
class Pick:
    id: int
    kind: FeedKind
    reason: str
    score: float


@dataclass(frozen=True)
class Taste:
    categories: dict[str, float]  # normalised to [-1, 1]
    tags: dict[str, float]  # lower-cased, normalised to [-1, 1]
    read_counts: dict[str, int] = field(default_factory=dict)  # primary category -> items read
    explicit: frozenset[str] = frozenset()

    @property
    def engaged(self) -> set[str]:
        """Categories with any signal, liked or disliked: never offered as discovery."""
        return set(self.categories) | set(self.read_counts) | set(self.explicit)


def normalized(weights: Mapping[str, float]) -> dict[str, float]:
    """Divide by the largest absolute weight, so affinities land in [-1, 1]; zeros are dropped."""
    top = max((abs(w) for w in weights.values()), default=0.0)
    return {k: w / top for k, w in weights.items() if w} if top else {}


def build_taste(profile: Profile, read_counts: Mapping[str, int]) -> Taste:
    cats = dict(profile.category_weights)
    for slug in profile.explicit_topics:
        cats[slug] = cats.get(slug, 0.0) + EXPLICIT_TOPIC_WEIGHT
    tags: dict[str, float] = {}
    for tag, w in profile.tag_weights.items():
        tags[tag.lower()] = tags.get(tag.lower(), 0.0) + w
    return Taste(
        normalized(cats), normalized(tags), dict(read_counts), frozenset(profile.explicit_topics)
    )


def _best(keys: Iterable[str], weights: Mapping[str, float]) -> tuple[str | None, float]:
    hits = [(weights[k], k) for k in keys if k in weights]
    if not hits:
        return None, 0.0
    w, k = max(hits)
    return k, w


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _personal_pick(c: Candidate, taste: Taste, names: Mapping[str, str]) -> Pick:
    cat, cat_w = _best(c.categories, taste.categories)
    tag, tag_w = _best((t.lower() for t in c.tags), taste.tags)
    sim = max(c.similarity, 0.0)
    score = personal(cat_w, sim, tag_w, c.quality, c.age_hours)
    # The reason names the largest positive part of the score.
    parts = {"category": 0.35 * cat_w, "similar": 0.25 * sim, "tag": 0.15 * tag_w}
    top = max(parts, key=lambda k: parts[k])
    if parts[top] <= 0:
        reason = "High quality and recent"
    elif top == "category" and cat:
        name = names.get(cat, cat)
        if n := taste.read_counts.get(cat, 0):
            reason = f"Because you read {_plural(n, name + ' article')}"
        elif cat in taste.explicit:
            reason = f"Because you picked {name}"
        else:
            reason = f"Because you showed interest in {name}"
    elif top == "tag":
        reason = f"Because you're interested in “{tag}”"
    else:
        reason = "Similar to articles you read or saved"
    return Pick(c.id, "personal", reason, score)


def rank_personal(
    candidates: Iterable[Candidate], taste: Taste, names: Mapping[str, str]
) -> list[Pick]:
    """Profile-scored items, with every DISCOVER_EVERY-th slot taken by a high-quality item from a
    category the user hasn't engaged with. Discovery rotates through categories."""
    main: list[Pick] = []
    discover: list[Candidate] = []
    engaged = taste.engaged
    for c in candidates:
        if not engaged & set(c.categories) and c.quality >= DISCOVER_MIN_QUALITY:
            discover.append(c)
        else:
            main.append(_personal_pick(c, taste, names))
    main.sort(key=lambda p: (-p.score, -p.id))

    discover.sort(key=lambda c: (-c.quality, c.age_hours, -c.id))
    seen: Counter[str | None] = Counter()
    rounds = []
    for c in discover:  # round-robin: the best item of each category first, then the second...
        rounds.append((seen[c.primary_category], c))
        seen[c.primary_category] += 1
    rounds.sort(key=lambda t: t[0])  # stable, keeps quality order inside a round
    disc = [
        Pick(
            c.id,
            "discover",
            f"Discover: {names.get(c.primary_category or '', c.primary_category or 'new topic')}",
            c.quality / 100,
        )
        for _, c in rounds
    ]
    return interleave(main, disc)


def interleave(main: list[Pick], discover: list[Pick]) -> list[Pick]:
    """Every DISCOVER_EVERY-th slot from `discover`; when one list runs out the other fills in."""
    out: list[Pick] = []
    m, d = iter(main), iter(discover)
    while True:
        first, second = (d, m) if (len(out) + 1) % DISCOVER_EVERY == 0 else (m, d)
        nxt = next(first, None) or next(second, None)
        if nxt is None:
            return out
        out.append(nxt)


def rank_cold_start(candidates: list[Candidate]) -> list[Pick]:
    """Empty profile: Trending and Most relevant, alternating, without repeats."""

    def trend(c: Candidate) -> float:
        return float(trending(c.points, c.comments, c.quality, c.coverage, c.age_hours))

    def rel(c: Candidate) -> float:
        return float(relevant(c.relevance, c.quality, c.age_hours))

    by_trend = sorted(candidates, key=lambda c: (-trend(c), -c.id))
    by_rel = sorted(candidates, key=lambda c: (-rel(c), -c.id))
    out: list[Pick] = []
    seen: set[int] = set()
    for t, r in zip(by_trend, by_rel, strict=True):
        for pick in (
            Pick(t.id, "trending", "Trending now", trend(t)),
            Pick(r.id, "relevant", "Highly relevant", rel(r)),
        ):
            if pick.id not in seen:
                seen.add(pick.id)
                out.append(pick)
    return out


# --- database ----------------------------------------------------------------------------------


def _centroid(db: Session, profile: Profile) -> Any:
    recent = profile.read_ids[-CENTROID_RECENT:] + profile.bookmark_ids[-CENTROID_RECENT:]
    if not recent:
        return None
    return db.scalar(
        select(func.avg(Item.embedding, type_=Vector(EMBEDDING_DIM))).where(
            Item.id.in_(recent), Item.embedding.is_not(None)
        )
    )


def _read_counts(db: Session, profile: Profile) -> dict[str, int]:
    ids = set(profile.read_ids) | set(profile.bookmark_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(AIAnnotation.primary_category, func.count())
        .where(AIAnnotation.item_id.in_(ids), AIAnnotation.primary_category.is_not(None))
        .group_by(AIAnnotation.primary_category)
    ).all()
    return {cat: n for cat, n in rows if cat}


def load_candidates(db: Session, profile: Profile) -> list[Candidate]:
    """The newest POOL_SIZE public items the user hasn't read, saved or dismissed."""
    centroid = _centroid(db, profile)
    sim = (
        func.coalesce(1 - Item.embedding.cosine_distance(centroid), 0.0)
        if centroid is not None
        else literal(0.0)
    )
    stmt = base(
        Item.id,
        AIAnnotation.primary_category,
        AIAnnotation.categories,
        AIAnnotation.tags,
        func.coalesce(AIAnnotation.relevance_score, 0),
        func.coalesce(AIAnnotation.quality_score, 0),
        func.coalesce(Item.points, 0),
        func.coalesce(Item.comments_count, 0),
        coverage_sql(),
        age_hours_sql(),
        cast(sim, Float),
    )
    if exclude := {*profile.read_ids, *profile.bookmark_ids, *profile.dismissed_ids}:
        stmt = stmt.where(Item.id.not_in(exclude))
    rows = db.execute(stmt.order_by(*ORDER["latest"]).limit(POOL_SIZE)).all()
    return [Candidate(*r) for r in rows]


def rank(db: Session, profile: Profile, names: Mapping[str, str]) -> tuple[list[Pick], bool]:
    """The whole ranked feed (at most POOL_SIZE picks) and whether it is a cold start."""
    candidates = load_candidates(db, profile)
    if profile.is_empty():
        return rank_cold_start(candidates), True
    return rank_personal(candidates, build_taste(profile, _read_counts(db, profile)), names), False
