import pytest
from wagtail.images import get_image_model

from semantichub_wagtail import images
from semantichub_wagtail.images import fetch_image

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeResponse:
    def __init__(self, content=PNG, content_type="image/png", error=None):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error


class FakeClient:
    response = FakeResponse()

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        return self.response


@pytest.fixture
def fake_http(monkeypatch):
    def configure(**kwargs):
        FakeClient.response = FakeResponse(**kwargs)

    monkeypatch.setattr(images.httpx, "Client", FakeClient)
    configure()
    return configure


@pytest.mark.django_db
class TestFetchImage:
    def test_https_image_is_downloaded(self, fake_http):
        image = fetch_image({"url": "https://semantichub.app/x.png"}, "Cover")
        assert image is not None
        assert image.width == 1
        assert image.height == 1
        assert image.title == "Cover"

    def test_http_url_is_ignored(self, fake_http):
        assert fetch_image({"url": "http://semantichub.app/x.png"}, "Cover") is None

    def test_missing_url_is_ignored(self, fake_http):
        assert fetch_image({}, "Cover") is None
        assert fetch_image(None, "Cover") is None
        assert fetch_image("https://semantichub.app/x.png", "Cover") is None

    def test_non_image_content_type_is_ignored(self, fake_http):
        fake_http(content_type="text/html")
        assert fetch_image({"url": "https://semantichub.app/x"}, "Cover") is None

    def test_oversized_file_is_ignored(self, fake_http):
        fake_http(content=b"x" * (12 * 1024 * 1024 + 1))
        assert fetch_image({"url": "https://semantichub.app/x.png"}, "Cover") is None

    def test_network_error_gives_none(self, fake_http):
        fake_http(error=RuntimeError("boom"))
        assert fetch_image({"url": "https://semantichub.app/x.png"}, "Cover") is None

    def test_bytes_that_are_not_an_image_give_none(self, fake_http):
        fake_http(content=b"not really a png")
        assert fetch_image({"url": "https://semantichub.app/x.png"}, "Cover") is None

    def test_same_content_is_not_duplicated(self, fake_http):
        first = fetch_image({"url": "https://semantichub.app/x.png"}, "Cover")
        second = fetch_image({"url": "https://semantichub.app/y.png"}, "Other")
        assert first.pk == second.pk
        assert get_image_model().objects.count() == 1
