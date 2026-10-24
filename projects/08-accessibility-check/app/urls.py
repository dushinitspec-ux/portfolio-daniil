"""URL normalisation, the same-origin rule and the guard against scanning private networks."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

# Links to these are files, not pages: requesting them would only waste the page budget.
NON_PAGE_EXTENSIONS = frozenset(
    {
        ".7z", ".avi", ".avif", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot", ".exe",
        ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".js", ".json", ".m4a", ".mov", ".mp3",
        ".mp4", ".ogg", ".otf", ".pdf", ".png", ".ppt", ".pptx", ".rar", ".rss", ".svg",
        ".tar", ".tif", ".tiff", ".ttf", ".txt", ".wav", ".webm", ".webp", ".woff", ".woff2",
        ".xls", ".xlsx", ".xml", ".zip",
    }
)  # fmt: skip
DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidURL(ValueError):
    """The text is not an http(s) URL that can be scanned."""


class TargetNotAllowed(ValueError):
    """The URL points to a private or local address and private targets are disabled."""


def normalize(url: str) -> str:
    """Canonical form used to de-duplicate pages: lower-case scheme and host, no default
    port, no fragment, "/" for an empty path. The query string is kept."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = parts.hostname or ""  # already lower-case, without user info
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port
    netloc = host if port in (None, DEFAULT_PORTS.get(scheme)) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def origin(url: str) -> str:
    parts = urlsplit(normalize(url))
    return f"{parts.scheme}://{parts.netloc}"


def same_origin(a: str, b: str) -> bool:
    return origin(a) == origin(b)


def parse_start_url(text: str) -> str:
    """User input -> a normalised start URL. "example.com" becomes "https://example.com/"."""
    text = text.strip()
    if not text:
        raise InvalidURL("Enter the address of a website.")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidURL("Only http:// and https:// addresses can be scanned.")
    if not parts.hostname:
        raise InvalidURL("The address has no host name.")
    if parts.username or parts.password:
        raise InvalidURL("Addresses with a user name or password are not accepted.")
    try:
        _ = parts.port
    except ValueError as exc:
        raise InvalidURL("The port number is not valid.") from exc
    return normalize(text)


def resolve_link(base: str, href: str) -> str | None:
    """Absolute, normalised http(s) URL for a link, or None for mailto:, tel:, files, etc."""
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    absolute = urljoin(base, href)
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    last = parts.path.rsplit("/", 1)[-1].lower()
    if "." in last and "." + last.rsplit(".", 1)[-1] in NON_PAGE_EXTENSIONS:
        return None
    return normalize(absolute)


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def ensure_public(url: str) -> None:
    """Raise TargetNotAllowed if the host is, or resolves to, a non-public address."""
    host = urlsplit(url).hostname or ""
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise InvalidURL(f"The host name {host!r} was not found.") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses or not all(_is_public(ip) for ip in addresses):
        raise TargetNotAllowed(
            f"{host} is a private or local address. Scanning those is disabled "
            "(set ALLOW_PRIVATE_TARGETS=true for your own network)."
        )
