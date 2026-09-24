from dataclasses import dataclass, field
from datetime import date

from django.utils.text import slugify

from semantichub_wagtail import content

MAX_SLUG_BASE_LENGTH = 200


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
    cover: object | None = field(default=None)


def _slug_base(cluster):
    source = content.text(cluster.get("url_slug")) or content.text(cluster.get("name"))
    return slugify(source)[:MAX_SLUG_BASE_LENGTH].strip("-")


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

    return Article(
        title=content.article_title(data, cluster),
        slug_base=_slug_base(cluster),
        lead=content.excerpt(data, cluster),
        body=content.render_body(data.get("llm_response", "")),
        tags=content.tags(data, cluster),
        publish_date=content.publish_date(data.get("executed_at")),
        publish_mode=data.get("publish_mode"),
        cluster=cluster,
        data=data,
    )
