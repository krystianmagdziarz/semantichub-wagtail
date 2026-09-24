from django.conf import settings

DEFAULT_LANGUAGES = ("pl", "en")


def allowed_languages():
    """Language codes this site accepts, from SEMANTICHUB_INGEST_LANGUAGES."""
    raw = getattr(settings, "SEMANTICHUB_INGEST_LANGUAGES", None) or DEFAULT_LANGUAGES
    return tuple(str(code).strip() for code in raw if str(code).strip())
