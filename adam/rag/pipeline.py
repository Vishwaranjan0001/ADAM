"""End-to-end RAG and citation pipeline for Uttarakhand public records.

Coordinates:
Query Understanding -> Pre-Ranking ACL Filtering -> Hybrid Retrieval ->
Evidence Packet Construction -> Generation & Research Brief -> Citation Validation
"""

from typing import Optional
from sqlalchemy.orm import Session

from adam.rag.evidence import EvidencePacketBuilder
from adam.rag.generator import RagGenerator
from adam.rag.models import UserContext, RagResponse, ParsedQuery
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever


class RagPipeline:
    """Coordinates retrieval, evidence packet assembly, grounded answer generation,
    and citation validation.
    """

    def __init__(self, session: Session):
        self.session = session
        self.retriever = HybridRetriever(session)
        self.packet_builder = EvidencePacketBuilder(session)
        self.generator = RagGenerator()

    def query(
        self,
        question: str,
        user_context: Optional[UserContext] = None,
        top_k: int = 10,
    ) -> RagResponse:
        """Execute full RAG retrieval, synthesis, and citation verification workflow."""
        user = user_context or UserContext()

        # Step 1: Query Understanding & explicit filter extraction
        parsed_query: ParsedQuery = QueryUnderstanding.parse(question)

        # Step 2: Hybrid retrieve with metadata ACL pre-filtering
        retrieved_passages = self.retriever.retrieve(
            parsed_query=parsed_query,
            user_context=user,
            top_k=top_k,
        )

        # Step 3: Build strict evidence packet (3–8 passages) including amending/conflicting records
        packet = self.packet_builder.build_packet(
            query=parsed_query,
            retrieved_passages=retrieved_passages,
            user_context=user,
        )

        # Step 4 & 5: Generate answer and validate citations
        response = self.generator.generate(packet)
        return response
