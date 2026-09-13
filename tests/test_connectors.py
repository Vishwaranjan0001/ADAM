"""Tests for pilot connectors (Ekosh Treasury and UKRD)."""

from datetime import date
from typing import Dict
import httpx
import pytest

from adam.connectors.ekosh import EkoshTreasuryConnector
from adam.connectors.ukrd import UkrdConnector
from adam.db.models import Source
from adam.vocabularies import DepartmentId, Classification, RefreshCadence, DocType


def test_ekosh_treasury_connector_discovery(mock_treasury_html: str):
    source = Source(
        id="src_ekosh_treasury_go",
        name="Ekosh Treasury",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Director Treasury",
        owner_contact="dir@uk.gov.in",
        written_authority_ref="AUTH-1",
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.WEEKLY.value,
    )

    pdf_bytes = b"%PDF-1.4 mock order bytes"

    def mock_fetcher(url: str) -> httpx.Response:
        if "government-orders" in url and not url.endswith(".pdf"):
            return httpx.Response(
                status_code=200,
                text=mock_treasury_html,
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", url),
            )
        elif url.endswith(".pdf"):
            return httpx.Response(
                status_code=200,
                content=pdf_bytes,
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(status_code=404, request=httpx.Request("GET", url))

    connector = EkoshTreasuryConnector(fetcher=mock_fetcher)
    discovered = list(connector.discover(source))

    assert len(discovered) == 2
    item1 = discovered[0]
    assert item1.source_url == "https://ekosh.uk.gov.in/government-orders/go-2024-101.pdf"
    assert "Dearness Allowance" in item1.title
    assert item1.displayed_date == date(2024, 1, 15)
    assert item1.go_number == "GO/2024/101"

    # Test fetch
    fetch_result = connector.fetch(item1)
    assert fetch_result.http_status == 200
    assert fetch_result.data == pdf_bytes
    assert fetch_result.http_headers["content-type"] == "application/pdf"


def test_ukrd_connector_discovery():
    source = Source(
        id="src_ukrd_documents",
        name="UKRD Documents",
        department_id=DepartmentId.RURAL_DEVELOPMENT.value,
        owner_name="Commissioner RD",
        owner_contact="rd@uk.gov.in",
        written_authority_ref="AUTH-RD-1",
        permitted_domains=["ukrd.uk.gov.in"],
        permitted_path_prefixes=["/documents/"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.WEEKLY.value,
    )

    ukrd_html = """
    <html>
      <body>
        <h2>Rural Development Approved Guidelines</h2>
        <ul>
          <li><a href="/documents/mgnrega-guidelines-2024.pdf">MGNREGA Operational Guidelines 2024</a></li>
          <li><a href="/documents/pmay-g-beneficiaries.pdf">PMAY-G Implementation Norms</a></li>
        </ul>
      </body>
    </html>
    """

    def mock_fetcher(url: str) -> httpx.Response:
        if url.endswith(".pdf"):
            return httpx.Response(
                status_code=200,
                content=b"%PDF-1.4 RD Guidelines",
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            status_code=200,
            text=ukrd_html,
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", url),
        )

    connector = UkrdConnector(fetcher=mock_fetcher)
    items = list(connector.discover(source))
    assert len(items) == 2
    assert items[0].doc_type == DocType.DEPARTMENTAL_DOCUMENT.value
    assert items[0].department_id == DepartmentId.RURAL_DEVELOPMENT.value
    assert "MGNREGA" in items[0].title


def test_ekosh_s3waas_multidepartment_discovery():
    """Verify S3WaaS 3-column table parsing and department propagation for non-Finance departments."""
    source = Source(
        id="src_audit_go",
        name="Audit Directorate Orders",
        department_id=DepartmentId.AUDIT_DIRECTORATE.value,
        owner_name="Director Audit",
        owner_contact="audit@uk.gov.in",
        written_authority_ref="AUTH-AUD-1",
        permitted_domains=["uttarakhandaudit.uk.gov.in", "cdnbbsr.s3waas.gov.in"],
        permitted_path_prefixes=["/document-category/government-orders/", "/"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.WEEKLY.value,
    )

    s3waas_html = """
    <html>
      <body>
        <table>
          <tr><th>Title</th><th>Date</th><th>View / Download</th></tr>
          <tr>
            <td>Notification No.-79/XVIII(3)/2026-03(20)/2021 regarding compliance</td>
            <td>10/06/2016</td>
            <td><a href="https://cdnbbsr.s3waas.gov.in/s3b1/uploads/order.pdf">Accessible Version :View(114 KB)</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    def mock_fetcher(url: str) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            text=s3waas_html,
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", url),
        )

    connector = EkoshTreasuryConnector(fetcher=mock_fetcher)
    items = list(connector.discover(source))
    assert len(items) == 1
    assert items[0].department_id == DepartmentId.AUDIT_DIRECTORATE.value
    assert items[0].go_number == "79/XVIII(3)/2026-03(20)/2021"
    assert items[0].displayed_date == date(2016, 6, 10)


def test_egazette_connector_resilience_and_soft404():
    """Verify EGazetteConnector ignores failing prefixes and flags soft-404 HTML responses."""
    from adam.connectors.egazette import EGazetteConnector
    from adam.connectors.base import DiscoveredItem

    source = Source(
        id="src_uk_egazette",
        name="Gazette Portal",
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        owner_name="Directorate Printing",
        owner_contact="gazette@uk.gov.in",
        written_authority_ref="AUTH-GAZ-1",
        permitted_domains=["uk.gov.in"],
        permitted_path_prefixes=["/hanging-path", "/valid-path", "/"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.WEEKLY.value,
    )

    def mock_fetcher(url: str) -> httpx.Response:
        if "hanging-path" in url:
            raise httpx.TimeoutException("Connection timed out")
        elif "valid-path" in url:
            return httpx.Response(
                status_code=200,
                text="<html><body><a href='/valid-path/gazette_101.pdf'>Extraordinary Gazette 101</a></body></html>",
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", url),
            )
        elif "soft404.pdf" in url:
            return httpx.Response(
                status_code=200,
                text="<html><head><title>404 Not Found</title></head><body>Resource missing</body></html>",
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(status_code=404, request=httpx.Request("GET", url))

    connector = EGazetteConnector(fetcher=mock_fetcher)
    # 1. Discover continues despite timeout on first prefix
    items = list(connector.discover(source))
    assert len(items) == 1
    assert items[0].title == "Extraordinary Gazette 101"

    # 2. Fetch rejects soft-404 HTML disguised as 200
    soft_item = DiscoveredItem(
        source_url="https://uk.gov.in/soft404.pdf",
        title="Bad Item",
        doc_type=DocType.GAZETTE.value,
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
    )
    res = connector.fetch(soft_item)
    assert res.http_status == 404
