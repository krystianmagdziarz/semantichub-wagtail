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
def api_client():
    return APIClient()
