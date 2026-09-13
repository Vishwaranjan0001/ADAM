"""Connector for Uttarakhand e-Gazette portal and official notifications."""

from datetime import datetime, timezone, date
import re
from typing import Iterator, Optional, Dict, Any, Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from adam.config import DEFAULT_USER_AGENT, REQUEST_TIMEOUT_SECONDS
from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult, create_gov_http_client
from adam.db.models import Source
from adam.ingest.crawler import UrlCrawlerGuard, CrawlerRateLimiter
from adam.vocabularies import DocType, DepartmentId, AuthorityLevel, Classification


class EGazetteConnector(BaseConnector):
    """Acquires published Gazette notifications and state statutory orders."""

    GAZETTE_PATH = "/gazette/"

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        fetcher: Optional[Callable[[str], httpx.Response]] = None,
    ):
        self.http_client = http_client
        self._custom_fetcher = fetcher
        self.rate_limiter = CrawlerRateLimiter(rate_limit_per_minute=25)

    def _get_client(self) -> httpx.Client:
        if self.http_client:
            return self.http_client
        return create_gov_http_client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            user_agent=DEFAULT_USER_AGENT,
            follow_redirects=True,
        )

    def _request(self, url: str) -> httpx.Response:
        self.rate_limiter.wait(url)
        if self._custom_fetcher:
            return self._custom_fetcher(url)
        client = self._get_client()
        return client.get(url)

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        guard = UrlCrawlerGuard(
            permitted_domains=source.permitted_domains,
            permitted_path_prefixes=source.permitted_path_prefixes,
        )
        base_url = f"https://{source.permitted_domains[0]}"

        for prefix in source.permitted_path_prefixes:
            if prefix == "/":
                continue
            target_url = urljoin(base_url, prefix)
            if not guard.is_url_allowed(target_url):
                continue

            try:
                resp = self._request(target_url)
            except Exception:
                continue

            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(target_url, href)
                if guard.is_url_allowed(full_url) and (full_url.endswith(".pdf") or "gazette" in full_url.lower()):
                    title = a.get_text(strip=True) or "Uttarakhand Official Gazette Publication"
                    yield DiscoveredItem(
                        source_url=guard.normalize_url(full_url),
                        title=title,
                        doc_type=DocType.GAZETTE.value,
                        department_id=source.department_id,
                        detail_page_url=target_url,
                        authority_level=AuthorityLevel.STATE_CABINET.value,
                        classification=source.access_classification or Classification.PUBLIC.value,
                    )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        resp = self._request(item.source_url)
        headers_dict = {k.lower(): v for k, v in resp.headers.items()}
        status = resp.status_code
        content = resp.content

        # Reject soft-404 HTML responses returned with 200 status code
        if status == 200:
            lower_head = content[:1024].lower()
            if b"<title>404" in lower_head or b"notfound" in lower_head:
                status = 404
            elif item.source_url.lower().endswith(".pdf") and not content.startswith(b"%PDF"):
                status = 404

        return FetchResult(
            source_url=item.source_url,
            data=content,
            http_status=status,
            http_headers=headers_dict,
            retrieved_at=datetime.now(timezone.utc),
        )
