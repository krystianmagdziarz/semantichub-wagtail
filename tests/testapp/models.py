from django.db import models
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.models import Page


class ArticleIndexPage(Page):
    subpage_types = ["testapp.ArticlePage"]


class ArticlePageTag(TaggedItemBase):
    content_object = ParentalKey(
        "testapp.ArticlePage",
        on_delete=models.CASCADE,
        related_name="tagged_items",
    )


class ArticlePage(Page):
    excerpt = models.TextField(blank=True)
    body = models.TextField(blank=True)
    publish_date = models.DateField(null=True, blank=True)
    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    tags = ClusterTaggableManager(through=ArticlePageTag, blank=True)

    parent_page_types = ["testapp.ArticleIndexPage"]
