import socket

import httpx
import pytest
from wagtail.images import get_image_model

from semantichub_wagtail import images
from semantichub_wagtail.images import fetch_image

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

PUBLIC_IP = "93.184.215.14"
URL = "https://cdn.example.com/x.png"


class FakeNetwork:
    def __init__(self):
        self.dns = {"cdn.example.com": [PUBLIC_IP], "other.example.com": ["93.184.215.15"]}
        self.routes = {}
        self.requests = []

    def resolve(self, host, port, *args, **kwargs):
        if host not in self.dns:
            raise socket.gaierror("unknown host")
        answers = []
        for ip in self.dns[host]:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            answers.append((family, socket.SOCK_STREAM, 6, "", (ip, port)))
        return answers

    def handle(self, request):
        self.requests.append(request)
        key = (request.url.host, request.headers["Host"], request.url.path)
        route = self.routes.get(key)
        if route is None:
            return httpx.Response(404)
        if isinstance(route, Exception):
            raise route
        return route

    def serve(self, host, path, response, ip=PUBLIC_IP):
        self.routes[(ip, host, path)] = response


def png_response(content=PNG, content_type="image/png", headers=None):
    return httpx.Response(
        200, content=content, headers={"Content-Type": content_type, **(headers or {})}
    )


@pytest.fixture
def network(monkeypatch):
    fake = FakeNetwork()
    fake.serve("cdn.example.com", "/x.png", png_response())
    monkeypatch.setattr(images.socket, "getaddrinfo", fake.resolve)
    monkeypatch.setattr(
        images,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(fake.handle), follow_redirects=False),
    )
    return fake


@pytest.mark.django_db
class TestFetchImage:
    def test_https_image_is_downloaded(self, network):
        image = fetch_image({"url": URL}, "Cover")
        assert image is not None
        assert image.width == 1
        assert image.height == 1
        assert image.title == "Cover"
        assert image.file.name.endswith(".png")

    def test_connection_is_pinned_to_the_checked_address(self, network):
        fetch_image({"url": URL}, "Cover")
        request = network.requests[0]
        assert request.url.host == PUBLIC_IP
        assert request.headers["Host"] == "cdn.example.com"
        assert request.extensions["sni_hostname"] == "cdn.example.com"

    def test_requests_identify_the_package(self, network):
        fetch_image({"url": URL}, "Cover")
        assert network.requests[0].headers["User-Agent"].startswith("semantichub-wagtail/")

    def test_http_url_is_ignored(self, network):
        assert fetch_image({"url": "http://cdn.example.com/x.png"}, "Cover") is None
        assert network.requests == []

    def test_missing_url_is_ignored(self, network):
        assert fetch_image({}, "Cover") is None
        assert fetch_image(None, "Cover") is None
        assert fetch_image(URL, "Cover") is None
        assert fetch_image({"url": 42}, "Cover") is None

    def test_credentials_in_url_are_refused(self, network):
        assert fetch_image({"url": "https://user:pass@cdn.example.com/x.png"}, "Cover") is None
        assert network.requests == []

    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.0.0.5",
            "172.16.0.1",
            "192.168.1.10",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "::1",
            "fd00::1",
            "::ffff:127.0.0.1",
            "224.0.0.1",
        ],
    )
    def test_non_public_addresses_are_refused(self, network, address):
        network.dns["cdn.example.com"] = [address]
        assert fetch_image({"url": URL}, "Cover") is None
        assert network.requests == []

    def test_any_non_public_address_in_the_answer_is_refused(self, network):
        network.dns["cdn.example.com"] = [PUBLIC_IP, "10.0.0.5"]
        assert fetch_image({"url": URL}, "Cover") is None
        assert network.requests == []

    def test_unresolvable_host_gives_none(self, network):
        assert fetch_image({"url": "https://nowhere.example.com/x.png"}, "Cover") is None

    def test_redirect_to_public_https_is_followed(self, network):
        network.serve(
            "cdn.example.com",
            "/old.png",
            httpx.Response(302, headers={"Location": "https://other.example.com/new.png"}),
        )
        network.serve("other.example.com", "/new.png", png_response(), ip="93.184.215.15")
        assert fetch_image({"url": "https://cdn.example.com/old.png"}, "Cover") is not None

    def test_redirect_to_private_address_is_refused(self, network):
        network.dns["internal.example.com"] = ["10.0.0.5"]
        network.serve(
            "cdn.example.com",
            "/old.png",
            httpx.Response(302, headers={"Location": "https://internal.example.com/x.png"}),
        )
        assert fetch_image({"url": "https://cdn.example.com/old.png"}, "Cover") is None
        assert [r.url.host for r in network.requests] == [PUBLIC_IP]

    def test_redirect_to_plain_http_is_refused(self, network):
        network.serve(
            "cdn.example.com",
            "/old.png",
            httpx.Response(302, headers={"Location": "http://cdn.example.com/x.png"}),
        )
        assert fetch_image({"url": "https://cdn.example.com/old.png"}, "Cover") is None
        assert len(network.requests) == 1

    def test_redirect_loop_gives_up(self, network):
        network.serve(
            "cdn.example.com",
            "/loop.png",
            httpx.Response(302, headers={"Location": "/loop.png"}),
        )
        assert fetch_image({"url": "https://cdn.example.com/loop.png"}, "Cover") is None
        assert len(network.requests) == images.MAX_REDIRECTS + 1

    def test_non_image_content_type_is_ignored(self, network):
        network.serve("cdn.example.com", "/x.png", png_response(content_type="text/html"))
        assert fetch_image({"url": URL}, "Cover") is None

    def test_svg_is_refused(self, network):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
        network.serve("cdn.example.com", "/x.png", png_response(svg, "image/svg+xml"))
        assert fetch_image({"url": URL}, "Cover") is None

    def test_svg_bytes_behind_a_raster_content_type_are_refused(self, network):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
        network.serve("cdn.example.com", "/x.png", png_response(svg, "image/png"))
        assert fetch_image({"url": URL}, "Cover") is None

    def test_declared_oversized_file_is_ignored(self, network):
        network.serve(
            "cdn.example.com",
            "/x.png",
            png_response(headers={"Content-Length": str(images.MAX_BYTES + 1)}),
        )
        assert fetch_image({"url": URL}, "Cover") is None

    def test_streamed_oversized_file_is_ignored(self, network):
        body = httpx.ByteStream(b"x" * (images.MAX_BYTES + 1))
        network.serve(
            "cdn.example.com",
            "/x.png",
            httpx.Response(200, stream=body, headers={"Content-Type": "image/png"}),
        )
        assert fetch_image({"url": URL}, "Cover") is None

    def test_error_status_gives_none(self, network):
        network.serve("cdn.example.com", "/x.png", httpx.Response(500))
        assert fetch_image({"url": URL}, "Cover") is None

    def test_network_error_gives_none(self, network):
        network.serve("cdn.example.com", "/x.png", httpx.ConnectError("boom"))
        assert fetch_image({"url": URL}, "Cover") is None

    def test_bytes_that_are_not_an_image_give_none(self, network):
        network.serve("cdn.example.com", "/x.png", png_response(b"not really a png"))
        assert fetch_image({"url": URL}, "Cover") is None

    def test_same_content_is_not_duplicated(self, network):
        network.serve("other.example.com", "/y.png", png_response(), ip="93.184.215.15")
        first = fetch_image({"url": URL}, "Cover")
        second = fetch_image({"url": "https://other.example.com/y.png"}, "Other")
        assert first.pk == second.pk
        assert get_image_model().objects.count() == 1
