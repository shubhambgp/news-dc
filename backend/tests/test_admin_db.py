"""Admin actions and export against real Postgres (TEST_DATABASE_URL, THROWAWAY database)."""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_DATABASE_URL
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app import db as app_db
from app import security
from app.api import common
from app.config import get_settings
from app.main import app
from app.models import AIAnnotation, Category, Item, ItemSource, Job, PipelineRun, Source
from app.pipeline.graph import current_prompt_hash, reprocess_outdated
from app.seed import seed

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

TOKEN, SECRET = "t" * 32, "s" * 48
T0 = datetime(2026, 10, 5, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def data(engine) -> dict[str, int]:
    """Three processed items (one found by two sources), one rejected by AI, one by prefilter."""
    with sessionmaker(engine).begin() as s:
        src = {x.key: x for x in s.scalars(select(Source))}
        ids = {}
        for n, (name, status, cat) in enumerate(
            [
                ("cool", "processed", "cooling"),
                ("power", "processed", "power-energy"),
                ("evil", "processed", "cooling"),
                ("recipe", "rejected_ai", None),
                ("short", "rejected_prefilter", None),
            ]
        ):
            title = "<script>alert(1)</script> [x](javascript:y)" if name == "evil" else name
            it = Item(
                primary_source_id=src["hn"].id,
                original_url=f"https://example.com/{name}",
                canonical_url=f"https://example.com/{name}",
                url_hash=(name * 64)[:64],
                title=title,
                content_text="FULL TEXT MUST NOT BE EXPORTED",
                publisher="Example",
                published_at=T0 - timedelta(days=n),
                status=status,
                status_reason="no data center keyword" if status == "rejected_prefilter" else None,
            )
            s.add(it)
            s.flush()
            for i, key in enumerate(("hn", "dcd") if name == "cool" else ("hn",)):
                s.add(
                    ItemSource(
                        item_id=it.id,
                        source_id=src[key].id,
                        external_id=f"{key}-{name}",
                        source_url=f"https://{key}.example/{name}",
                        is_primary=i == 0,
                    )
                )
            if status != "rejected_prefilter":
                s.add(
                    AIAnnotation(
                        item_id=it.id,
                        is_relevant=status == "processed",
                        relevance_score=80 if cat else 5,
                        quality_score=60,
                        primary_category=cat,
                        categories=[cat] if cat else [],
                        content_type="news",
                        summary=f"Summary of {name}.",
                        key_insights=[{"type": "business", "text": f"Insight {name}."}],
                        reject_reason="about baking" if status == "rejected_ai" else None,
                        prompt_version="classify-v2",
                        prompt_hash="0" * 64,
                    )
                )
            ids[name] = it.id
        s.add(PipelineRun(kind="pipeline", trigger="cli", status="partial", stop_reason="budget"))
    return ids


@pytest.fixture(autouse=True)
def api(engine, data, monkeypatch):
    S = sessionmaker(engine)

    def db():
        with S() as s:
            yield s

    app.dependency_overrides[common.get_db] = db
    monkeypatch.setattr(app_db, "engine", engine)
    monkeypatch.setattr(get_settings(), "admin_token", TOKEN)
    monkeypatch.setattr(get_settings(), "session_secret", SECRET)
    security.reset_rate_limits()
    with engine.begin() as c:
        c.execute(text("DELETE FROM jobs"))
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def admin() -> TestClient:
    c = TestClient(app, base_url="https://testserver")
    csrf = c.post("/api/v1/admin/login", json={"token": TOKEN}).json()["csrf_token"]
    c.headers["X-CSRF-Token"] = csrf
    return c


def jobs(engine) -> list[tuple[str, dict]]:
    with Session(engine) as s:
        return [(j.kind, j.payload) for j in s.scalars(select(Job).order_by(Job.id))]


# --- Export -------------------------------------------------------------------------------------


def test_export_json(data):
    r = TestClient(app).get("/api/v1/export?format=json")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    assert r.headers["content-disposition"] == 'attachment; filename="newsdc_export.json"'
    assert "FULL TEXT" not in r.text
    rows = json.loads(r.text)
    assert [x["id"] for x in rows] == [data["cool"], data["power"], data["evil"]]  # processed only
    cool = rows[0]
    assert [s["key"] for s in cool["sources"]] == ["hn", "dcd"]  # attribution, primary first
    assert cool["key_insights"] == [{"type": "business", "text": "Insight cool."}]
    assert cool["summary"] == "Summary of cool." and cool["url"] == "https://example.com/cool"
    assert "content_text" not in cool and "description" not in cool


def test_export_filters_and_limit(data):
    c = TestClient(app)
    rows = c.get("/api/v1/export?category=cooling").json()
    assert {x["id"] for x in rows} == {data["cool"], data["evil"]}
    assert len(c.get("/api/v1/export?limit=1").json()) == 1
    assert c.get("/api/v1/export?limit=1001").status_code == 422
    assert c.get("/api/v1/export?format=csv").status_code == 422
    assert c.get("/api/v1/export?category=Bad%20Slug").status_code == 422


def test_export_markdown_opens_and_is_inert(data):
    r = TestClient(app).get("/api/v1/export?format=md")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/markdown; charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="newsdc_export.md"'
    md = r.text
    assert md.startswith("# NewsDC export\n")
    assert md.index("## Cooling") < md.index("[cool]") and "## Power" in md
    assert "[cool](<https://example.com/cool>)" in md
    assert "FULL TEXT" not in md
    # The injected title stays text: no raw tag, no live link.
    assert not re.search(r"(?<!\\)<script", md)  # every < is backslash-escaped
    assert not re.search(r"(?<!\\)\]\(javascript", md)
    assert r"\<script\>alert(1)\</script\> \[x\](javascript:y)" in md
    assert md.count("\n### ") == 3


# --- Admin actions ------------------------------------------------------------------------------


def test_queue_actions(admin, engine):
    r = admin.post("/api/v1/admin/ingest", json={})
    assert r.status_code == 202 and r.json()["job_id"]
    r = admin.post("/api/v1/admin/pipeline")
    assert r.status_code == 202 and r.json()["job_id"]
    again = admin.post("/api/v1/admin/pipeline")
    assert again.status_code == 202 and again.json()["job_id"] is None  # one active per kind
    assert [k for k, _ in jobs(engine)] == ["ingest_all", "pipeline"]
    assert all(p["trigger"] == "admin" for _, p in jobs(engine))


def test_ingest_one_source(admin, engine):
    r = admin.post("/api/v1/admin/ingest", json={"source": "dcd"})
    assert r.status_code == 202
    assert jobs(engine) == [("ingest_all", {"trigger": "admin", "source": "dcd"})]
    assert admin.post("/api/v1/admin/ingest", json={"source": "nope"}).status_code == 404
    off = admin.post("/api/v1/admin/ingest", json={"source": "register_dc"})  # off in YAML
    assert off.status_code == 409


def test_trend_brief_needs_assistant(admin, engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "assistant_model", "")
    assert admin.post("/api/v1/admin/trend-brief").status_code == 409
    monkeypatch.setattr(get_settings(), "assistant_model", "some-model")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    assert admin.post("/api/v1/admin/trend-brief").status_code == 202
    assert jobs(engine)[0][0] == "trend_brief"


def test_runs_jobs_and_retry(admin, engine):
    runs = admin.get("/api/v1/admin/runs").json()
    assert runs[0]["stop_reason"] == "budget"
    with Session(engine) as s, s.begin():
        s.add(Job(kind="pipeline", status="dead_letter", attempt_count=3, last_error="boom"))
    listed = admin.get("/api/v1/admin/jobs").json()
    dead = listed[0]
    assert dead["status"] == "dead_letter" and dead["last_error"] == "boom"
    assert admin.post(f"/api/v1/admin/jobs/{dead['id']}/retry").status_code == 200
    assert admin.post(f"/api/v1/admin/jobs/{dead['id']}/retry").status_code == 409


def test_reprocess_one_item(admin, engine, data):
    r = admin.post(f"/api/v1/admin/items/{data['recipe']}/reprocess")
    assert r.status_code == 202 and r.json()["items"] == 1 and r.json()["job_id"]
    with Session(engine) as s:
        assert s.get(Item, data["recipe"]).status == "new"
        s.execute(text("UPDATE items SET status='rejected_ai' WHERE id=:i"), {"i": data["recipe"]})
        s.commit()
    assert admin.post("/api/v1/admin/items/999999/reprocess").status_code == 404


def test_rejected_items_with_reasons(admin, data):
    body = admin.get("/api/v1/admin/rejected").json()
    by_id = {x["id"]: x for x in body["items"]}
    assert body["total"] == 2
    assert by_id[data["recipe"]]["reason"] == "about baking"
    assert by_id[data["short"]]["reason"] == "no data center keyword"
    only = admin.get("/api/v1/admin/rejected?status=rejected_ai").json()
    assert [x["id"] for x in only["items"]] == [data["recipe"]]
    assert admin.get("/api/v1/admin/rejected?status=processed").status_code == 422


def test_pause_and_resume_source(admin, engine):
    r = admin.patch("/api/v1/admin/sources/dcd", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["enabled"] is True
    assert admin.post("/api/v1/admin/ingest", json={"source": "dcd"}).status_code == 409
    seed(engine, get_settings().config_dir)  # a restart doesn't undo the pause
    src = {s["key"]: s for s in admin.get("/api/v1/admin/sources").json()}
    assert src["dcd"]["admin_disabled"] is True
    assert admin.patch("/api/v1/admin/sources/dcd", json={"active": True}).json()["active"]
    off = admin.patch("/api/v1/admin/sources/register_dc", json={"active": True})
    assert off.status_code == 409 and off.json()["error"]["code"] == "disabled_in_config"
    assert admin.patch("/api/v1/admin/sources/nope", json={"active": True}).status_code == 404
    assert admin.patch("/api/v1/admin/sources/dcd", json={"enabled": True}).status_code == 422


def test_edit_category_survives_seed_and_outdates_annotations(admin, engine, data):
    with Session(engine) as s, s.begin():  # make every annotation current first
        s.execute(
            text("UPDATE ai_annotations SET prompt_hash=:h"), {"h": current_prompt_hash(engine)}
        )
    assert reprocess_outdated(engine) == 0
    r = admin.patch(
        "/api/v1/admin/categories/cooling",
        json={
            "description": "Liquid, immersion and air cooling.",
            "keywords": ["cdu", "immersion"],
        },
    )
    assert r.status_code == 200
    assert r.json()["description"] == "Liquid, immersion and air cooling."
    assert r.json()["admin_edited_at"]
    seed(engine, get_settings().config_dir)
    with Session(engine) as s:
        cat = s.get(Category, "cooling")
        assert cat.description == "Liquid, immersion and air cooling." and cat.keywords == [
            "cdu",
            "immersion",
        ]
    # The prompt changed, so every classified item is outdated now.
    r = admin.post("/api/v1/admin/reprocess-outdated")
    assert r.status_code == 202 and r.json()["items"] == 4 and r.json()["job_id"]
    with engine.begin() as c:  # restore for other tests
        c.execute(text("UPDATE items SET status='processed' WHERE status='new'"))
        c.execute(text("UPDATE items SET status='rejected_ai' WHERE id=:i"), {"i": data["recipe"]})


def test_category_validation_and_last_enabled(admin, engine):
    c = admin
    assert c.patch("/api/v1/admin/categories/nope", json={"name": "X"}).status_code == 404
    assert c.patch("/api/v1/admin/categories/cooling", json={"name": ""}).status_code == 422
    assert (
        c.patch("/api/v1/admin/categories/cooling", json={"keywords": ["k"] * 51}).status_code
        == 422
    )
    assert c.patch("/api/v1/admin/categories/cooling", json={"slug": "x"}).status_code == 422
    with engine.begin() as conn:
        conn.execute(text("UPDATE categories SET enabled = (slug = 'cooling')"))
    r = c.patch("/api/v1/admin/categories/cooling", json={"enabled": False})
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_category"
    with engine.begin() as conn:
        conn.execute(text("UPDATE categories SET enabled = true"))
