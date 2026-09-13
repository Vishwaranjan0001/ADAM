"""Pilot connector for Treasury / IFMS Uttarakhand (ekosh.uk.gov.in)."""

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


class EkoshTreasuryConnector(BaseConnector):
    """Acquires Treasury/IFMS Government Orders and RTI manuals from ekosh.uk.gov.in."""

    GO_INDEX_PATH = "/government-orders/"
    RTI_INDEX_PATH = "/document-category/rti-documents-manuals/"

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        fetcher: Optional[Callable[[str], httpx.Response]] = None,
    ):
        self.http_client = http_client
        self._custom_fetcher = fetcher
        self.rate_limiter = CrawlerRateLimiter(rate_limit_per_minute=30)

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
        """Crawl allowed pages and yield discovered GOs and RTI manuals."""
        guard = UrlCrawlerGuard(
            permitted_domains=source.permitted_domains,
            permitted_path_prefixes=source.permitted_path_prefixes,
        )

        base_url = f"https://{source.permitted_domains[0]}"

        # Discover from all authorized non-root path prefixes
        for prefix in source.permitted_path_prefixes:
            if prefix == "/" or prefix.startswith("/s3"):
                continue
            target_url = urljoin(base_url, prefix)
            if not guard.is_url_allowed(target_url):
                continue
            if "rti" in prefix.lower():
                yield from self._discover_rti_manuals(target_url, guard, source)
            else:
                yield from self._discover_gos(target_url, guard, source)

    def _discover_gos(
        self,
        index_url: str,
        guard: UrlCrawlerGuard,
        source: Source,
    ) -> Iterator[DiscoveredItem]:
        try:
            resp = self._request(index_url)
        except Exception:
            return
        if resp.status_code != 200:
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        dept_id = source.department_id or DepartmentId.FINANCE_TREASURY.value
        # Find listings (tables, articles, or links ending in .pdf or detail view)
        rows = soup.find_all("tr")
        if rows:
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    link_tag = row.find("a", href=True)
                    if link_tag:
                        href = link_tag["href"]
                        full_url = urljoin(index_url, href)
                        if not guard.is_url_allowed(full_url):
                            continue

                        link_text = link_tag.get_text(strip=True)

                        def _is_generic(t: str) -> bool:
                            s = t.lower().strip()
                            return any(k in s for k in ("download", "view(", "view (", "click here", "accessible version")) or s in ("view", "pdf", "details")

                        if len(cols) >= 4:
                            # 4-column layout: [Order No, Date, Subject/Title, Download]
                            title = cols[2].get_text(strip=True)
                            go_num = cols[0].get_text(strip=True)
                            date_text = cols[1].get_text(strip=True)
                        elif len(cols) == 3:
                            c2 = cols[2].get_text(strip=True)
                            if _is_generic(c2):
                                # 3-column Sugamya layout: [Title, Date, Download]
                                title = cols[0].get_text(strip=True)
                                go_num = None
                                date_text = cols[1].get_text(strip=True)
                            else:
                                title = cols[2].get_text(strip=True)
                                go_num = cols[0].get_text(strip=True)
                                date_text = cols[1].get_text(strip=True)
                        else:
                            title = cols[0].get_text(strip=True) if len(cols) >= 1 else link_text
                            date_text = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                            go_num = None

                        if not go_num and title:
                            m = re.search(r'(?:Notification\s*No[.:–-]*|GO\s*No[.:–-]*|No[.:–-]*|Order\s*No[.:–-]*|संख्या[.:–-]*)\s*([^\s,]+(?:/[^\s,]+)+)', title, re.IGNORECASE)
                            if m:
                                go_num = m.group(1).strip()

                        parsed_date = self._parse_date(date_text)

                        yield DiscoveredItem(
                            source_url=guard.normalize_url(full_url),
                            title=title or "Government Order",
                            doc_type=DocType.GO.value,
                            department_id=dept_id,
                            detail_page_url=index_url,
                            displayed_date=parsed_date,
                            go_number=go_num,
                            authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
                            classification=source.access_classification or Classification.PUBLIC.value,
                            metadata={"table_columns": [c.get_text(strip=True) for c in cols]},
                        )
        else:
            # Fallback for anchor links if portal uses cards/lists
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(index_url, href)
                if guard.is_url_allowed(full_url) and (full_url.endswith(".pdf") or "download" in full_url):
                    title = a.get_text(strip=True) or "Government Order"
                    yield DiscoveredItem(
                        source_url=guard.normalize_url(full_url),
                        title=title,
                        doc_type=DocType.GO.value,
                        department_id=dept_id,
                        detail_page_url=index_url,
                        authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
                        classification=source.access_classification or Classification.PUBLIC.value,
                    )

    def _discover_rti_manuals(
        self,
        index_url: str,
        guard: UrlCrawlerGuard,
        source: Source,
    ) -> Iterator[DiscoveredItem]:
        try:
            resp = self._request(index_url)
        except Exception:
            return
        if resp.status_code != 200:
            return

        dept_id = source.department_id or DepartmentId.FINANCE_TREASURY.value
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(index_url, href)
            if guard.is_url_allowed(full_url) and (full_url.endswith(".pdf") or "download" in full_url):
                title = a.get_text(strip=True) or "RTI Document / Manual"
                yield DiscoveredItem(
                    source_url=guard.normalize_url(full_url),
                    title=title,
                    doc_type=DocType.RTI_MANUAL.value,
                    department_id=dept_id,
                    detail_page_url=index_url,
                    category="RTI Rules and Manuals",
                    authority_level=AuthorityLevel.HEAD_OF_DEPARTMENT.value,
                    classification=source.access_classification or Classification.PUBLIC.value,
                )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        """Fetch immutable original bytes for a discovered document and capture detail page."""
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
        """Try parsing Indian date formats (DD/MM/YYYY or DD-MM-YYYY or YYYY-MM-DD)."""
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
