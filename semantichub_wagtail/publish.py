from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

PUBLISH_MODES = ("moderation", "draft", "publish")


def resolve_mode(article):
    requested = str(article.publish_mode or "").strip()
    if requested:
        return requested if requested in PUBLISH_MODES else "moderation"
    mode = getattr(settings, "SEMANTICHUB_INGEST_PUBLISH_MODE", "moderation")
    return mode if mode in PUBLISH_MODES else "moderation"


def ingest_user():
    User = get_user_model()
    user, _created = User.objects.get_or_create(
        username="semantichub",
        defaults={"is_active": False, "password": make_password(None)},
    )
    return user


def apply_policy(page, revision, mode, user):
    if mode == "publish" and page.permissions_for_user(user).can_publish():
        revision.publish(user=user)
        page.refresh_from_db()
        return "published"
    if mode == "draft":
        return "draft"
    if page.current_workflow_state is not None:
        return "moderation"
    workflow = page.get_workflow()
    if workflow is not None:
        workflow.start(page, user)
        return "moderation"
    return "draft"
