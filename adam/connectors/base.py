"""Base protocol and data models for portal connectors."""

import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Any, Iterator, Optional, List

import httpx

from adam.config import DEFAULT_USER_AGENT, REQUEST_TIMEOUT_SECONDS
from adam.db.models import Source


def create_gov_ssl_context() -> ssl.SSLContext:
    """Create an SSLContext that allows legacy server renegotiation for NIC/state government portals."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    except Exception:
        pass
    return ctx


def create_gov_http_client(
    timeout: float = REQUEST_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
    follow_redirects: bool = True,
) -> httpx.Client:
    """Instantiate an httpx Client tuned for state government websites and CDNs."""
    ctx = create_gov_ssl_context()
    return httpx.Client(
        headers={"User-Agent": user_agent},
        timeout=timeout,
        follow_redirects=follow_redirects,
        verify=ctx,
    )



@dataclass
class DiscoveredItem:
    """A record discovered on an authorized portal listing/sitemap."""
    source_url: str
    title: str
    doc_type: str
    department_id: str
    detail_page_url: Optional[str] = None
    displayed_date: Optional[date] = None
    go_number: Optional[str] = None
    gazette_number: Optional[str] = None
    category: Optional[str] = None
    authority_level: Optional[str] = None
    classification: Optional[str] = None
    language: str = "hi"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    """Result of fetching an original document from its source URL."""
    source_url: str
    data: bytes
    http_status: int
    http_headers: Dict[str, str]
    retrieved_at: datetime
    detail_page_bytes: Optional[bytes] = None


class BaseConnector(ABC):
    """Abstract base connector for acquiring Uttarakhand departmental records."""

    @abstractmethod
    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        """Discover documents from authorized index/sitemap/category pages."""
        pass

    @abstractmethod
    def fetch(self, item: DiscoveredItem) -> FetchResult:
        """Fetch immutable original bytes and HTTP headers for a discovered item."""
        pass
