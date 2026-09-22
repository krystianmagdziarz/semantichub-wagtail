from datetime import date

import pytest
from django.core.exceptions import ImproperlyConfigured

from semantichub_wagtail.adapters import ArticleAdapter, get_adapter
from semantichub_wagtail.payload import Article, InvalidPayload, parse_article
from tests.testapp.adapter import ExampleArticleAdapter


def make_payload(**overrides):
    payload = {
        "payload_version": 3,
        "mode": "article",
        "event": "workflow.action",
        "workflow_execution": "exec-abc-123",
        "workflow_name": "kmagdziarz - passive income",
        "title": "Editor title",
        "lead": "Editor lead.",
        "executed_at": "2026-07-21T09:30:00+00:00",
        "articles_count": 1,
        "articles": [{"url": "https://example.com/a", "title": "Source A"}],
        "clusters": [
            {
                "name": "How to build passive income",
                "description": "A practical guide.",
                "url_slug": "passive-income",
                "semantic_groups": {"passive income": [], "niches": []},
            }
        ],
        "llm_response": "## Intro\n\nBody text.\n",
        "ai_model": "openai/gpt-5.4",
        "tokens_used": 1234,
        "cost": 0.01,
    }
    payload.update(overrides)
    return payload


class TestParseArticle:
    def test_maps_payload_to_article(self):
        article = parse_article(make_payload())
        assert isinstance(article, Article)
        assert article.title == "Editor title"
        assert article.lead == "Editor lead."
        assert article.slug_base == "passive-income"
        assert "<h2>Intro</h2>" in article.body
        assert article.tags == ["passive income", "niches"]
        assert article.publish_date == date(2026, 7, 21)
        assert article.publish_mode is None
        assert article.cluster["name"] == "How to build passive income"
        assert article.cover is None

    def test_publish_mode_is_carried_over(self):
        article = parse_article(make_payload(publish_mode="draft"))
        assert article.publish_mode == "draft"

    def test_slug_falls_back_to_cluster_name(self):
        payload = make_payload()
        del payload["clusters"][0]["url_slug"]
        assert parse_article(payload).slug_base == "how-to-build-passive-income"

    def test_missing_clusters_is_invalid(self):
        with pytest.raises(InvalidPayload):
            parse_article(make_payload(clusters=[]))

    def test_non_article_mode_is_invalid(self):
        with pytest.raises(InvalidPayload):
            parse_article(make_payload(mode="cluster", llm_response=None))

    def test_empty_body_is_invalid(self):
        with pytest.raises(InvalidPayload):
            parse_article(make_payload(llm_response="   "))

    def test_non_dict_payload_is_invalid(self):
        with pytest.raises(InvalidPayload):
            parse_article(["not", "a", "dict"])


class TestGetAdapter:
    def test_returns_configured_adapter(self):
        adapter = get_adapter()
        assert isinstance(adapter, ExampleArticleAdapter)
        assert isinstance(adapter, ArticleAdapter)

    def test_missing_setting_raises(self, settings):
        settings.SEMANTICHUB_INGEST_ADAPTER = ""
        with pytest.raises(ImproperlyConfigured):
            get_adapter()


@pytest.mark.django_db
class TestExampleAdapter:
    def test_build_maps_article_to_page(self, article_index):
        adapter = get_adapter()
        article = parse_article(make_payload())
        page = adapter.build(article)
        assert page.title == "Editor title"
        assert page.excerpt == "Editor lead."
        assert "<h2>Intro</h2>" in page.body
        assert page.publish_date == date(2026, 7, 21)

    def test_update_rewrites_fields(self, article_index):
        from tests.testapp.models import ArticlePage

        page = article_index.add_child(
            instance=ArticlePage(title="Old", slug="old", body="<p>old</p>")
        )
        adapter = get_adapter()
        adapter.update(page, parse_article(make_payload()))
        assert page.title == "Editor title"
        assert "<h2>Intro</h2>" in page.body

    def test_get_parent_returns_index(self, article_index):
        adapter = get_adapter()
        assert adapter.get_parent(parse_article(make_payload())).pk == article_index.pk
