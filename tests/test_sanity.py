import pytest


@pytest.mark.django_db
def test_wagtail_root_exists(article_index):
    assert article_index.pk is not None
