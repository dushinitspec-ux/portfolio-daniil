"""Parsing a fetched HTML page and finding the links a crawler follows.

Kept apart from the crawler (which needs httpx) so the same code also runs in the in-browser
demo, where the bundled sample pages are read from files instead of fetched.
"""

from bs4 import BeautifulSoup, Tag

from app.urls import resolve_link


def parse_html(body: bytes, content_type: str) -> BeautifulSoup:
    charset = None
    for param in content_type.split(";")[1:]:
        key, _, value = param.partition("=")
        if key.strip().lower() == "charset" and value.strip():
            charset = value.strip().strip("\"'")
    # Without a charset in the header, BeautifulSoup reads <meta charset> or guesses.
    return BeautifulSoup(body, "lxml", from_encoding=charset)


def extract_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    base = page_url
    base_tag = soup.find("base", href=True)
    if isinstance(base_tag, Tag):
        base = resolve_link(page_url, str(base_tag["href"])) or page_url
    links = []
    for tag in soup.find_all(["a", "area"], href=True):
        if isinstance(tag, Tag) and (url := resolve_link(base, str(tag["href"]))):
            links.append(url)
    return links
