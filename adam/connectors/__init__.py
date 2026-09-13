"""Connectors for Uttarakhand government portals and departmental records."""

from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.connectors.ekosh import EkoshTreasuryConnector
from adam.connectors.ukrd import UkrdConnector
from adam.connectors.itda import ITDASampleBatchConnector
from adam.connectors.egazette import EGazetteConnector

__all__ = [
    "BaseConnector",
    "DiscoveredItem",
    "FetchResult",
    "EkoshTreasuryConnector",
    "UkrdConnector",
    "ITDASampleBatchConnector",
    "EGazetteConnector",
]
