from semantichub_wagtail.adapters import ArticleAdapter
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
