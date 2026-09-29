import logging

import httpx

from semantichub_wagtail import __version__
from semantichub_wagtail import settings as sh_settings
from semantichub_wagtail.adapters import get_adapter

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15.0

BLOCKS: tuple[dict, ...] = ()

SECTIONS: tuple[dict, ...] = ({"key": "seo", "name": "SEO meta"},)

FEATURES: tuple[str, ...] = ()


def build_manifest() -> dict:
    adapter = get_adapter()
    return {
        "blocks": [dict(block) for block in BLOCKS],
        "sections": [dict(section) for section in SECTIONS],
        "features": list(FEATURES),
        "fields": adapter.get_fields(),
        "source": "receiver",
        "version": __version__,
    }


def is_configured() -> bool:
    return bool(sh_settings.api_base_url() and sh_settings.agent_token() and sh_settings.goal_id())


def uses_https() -> bool:
    return sh_settings.api_base_url().lower().startswith("https://")


def manifest_url() -> str:
    base = sh_settings.api_base_url().rstrip("/")
    return f"{base}/api/goals/{sh_settings.goal_id()}/target-manifest"


def push_manifest(client=None) -> bool:
    if not is_configured():
        logger.debug("semantichub_manifest_push_skipped reason=not_configured")
        return False
    if not uses_https():
        logger.warning("semantichub_manifest_push_skipped reason=insecure_base_url")
        return False

    headers = {
        "Authorization": f"Bearer {sh_settings.agent_token()}",
        "User-Agent": f"SemanticHub-wagtail/{__version__}",
        "Content-Type": "application/json",
    }
    url = manifest_url()
    body = build_manifest()
    try:
        if client is not None:
            response = client.put(url, headers=headers, json=body)
        else:
            response = httpx.put(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
    except Exception:
        logger.warning("semantichub_manifest_push_failed reason=transport", exc_info=True)
        return False

    status_code = getattr(response, "status_code", 0)
    if status_code >= 400:
        logger.warning("semantichub_manifest_push_rejected status=%s", status_code)
        return False

    logger.info("semantichub_manifest_push_ok status=%s", status_code)
    return True
