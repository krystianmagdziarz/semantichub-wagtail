from datetime import date

import pytest
from django.core.exceptions import ImproperlyConfigured

from semantichub_wagtail.adapters import ArticleAdapter, get_adapter
from semantichub_wagtail.payload import (
    Article,
    InvalidPayload,
    article_for_locale,
    parse_article,
    parse_identity,
)
from tests.testapp.adapter import ExampleArticleAdapter


def make_payload(**overrides):
    payload = {
        "payload_version": 3,
        "mode": "article",
        "event": "workflow.action",
        "workflow_execution": "exec-abc-123",
        "workflow_name": "Blog - passive income",
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
        "ai_model": "provider/model",
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


class TestHostilePayloads:
    @pytest.mark.parametrize(
        "clusters",
        ["not-a-list", {"name": "x"}, ["not-a-dict"], [None]],
    )
    def test_malformed_clusters_are_invalid(self, clusters):
        with pytest.raises(InvalidPayload):
            parse_article(make_payload(clusters=clusters))

    @pytest.mark.parametrize("body", [123, ["## a"], {"text": "a"}])
    def test_non_string_body_is_invalid(self, body):
        with pytest.raises(InvalidPayload):
            parse_article(make_payload(llm_response=body))

    def test_non_string_title_falls_back_to_cluster_name(self):
        article = parse_article(make_payload(title=123))
        assert article.title == "How to build passive income"

    def test_non_string_lead_falls_back_to_cluster_description(self):
        article = parse_article(make_payload(lead={"x": 1}))
        assert article.lead == "A practical guide."

    @pytest.mark.parametrize("executed_at", ["2026-13-45T10:00:00+00:00", 1700000000, ["x"]])
    def test_unusable_executed_at_falls_back_to_today(self, executed_at):
        article = parse_article(make_payload(executed_at=executed_at))
        assert article.publish_date == date.today()

    def test_url_slug_is_sanitised(self):
        payload = make_payload()
        payload["clusters"][0]["url_slug"] = "Passive Income/../<b>2026</b>"
        assert parse_article(payload).slug_base == "passive-incomeb2026b"

    def test_long_url_slug_is_trimmed(self):
        payload = make_payload()
        payload["clusters"][0]["url_slug"] = "a" * 400
        assert len(parse_article(payload).slug_base) <= 200

    def test_non_string_cluster_name_does_not_break_slug(self):
        payload = make_payload()
        del payload["clusters"][0]["url_slug"]
        payload["clusters"][0]["name"] = 42
        assert parse_article(payload).slug_base == ""

    def test_non_string_tags_are_skipped(self):
        article = parse_article(make_payload(tags=["seo", {"x": 1}, None, 7, "google"]))
        assert article.tags == ["seo", "google"]


def make_v5_payload(**overrides):
    payload = make_payload()
    payload.update(
        {
            "payload_version": 5,
            "result_id": "6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b",
            "revision": 1,
            "published_at": "2026-09-24T10:00:00+00:00",
            "source_lang": "pl",
            "pair_source_lang": "pl",
            "steps": {"Stylista": {"text": "...", "model": "m", "tokens": 1, "cost": 0.0}},
            "locales": {
                "pl": {
                    "title": "Tytuł PL",
                    "slug": "tytul-pl",
                    "lead": "Zajawka PL",
                    "body": "## Wstęp\n\nAkapit.",
                    "seo_description": "SEO PL",
                    "body_html": "<h2>Wstęp</h2>\n<p>Akapit.</p>\n",
                },
                "en": {
                    "title": "Title EN",
                    "slug": "title-en",
                    "lead": "Lead EN",
                    "body": "## Intro\n\nParagraph.",
                    "seo_description": "SEO EN",
                    "body_html": "<h2>Intro</h2>\n<p>Paragraph.</p>\n",
                },
            },
        }
    )
    payload.update(overrides)
    return payload


def test_v3_payload_has_no_identity():
    assert parse_identity(make_payload()) is None
    article = parse_article(make_payload())
    assert article.language is None


def test_v5_identity_and_source_article():
    data = make_v5_payload()
    identity = parse_identity(data)
    assert str(identity.result_id) == "6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b"
    assert identity.revision == 1 and identity.source_lang == "pl"
    assert set(identity.locales) == {"pl", "en"}
    article = parse_article(data)
    assert article.language == "pl"
    assert article.title == "Tytuł PL" and article.lead == "Zajawka PL"
    assert article.body == "<h2>Wstęp</h2>\n<p>Akapit.</p>\n"
    assert article.slug_base == "tytul-pl"
    assert article.seo_description == "SEO PL"
    assert article.publish_date.isoformat() == "2026-09-24"


def test_v5_source_lang_falls_back_to_alias_then_single_locale():
    data = make_v5_payload()
    del data["source_lang"]
    assert parse_identity(data).source_lang == "pl"
    del data["pair_source_lang"]
    data["locales"] = {"en": data["locales"]["en"]}
    assert parse_identity(data).source_lang == "en"


def test_article_for_locale_renders_markdown_when_html_missing():
    data = make_v5_payload()
    locale = dict(data["locales"]["en"])
    locale.pop("body_html")
    article = article_for_locale(data, "en", locale)
    assert article.language == "en" and article.title == "Title EN"
    assert article.body.startswith("<h2>Intro</h2>")


@pytest.mark.parametrize(
    "broken",
    [
        {"locales": []},
        {"locales": {"pl": "tekst"}},
        {"locales": {"de": {"title": "x"}}, "source_lang": "de"},
        {"revision": 0},
        {"result_id": "nie-uuid"},
        {"payload_version": 4},
        {"locales": {"en": {"title": "x"}}, "source_lang": "pl"},
    ],
)
def test_v5_invalid_shapes(broken):
    with pytest.raises(InvalidPayload):
        parse_identity(make_v5_payload(**broken))
