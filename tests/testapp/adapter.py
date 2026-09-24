from semantichub_wagtail.adapters import ArticleAdapter, PairAdapter
from semantichub_wagtail.models import IngestPublication
from tests.testapp.models import ArticleIndexPage, ArticlePage


class ExampleArticleAdapter(ArticleAdapter):
    def get_parent(self, article):
        return ArticleIndexPage.objects.first()

    def build(self, article):
        return ArticlePage(
            title=article.title,
            excerpt=article.lead,
            body=article.body,
            publish_date=article.publish_date,
            cover_image=article.cover,
        )

    def update(self, page, article):
        page.title = article.title
        page.excerpt = article.lead
        page.body = article.body
        page.publish_date = article.publish_date
        if article.cover is not None:
            page.cover_image = article.cover

    def apply_tags(self, page, tags):
        page.tags.set(tags)


class ExamplePairAdapter(PairAdapter):
    def upsert(self, publication, data, revision):
        index = ArticleIndexPage.objects.first()
        if publication is None:
            publication = IngestPublication()
            en_page = index.add_child(instance=ArticlePage(**self._fields(data["locales"]["en"])))
            pl_page = index.add_child(instance=ArticlePage(**self._fields(data["locales"]["pl"])))
        else:
            en_page = publication.en_page.specific
            pl_page = publication.pl_page.specific
            self._apply(en_page, data["locales"]["en"])
            self._apply(pl_page, data["locales"]["pl"])
        publication.en_page = en_page
        publication.pl_page = pl_page
        return publication

    def _fields(self, locale_data):
        return {
            "title": locale_data["title"],
            "slug": locale_data["slug"],
            "excerpt": locale_data.get("lead", ""),
            "body": locale_data.get("body", ""),
        }

    def _apply(self, page, locale_data):
        for name, value in self._fields(locale_data).items():
            setattr(page, name, value)
        page.save()
