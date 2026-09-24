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


def _load(setting_name, base_hint):
    dotted_path = getattr(settings, setting_name, "") or ""
    if not dotted_path:
        raise ImproperlyConfigured(f"{setting_name} must point to a {base_hint} subclass")
    return import_string(dotted_path)()


def get_adapter():
    return _load("SEMANTICHUB_INGEST_ADAPTER", "ArticleAdapter")
