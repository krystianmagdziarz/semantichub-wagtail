from django.conf import settings

DEFAULT_LANGUAGES = ("pl", "en")


def allowed_languages():
    raw = getattr(settings, "SEMANTICHUB_INGEST_LANGUAGES", None) or DEFAULT_LANGUAGES
    return tuple(str(code).strip() for code in raw if str(code).strip())


def _stripped(setting_name):
    return (getattr(settings, setting_name, "") or "").strip()


def api_base_url():
    return _stripped("SEMANTICHUB_API_BASE_URL")


def agent_token():
    return _stripped("SEMANTICHUB_AGENT_TOKEN")


def goal_id():
    return _stripped("SEMANTICHUB_GOAL_ID")
