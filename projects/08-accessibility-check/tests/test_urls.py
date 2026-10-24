import pytest

from app.urls import (
    InvalidURL,
    TargetNotAllowed,
    ensure_public,
    normalize,
    parse_start_url,
    resolve_link,
    same_origin,
)


def test_normalize() -> None:
    assert normalize("HTTPS://Shop.TEST:443/Bags?x=1#top") == "https://shop.test/Bags?x=1"
    assert normalize("http://shop.test") == "http://shop.test/"
    assert normalize("http://shop.test:8080/a") == "http://shop.test:8080/a"
    assert normalize("http://[::1]:8000/") == "http://[::1]:8000/"


def test_same_origin_compares_scheme_host_and_port() -> None:
    assert same_origin("https://shop.test/a", "https://SHOP.test:443/b")
    assert not same_origin("https://shop.test/", "http://shop.test/")
    assert not same_origin("https://shop.test/", "https://www.shop.test/")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("shop.test", "https://shop.test/"), (" http://shop.test/a ", "http://shop.test/a")],
)
def test_parse_start_url(text: str, expected: str) -> None:
    assert parse_start_url(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "ftp://shop.test/", "https://user:secret@shop.test/", "https://", "http://x:99999/"],
)
def test_parse_start_url_rejects(text: str) -> None:
    with pytest.raises(InvalidURL):
        parse_start_url(text)


def test_resolve_link_skips_non_pages() -> None:
    base = "https://shop.test/bags/"
    assert resolve_link(base, "tote.html#reviews") == "https://shop.test/bags/tote.html"
    assert resolve_link(base, "../contact") == "https://shop.test/contact"
    for href in ["#top", "mailto:a@b.test", "tel:+90", "javascript:void(0)", "x.pdf", "a.JPG"]:
        assert resolve_link(base, href) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://192.168.88.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/",
    ],
)
async def test_private_and_local_targets_are_refused(url: str) -> None:
    with pytest.raises(TargetNotAllowed):
        await ensure_public(url)


async def test_public_address_is_allowed() -> None:
    await ensure_public("http://93.184.215.14/")  # a public IPv4 literal, no DNS needed
