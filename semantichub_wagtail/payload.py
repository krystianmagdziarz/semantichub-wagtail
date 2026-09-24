from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import nh3
from django.utils.text import slugify

from semantichub_wagtail import content
from semantichub_wagtail.settings import allowed_languages

MAX_SLUG_BASE_LENGTH = 200
MAX_REVISION = 2**31 - 1

SUPPORTED_VERSIONS = (None, 3, 5)


class InvalidPayload(Exception):
    pass


@dataclass
class Article:
    title: str
    slug_base: str
    lead: str
    body: str
    tags: list[str]
    publish_date: date
    publish_mode: str | None
    cluster: dict
    data: dict
    language: str | None = None
    seo_description: str = ""
    cover: object | None = field(default=None)


@dataclass
class Identity:
    result_id: UUID
    revision: int
    source_lang: str
    locales: dict


def _slug_base(cluster):
    source = content.text(cluster.get("url_slug")) or content.text(cluster.get("name"))
    return slugify(source)[:MAX_SLUG_BASE_LENGTH].strip("-")


def _version(data):
    raw = data.get("payload_version")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as error:
        raise InvalidPayload("payload_version must be an integer") from error


def _source_lang(data, locales):
    source = content.text(data.get("source_lang")) or content.text(data.get("pair_source_lang"))
    if not source and isinstance(locales, dict) and len(locales) == 1:
        source = next(iter(locales))
    return source


def parse_identity(data):
    """Delivery identity of a v5 payload; None for a payload without result_id."""
    if not isinstance(data, dict):
        raise InvalidPayload("payload must be a JSON object")
    if _version(data) not in SUPPORTED_VERSIONS:
        raise InvalidPayload("unsupported payload_version")
    if "result_id" not in data:
        return None
    raw_revision = data.get("revision", 1)
    try:
        result_id = UUID(str(data["result_id"]))
        revision = int(raw_revision)
    except (TypeError, ValueError) as error:
        raise InvalidPayload("result_id must be a UUID and revision an integer") from error
    if isinstance(raw_revision, bool) or (
        isinstance(raw_revision, float) and raw_revision != revision
    ):
        raise InvalidPayload("revision must be an integer")
    if revision < 1:
        raise InvalidPayload("revision must be >= 1")
    if revision > MAX_REVISION:
        raise InvalidPayload(f"revision must be <= {MAX_REVISION}")
    locales = data.get("locales")
    if locales is None:
        locales = {}
    if not isinstance(locales, dict):
        raise InvalidPayload("locales must be an object")
    allowed = allowed_languages()
    for code, locale in locales.items():
        if code not in allowed:
            raise InvalidPayload(f"language {code!r} is not accepted here")
        if not isinstance(locale, dict):
            raise InvalidPayload(f"locales.{code} must be an object")
    source = _source_lang(data, locales)
    if locales and source not in locales:
        raise InvalidPayload("source language is missing from locales")
    if source and source not in allowed:
        raise InvalidPayload(f"language {source!r} is not accepted here")
    return Identity(result_id=result_id, revision=revision, source_lang=source, locales=locales)


def _publish_date(data):
    return content.publish_date(data.get("published_at") or data.get("executed_at"))


def _locale_body(locale):
    if content.text(locale.get("body_html")):
        return nh3.clean(locale["body_html"])
    body = locale.get("body")
    return content.render_body(body if isinstance(body, str) else "")


def _locale_slug_base(locale, title):
    source = content.text(locale.get("slug")) or title
    return slugify(source)[:MAX_SLUG_BASE_LENGTH].strip("-")


def _first_cluster(data):
    clusters = data.get("clusters")
    if isinstance(clusters, list) and clusters and isinstance(clusters[0], dict):
        return clusters[0]
    return {}


def article_for_locale(data, language_code, locale):
    """Article for one language of a v5 delivery.

    The sender may leave title and lead empty. The source language then falls
    back like v3 (cluster name, cluster description); another language takes
    the source title, so no page is created without a title."""
    cluster = _first_cluster(data)
    locales = data.get("locales") if isinstance(data.get("locales"), dict) else {}
    source = _source_lang(data, locales)
    title = content.text(locale.get("title"))
    lead = content.text(locale.get("lead"))
    if language_code == source:
        title = title or content.article_title(data, cluster)
        lead = lead or content.excerpt(data, cluster)
    elif not title:
        source_locale = locales.get(source)
        if isinstance(source_locale, dict):
            title = content.text(source_locale.get("title"))
        title = title or content.article_title(data, cluster)
    title = title[:255]
    return Article(
        title=title,
        slug_base=_locale_slug_base(locale, title),
        lead=lead,
        body=_locale_body(locale),
        tags=content.tags(data, cluster),
        publish_date=_publish_date(data),
        publish_mode=data.get("publish_mode"),
        cluster=cluster,
        data=data,
        language=language_code,
        seo_description=content.text(locale.get("seo_description"))[:255],
    )


def parse_article(data):
    if not isinstance(data, dict):
        raise InvalidPayload("payload must be a JSON object")
    clusters = data.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        raise InvalidPayload("payload has no clusters")
    cluster = clusters[0]
    if not isinstance(cluster, dict):
        raise InvalidPayload("clusters must contain objects")
    if data.get("mode") != "article" or not content.text(data.get("llm_response")):
        raise InvalidPayload(
            "payload is not a generated article (mode=article + llm_response required)"
        )

    identity = parse_identity(data)
    if identity is not None and identity.source_lang and identity.locales:
        return article_for_locale(
            data, identity.source_lang, identity.locales[identity.source_lang]
        )

    return Article(
        title=content.article_title(data, cluster),
        slug_base=_slug_base(cluster),
        lead=content.excerpt(data, cluster),
        body=content.render_body(data.get("llm_response", "")),
        tags=content.tags(data, cluster),
        publish_date=_publish_date(data),
        publish_mode=data.get("publish_mode"),
        cluster=cluster,
        data=data,
        language=(identity.source_lang or None) if identity is not None else None,
    )
