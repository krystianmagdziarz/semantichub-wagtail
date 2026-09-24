import pytest
from rest_framework.test import APIClient
from wagtail.models import Page

from tests.testapp.models import ArticleIndexPage


@pytest.fixture
def article_index(db):
    index = ArticleIndexPage.objects.first()
    if index is not None:
        return index
    root = Page.get_first_root_node()
    return root.add_child(instance=ArticleIndexPage(title="Articles", slug="articles"))


@pytest.fixture
def article_index_en(article_index):
    parent = article_index.get_parent()
    return parent.add_child(instance=ArticleIndexPage(title="Articles EN", slug="articles-en"))


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
