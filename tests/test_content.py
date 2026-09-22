from datetime import date

import pytest

from semantichub_wagtail.content import (
    article_title,
    excerpt,
    publish_date,
    render_body,
    tags,
    unique_slug,
)

MARKDOWN = """## Intro

Opening paragraph.

- first item
- second item

| Model | Cost |
| --- | --- |
| A | 1 |
"""


class TestRenderBody:
    def test_markdown_is_rendered_to_html(self):
        html = render_body(MARKDOWN)
        assert "<h2>Intro</h2>" in html
        assert "<li>first item</li>" in html
        assert "<table>" in html
        assert "## Intro" not in html

    def test_raw_html_tags_in_markdown_are_escaped(self):
        html = render_body("## Title\n\n<script>alert(1)</script>\n\nMore text.\n")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_body_passes_through_unchanged(self):
        body = "<h2>Intro</h2><p>Generated article.</p>"
        assert render_body(body) == body

    def test_html_with_leading_whitespace_passes_through(self):
        body = "\n  <p>Generated article.</p>"
        assert render_body(body) == body

    def test_empty_body_renders_to_empty_string(self):
        assert render_body("") == ""
        assert render_body(None) == ""

    def test_heading_markdown_is_not_mistaken_for_html(self):
        assert "<h1>" in render_body("# Title")


class TestArticleTitle:
    def test_payload_title_wins_over_cluster_name(self):
        payload = {"title": "Editor title"}
        cluster = {"name": "Cluster name"}
        assert article_title(payload, cluster) == "Editor title"

    def test_empty_title_falls_back_to_cluster_name(self):
        assert article_title({"title": None}, {"name": "Cluster name"}) == "Cluster name"
        assert article_title({}, {"name": "Cluster name"}) == "Cluster name"

    def test_title_is_trimmed_to_wagtail_limit(self):
        assert len(article_title({"title": "x" * 400}, {})) == 255


class TestExcerpt:
    def test_lead_wins_over_cluster_description(self):
        payload = {"lead": "Lead text."}
        cluster = {"description": "Topic description."}
        assert excerpt(payload, cluster) == "Lead text."

    def test_cluster_description_is_the_fallback(self):
        assert excerpt({}, {"description": "Topic description."}) == "Topic description."

    def test_legacy_meta_description_still_works(self):
        assert excerpt({}, {"meta_description": "Old key."}) == "Old key."

    def test_no_source_gives_empty_string(self):
        assert excerpt({}, {}) == ""


class TestTags:
    def test_tags_come_from_payload(self):
        assert tags({"tags": ["seo", " google ", "seo"]}, {}) == ["seo", "google"]

    def test_fallback_to_semantic_group_names(self):
        cluster = {"semantic_groups": {"passive income": ["a"], "niches": ["b"]}}
        assert tags({}, cluster) == ["passive income", "niches"]

    def test_non_list_tags_fall_back_to_cluster(self):
        cluster = {"semantic_groups": {"niches": []}}
        assert tags({"tags": "oops"}, cluster) == ["niches"]

    def test_limits_to_ten_tags(self):
        assert len(tags({"tags": [f"t{i}" for i in range(30)]}, {})) == 10


class TestPublishDate:
    def test_parses_executed_at(self):
        assert publish_date("2026-07-21T09:30:00+00:00") == date(2026, 7, 21)

    def test_invalid_value_falls_back_to_today(self):
        assert publish_date("not-a-date") == date.today()

    def test_missing_value_falls_back_to_today(self):
        assert publish_date(None) == date.today()


@pytest.mark.django_db
class TestUniqueSlug:
    def test_returns_base_when_free(self, article_index):
        assert unique_slug(article_index, "passive-income") == "passive-income"

    def test_appends_counter_on_collision(self, article_index):
        from tests.testapp.models import ArticlePage

        article_index.add_child(instance=ArticlePage(title="A", slug="passive-income"))
        article_index.add_child(instance=ArticlePage(title="B", slug="passive-income-2"))
        assert unique_slug(article_index, "passive-income") == "passive-income-3"

    def test_empty_base_gets_a_default(self, article_index):
        assert unique_slug(article_index, "") == "post"
