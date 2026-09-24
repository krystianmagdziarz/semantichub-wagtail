import re

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from markdown_it import MarkdownIt

_MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable("table")

_HTML_OPENING_TAG = re.compile(r"^<(?:!--|!doctype|[a-zA-Z][a-zA-Z0-9-]*)[\s>/]")


def _looks_like_html(text):
    stripped = text.lstrip()
    if not _HTML_OPENING_TAG.match(stripped):
        return False
    return "</" in stripped or "/>" in stripped


def render_body(llm_response):
    text = llm_response or ""
    if not text.strip():
        return ""
    if _looks_like_html(text):
        return text
    return _MARKDOWN.render(text)


def text(value):
    return value.strip() if isinstance(value, str) else ""


def article_title(payload, cluster):
    title = text(payload.get("title")) or text(cluster.get("name"))
    return title[:255]


def excerpt(payload, cluster):
    for value in (
        payload.get("lead"),
        cluster.get("description"),
        cluster.get("meta_description"),
    ):
        stripped = text(value)
        if stripped:
            return stripped
    return ""


def tags(payload, cluster):
    raw = payload.get("tags")
    if not isinstance(raw, list):
        groups = cluster.get("semantic_groups")
        raw = list(groups) if isinstance(groups, dict) else []
    out = []
    for value in raw:
        tag = text(value)[:100]
        if tag and tag not in out:
            out.append(tag)
    return out[:10]


def publish_date(executed_at):
    try:
        parsed = parse_datetime(text(executed_at))
    except ValueError:
        parsed = None
    if parsed is not None:
        return parsed.date()
    return timezone.now().date()


def unique_slug(parent, base):
    slug = base or "post"
    candidate = slug
    n = 2
    existing = set(parent.get_children().values_list("slug", flat=True))
    while candidate in existing:
        candidate = f"{slug}-{n}"
        n += 1
    return candidate
