"""Tests for the Help Center safety-scope article seed (Phase 8) and a real bug it
surfaced along the way: HelpArticleRead couldn't parse the comma-joined `tags` column at
all - any help article with tags set would 500 on every GET, seeded or admin-created.

The seed itself directly addresses the "verified safety/self-check beyond regex, or an
explicit, communicated scope limit" ask (docs/PRODUCT_BENCHMARK.md): building a
clinically-validated classifier isn't something to fake in a single pass, so this makes
the existing pattern-based system's real scope and limits an actual, user-reachable page
instead of something only visible in code comments.
"""

from app.core.database import SessionLocal
from app.models import HelpCenterArticle
from app.schemas import HelpArticleRead
from app.services.users import SAFETY_SCOPE_ARTICLE_TITLE, seed_safety_scope_help_article


def test_seed_creates_the_safety_scope_article_once():
    with SessionLocal() as db:
        seed_safety_scope_help_article(db)
        count_after_first = db.query(HelpCenterArticle).filter(HelpCenterArticle.title == SAFETY_SCOPE_ARTICLE_TITLE).count()

        seed_safety_scope_help_article(db)
        count_after_second = db.query(HelpCenterArticle).filter(HelpCenterArticle.title == SAFETY_SCOPE_ARTICLE_TITLE).count()

    assert count_after_first == 1
    assert count_after_second == 1, "must be idempotent - calling it again must not duplicate the article"


def test_safety_scope_article_is_honest_about_not_being_a_diagnostic_system():
    with SessionLocal() as db:
        seed_safety_scope_help_article(db)
        article = db.query(HelpCenterArticle).filter(HelpCenterArticle.title == SAFETY_SCOPE_ARTICLE_TITLE).first()

    assert "not a clinical diagnostic system" in article.content
    assert "pattern-based" in article.content
    assert article.is_published is True


def test_help_article_read_schema_parses_comma_joined_tags():
    """Regression test: HelpArticleRead.tags is declared list[str], but
    HelpCenterArticle.tags is stored as a single comma-joined string
    (app/routers/settings.py joins on create/update) - reading a real row back with
    model_validate(article, from_attributes=True) handed Pydantic the raw string, which a
    bare list[str] field rejects outright, a hard 500 on every GET for any tagged article."""
    import datetime

    article = HelpCenterArticle(
        id="x", title="t", content="c", category="safety",
        tags="safety,limitations,emergency", is_published=True, order_index=0,
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    result = HelpArticleRead.model_validate(article)
    assert result.tags == ["safety", "limitations", "emergency"]


def test_help_article_read_schema_handles_no_tags():
    import datetime

    article = HelpCenterArticle(
        id="x", title="t", content="c", category="safety",
        tags=None, is_published=True, order_index=0,
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    result = HelpArticleRead.model_validate(article)
    assert result.tags == []


def test_get_help_articles_returns_the_seeded_safety_article(client):
    with SessionLocal() as db:
        seed_safety_scope_help_article(db)

    response = client.get("/api/help/articles")
    assert response.status_code == 200
    articles = response.json()
    titles = [a["title"] for a in articles]
    assert SAFETY_SCOPE_ARTICLE_TITLE in titles

    safety_article = next(a for a in articles if a["title"] == SAFETY_SCOPE_ARTICLE_TITLE)
    assert safety_article["tags"] == ["safety", "limitations", "emergency"]
