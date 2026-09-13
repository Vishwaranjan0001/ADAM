"""Pilot connector for Uttarakhand Rural Development (ukrd.uk.gov.in)."""

from datetime import datetime, timezone, date
import re
from typing import Iterator, Optional, Dict, Any, Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from adam.config import DEFAULT_USER_AGENT, REQUEST_TIMEOUT_SECONDS
from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult, create_gov_http_client
from adam.db.models import Source
from adam.ingest.crawler import UrlCrawlerGuard, CrawlerRateLimiter
from adam.vocabularies import DocType, DepartmentId, AuthorityLevel, Classification


class UkrdConnector(BaseConnector):
    """Acquires Rural Development documents, paginating only owner-approved categories."""

    DOCUMENTS_PATH = "/documents/"

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        fetcher: Optional[Callable[[str], httpx.Response]] = None,
    ):
        self.http_client = http_client
        self._custom_fetcher = fetcher
        self.rate_limiter = CrawlerRateLimiter(rate_limit_per_minute=20)

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
        for path_prefix in source.permitted_path_prefixes:
            target_url = urljoin(base_url, path_prefix)
            if guard.is_url_allowed(target_url):
                yield from self._paginate_category(target_url, guard, source)

    def _paginate_category(
        self,
        category_url: str,
        guard: UrlCrawlerGuard,
        source: Source,
    ) -> Iterator[DiscoveredItem]:
        current_url = category_url
        visited_pages = set()

        while current_url and current_url not in visited_pages:
            visited_pages.add(current_url)
            if not guard.is_url_allowed(current_url):
                break

            resp = self._request(current_url)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            # Check table rows for genuine title, date and download link
            rows = soup.find_all("tr")
            found_in_table = False
            if rows:
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        link_tag = row.find("a", href=True)
                        if link_tag:
                            href = link_tag["href"]
                            full_url = urljoin(current_url, href)
                            if guard.is_url_allowed(full_url) and (full_url.endswith(".pdf") or "download" in full_url.lower() or "upload" in full_url.lower()):
                                found_in_table = True
                                title = cols[0].get_text(strip=True) or link_tag.get_text(strip=True) or "Rural Development Document"
                                date_str = cols[1].get_text(strip=True) if len(cols) > 1 else None
                                parsed_date = self._parse_date(date_str) if date_str else None
                                yield DiscoveredItem(
                                    source_url=guard.normalize_url(full_url),
                                    title=title,
                                    doc_type=DocType.DEPARTMENTAL_DOCUMENT.value,
                                    department_id=DepartmentId.RURAL_DEVELOPMENT.value,
                                    detail_page_url=current_url,
                                    displayed_date=parsed_date,
                                    authority_level=AuthorityLevel.HEAD_OF_DEPARTMENT.value,
                                    classification=source.access_classification or Classification.PUBLIC.value,
                                    metadata={"departmental_scope": "Rural Development Department, Uttarakhand"},
                                )

            if not found_in_table:
                # Fallback for generic anchor links
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full_url = urljoin(current_url, href)
                    if guard.is_url_allowed(full_url) and (full_url.endswith(".pdf") or "download" in full_url.lower()):
                        title = a.get_text(strip=True) or "Rural Development Document"
                        yield DiscoveredItem(
                            source_url=guard.normalize_url(full_url),
                            title=title,
                            doc_type=DocType.DEPARTMENTAL_DOCUMENT.value,
                            department_id=DepartmentId.RURAL_DEVELOPMENT.value,
                            detail_page_url=current_url,
                            authority_level=AuthorityLevel.HEAD_OF_DEPARTMENT.value,
                            classification=source.access_classification or Classification.PUBLIC.value,
                            metadata={"departmental_scope": "Rural Development Department, Uttarakhand"},
                        )


            # Look for next page in pagination links
            next_link = soup.find("a", string=re.compile(r"Next|»|अगला", re.I))
            if next_link and next_link.get("href"):
                next_url = urljoin(current_url, next_link["href"])
                if guard.is_url_allowed(next_url) and next_url not in visited_pages:
                    current_url = next_url
                else:
                    break
            else:
                break

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        resp = self._request(item.source_url)
        detail_bytes = None
        if item.detail_page_url:
            try:
                detail_resp = self._request(item.detail_page_url)
                if detail_resp.status_code == 200:
                    detail_bytes = detail_resp.content
            except Exception:
                pass

        headers_dict = {k.lower(): v for k, v in resp.headers.items()}
        return FetchResult(
            source_url=item.source_url,
            data=resp.content,
            http_status=resp.status_code,
            http_headers=headers_dict,
            retrieved_at=datetime.now(timezone.utc),
            detail_page_bytes=detail_bytes,
        )

    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        """Parse Indian date formats (DD/MM/YYYY or DD-MM-YYYY or YYYY-MM-DD)."""
        match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", text)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            try:
                return date(year, month, day)
            except ValueError:
                pass
        iso_match = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
        if iso_match:
            year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            try:
                return date(year, month, day)
            except ValueError:
                pass
        return None

