from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class ArticleAdapter:
    def get_parent(self, article):
        raise NotImplementedError

    def build(self, article):
        raise NotImplementedError

    def update(self, page, article):
        raise NotImplementedError

    def apply_tags(self, page, tags):
        pass


def get_adapter():
    dotted_path = getattr(settings, "SEMANTICHUB_INGEST_ADAPTER", "") or ""
    if not dotted_path:
        raise ImproperlyConfigured(
            "SEMANTICHUB_INGEST_ADAPTER must point to an ArticleAdapter subclass"
        )
    return import_string(dotted_path)()
