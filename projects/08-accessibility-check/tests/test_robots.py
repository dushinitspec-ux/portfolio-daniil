from app.robots import Robots

BOT = "AccessibilityCheckBot"
SITE = "https://shop.test"


def allowed(robots_txt: str, path: str, agent: str = BOT) -> bool:
    return Robots.parse(robots_txt).allowed(SITE + path, agent)


def test_longest_match_wins_not_the_first_one() -> None:
    # Python's urllib.robotparser would apply the first matching line (Disallow) here.
    rules = "User-agent: *\nDisallow: /shop\nAllow: /shop/public\n"
    assert allowed(rules, "/shop/public/bags")
    assert not allowed(rules, "/shop/cart")


def test_allow_wins_a_tie() -> None:
    assert allowed("User-agent: *\nDisallow: /page\nAllow: /page\n", "/page")


def test_wildcards_and_end_anchor() -> None:
    rules = "User-agent: *\nDisallow: /*?sort=\nDisallow: /*.pdf$\n"
    assert not allowed(rules, "/bags?sort=price")
    assert allowed(rules, "/bags?page=2")
    assert not allowed(rules, "/files/catalogue.pdf")
    assert allowed(rules, "/files/catalogue.pdf.html")


def test_own_group_replaces_the_star_group() -> None:
    rules = "User-agent: *\nDisallow: /\n\nUser-agent: accessibilitycheckbot\nDisallow: /admin\n"
    assert allowed(rules, "/products")
    assert not allowed(rules, "/admin/login")
    assert not allowed(rules, "/products", agent="OtherBot")


def test_consecutive_user_agent_lines_share_rules_and_comments_are_ignored() -> None:
    rules = "# hello\nUser-agent: Googlebot\nUser-agent: AccessibilityCheckBot\nDisallow: /x # no\n"
    assert not allowed(rules, "/x/1")
    assert allowed(rules, "/y")


def test_empty_disallow_and_rules_outside_groups() -> None:
    assert allowed("Disallow: /\nUser-agent: *\nDisallow:\n", "/anything")


def test_robots_txt_itself_is_always_allowed_and_disallow_all() -> None:
    robots = Robots.disallow_all("unreachable")
    assert not robots.allowed(SITE + "/", BOT)
    assert allowed("User-agent: *\nDisallow: /\n", "/robots.txt")


def test_crawl_delay() -> None:
    robots = Robots.parse("User-agent: *\nCrawl-delay: 3\nDisallow: /tmp\n")
    assert robots.crawl_delay(BOT) == 3.0
    assert Robots.parse("User-agent: *\nCrawl-delay: soon\n").crawl_delay(BOT) is None
