from dataclasses import dataclass, field
from datetime import date

from django.utils.text import slugify

from semantichub_wagtail import content


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


def parse_article(data):
    if not isinstance(data, dict):
        raise InvalidPayload("payload must be a JSON object")
    clusters = data.get("clusters") or []
    if not clusters:
        raise InvalidPayload("payload has no clusters")
    if data.get("mode") != "article" or not (data.get("llm_response") or "").strip():
        raise InvalidPayload(
            "payload is not a generated article (mode=article + llm_response required)"
        )

    cluster = clusters[0]
    return Article(
        title=content.article_title(data, cluster),
        slug_base=cluster.get("url_slug") or slugify(cluster.get("name", "")),
        lead=content.excerpt(data, cluster),
        body=content.render_body(data.get("llm_response", "")),
        tags=content.tags(data, cluster),
        publish_date=content.publish_date(data.get("executed_at")),
        publish_mode=data.get("publish_mode"),
        cluster=cluster,
        data=data,
    )
