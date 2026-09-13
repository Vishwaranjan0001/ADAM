"""Tests for URL crawling allow-lists, rate limiting, and robots compliance."""

import pytest

from adam.ingest.crawler import (
    UrlCrawlerGuard,
    DisallowedUrlError,
    CrawlerRateLimiter,
    RobotsComplianceGuard,
)


def test_url_guard_permitted_urls():
    guard = UrlCrawlerGuard(
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/", "/document-category/"],
    )

    assert guard.is_url_allowed("https://ekosh.uk.gov.in/government-orders/") is True
    assert guard.is_url_allowed("https://ekosh.uk.gov.in/government-orders/2024/order.pdf") is True
    assert guard.is_url_allowed("https://ekosh.uk.gov.in/document-category/manuals.pdf") is True


def test_url_guard_rejects_unauthorized_domains_and_paths():
    guard = UrlCrawlerGuard(
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/"],
    )

    # Unauthorized path on same domain
    assert guard.is_url_allowed("https://ekosh.uk.gov.in/secret-admin-portal/") is False

    # External unauthorized domain (blog, search engine, mirror)
    assert guard.is_url_allowed("https://newsblog.com/government-orders/order.pdf") is False
    assert guard.is_url_allowed("https://search.google.com/url?q=ekosh") is False

    # Exception raising test
    with pytest.raises(DisallowedUrlError):
        guard.validate_or_raise("https://unauthorized-portal.com/data.pdf")


def test_rate_limiter_pacing():
    limiter = CrawlerRateLimiter(rate_limit_per_minute=60)  # 1 req/sec
    url = "https://ekosh.uk.gov.in/government-orders/list"

    # First request: 0 delay
    wait1 = limiter.acquire(url)
    assert wait1 == 0.0

    # Immediate second request: requires approx 1s wait
    wait2 = limiter.acquire(url)
    assert 0.8 <= wait2 <= 1.05


def test_robots_guard():
    guard = RobotsComplianceGuard()
    base = "https://ekosh.uk.gov.in"
    robots_txt = """
    User-agent: *
    Disallow: /private/
    Allow: /government-orders/
    """
    guard.set_robots_content(base, robots_txt)

    assert guard.can_fetch("https://ekosh.uk.gov.in/government-orders/doc.pdf") is True
    assert guard.can_fetch("https://ekosh.uk.gov.in/private/confidential.pdf") is False
