"""Read-only tools and tool sandbox with strict security guardrails.

Per Phase 04 specification:
- 'Tools are read-only: search, open cited source, list authorised collections.
   No web browsing, emailing, editing records, procurement action, or database write tool is available to the model.
   The “agent” is a state machine with max one retrieval and one answer pass; it does not self-expand tasks.'
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from adam.db.models import Document, DocumentVersion, DocumentPage, TextBlock, Source
from adam.rag.acl import AclEnforcer
from adam.rag.models import UserContext, ParsedQuery
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever
from adam.vocabularies import AgentToolName, Classification, DepartmentId, SourceStatus


class ForbiddenToolError(PermissionError):
    """Raised when an attempt is made to call a forbidden, write, or unapproved tool."""
    pass


class ReadOnlyToolRegistry:
    """Registry and execution sandbox enforcing read-only tools and blocking dangerous capabilities."""

    ALLOWED_TOOLS = {
        AgentToolName.SEARCH.value,
        AgentToolName.OPEN_CITED_SOURCE.value,
        AgentToolName.LIST_AUTHORISED_COLLECTIONS.value,
    }

    FORBIDDEN_TOOLS = {
        "web_browse",
        "browse_web",
        "fetch_url",
        "curl",
        "send_email",
        "email",
        "edit_record",
        "update_record",
        "delete_record",
        "write_record",
        "db_write",
        "procure_action",
        "procurement_action",
        "sanction_release",
        "run_bash",
        "execute_command",
        "modify_document",
    }

    @classmethod
    def get_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Return JSON-schema definitions for the 3 authorized read-only tools."""
        return [
            {
                "name": AgentToolName.SEARCH.value,
                "description": "Authorized read-only semantic and full-text search over approved repository chunks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query text"},
                        "department_id": {"type": "string", "description": "Optional department filter"},
                        "doc_type": {"type": "string", "description": "Optional document type filter"},
                        "top_k": {"type": "integer", "description": "Max passages to retrieve (default 5)"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": AgentToolName.OPEN_CITED_SOURCE.value,
                "description": "Read-only inspection of a cited document record, PDF page link, text blocks, and coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "Unique document identifier"},
                        "page_number": {"type": "integer", "description": "Page number to view (1-indexed)"},
                    },
                    "required": ["document_id"],
                },
            },
            {
                "name": AgentToolName.LIST_AUTHORISED_COLLECTIONS.value,
                "description": "List departments, classifications, and approved document collections accessible to current user.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    @classmethod
    def execute(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute tool strictly within read-only bounds with security interception."""
        normalized_name = tool_name.strip().lower()

        # Check explicit forbidden list or whitelist violation
        if normalized_name in cls.FORBIDDEN_TOOLS or normalized_name not in cls.ALLOWED_TOOLS:
            raise ForbiddenToolError(
                f"Security Violation: Tool '{tool_name}' is strictly forbidden. "
                "The ADAM model agent is restricted to read-only tools (search, open_cited_source, "
                "list_authorised_collections). Web browsing, emailing, editing records, procurement action, "
                "and database write tools are strictly unavailable."
            )

        if normalized_name == AgentToolName.SEARCH.value:
            return cls._execute_search(arguments, user_context, session)
        elif normalized_name == AgentToolName.OPEN_CITED_SOURCE.value:
            return cls._execute_open_cited_source(arguments, user_context, session)
        elif normalized_name == AgentToolName.LIST_AUTHORISED_COLLECTIONS.value:
            return cls._execute_list_collections(user_context, session)

        raise ForbiddenToolError(f"Unsupported tool '{tool_name}'.")

    @classmethod
    def _execute_search(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only hybrid search over authorized chunks."""
        query_text = arguments.get("query", "")
        parsed = QueryUnderstanding.parse(query_text)
        if "department_id" in arguments and arguments["department_id"]:
            parsed.department_id = arguments["department_id"]
        if "doc_type" in arguments and arguments["doc_type"]:
            parsed.doc_type = arguments["doc_type"]

        top_k = min(10, max(1, arguments.get("top_k", 5)))
        retriever = HybridRetriever(session)
        passages = retriever.retrieve(parsed, user_context=user_context, top_k=top_k)

        return {
            "query": query_text,
            "total_found": len(passages),
            "passages": [p.to_dict() for p in passages],
            "raw_passages": passages,
        }

    @classmethod
    def _is_authorized_access(
        cls,
        classification: str,
        user_context: UserContext,
        department_id: Optional[str] = None,
        session: Optional[Session] = None,
        document_id: Optional[str] = None,
    ) -> bool:
        """Check if user has clearance to access document or source."""
        if user_context.is_admin() or classification == Classification.PUBLIC.value:
            return True
        if session and document_id:
            return AclEnforcer.is_document_authorized(session, document_id, user_context)
        if classification == Classification.INTERNAL.value:
            if user_context.clearance_level not in (
                Classification.INTERNAL.value,
                Classification.RESTRICTED.value,
                Classification.CONFIDENTIAL.value,
            ):
                return False
            return bool(user_context.department_id and department_id and user_context.department_id == department_id)
        if classification == Classification.RESTRICTED.value:
            if user_context.clearance_level not in (
                Classification.RESTRICTED.value,
                Classification.CONFIDENTIAL.value,
            ):
                return False
            return bool(
                user_context.department_id
                and department_id
                and user_context.department_id == department_id
                and "OFFICER" in [r.upper() for r in user_context.roles]
            )
        if classification == Classification.CONFIDENTIAL.value:
            return False
        return False

    @classmethod
    def _execute_open_cited_source(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only lookup of cited document page and coordinates."""
        doc_id = arguments.get("document_id")
        page_num = arguments.get("page_number", 1)
        version_id = arguments.get("version_id")

        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return {"error": f"Document '{doc_id}' not found in repository."}

        # Verify ACL access with full AclEnforcer grant checks
        if not AclEnforcer.is_document_authorized(session, doc, user_context):
            return {"error": "Access Denied: Document classification exceeds clearance."}

        current_version = None
        if version_id:
            current_version = session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not current_version:
            current_version = (
                session.query(DocumentVersion)
                .filter(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.retrieved_at.desc())
                .first()
            )

        page_record = None
        blocks_data = []
        if current_version:
            page_record = (
                session.query(DocumentPage)
                .filter(
                    DocumentPage.version_id == current_version.id,
                    DocumentPage.page_number == page_num,
                )
                .first()
            )
            if page_record:
                blocks = (
                    session.query(TextBlock)
                    .filter(TextBlock.page_id == page_record.id)
                    .order_by(TextBlock.reading_order)
                    .all()
                )
                for b in blocks[:20]:
                    blocks_data.append({
                        "block_type": b.block_type,
                        "text": b.text,
                        "bbox": b.bbox,
                    })

        pdf_link = ""
        if current_version and current_version.source_url:
            pdf_link = f"{current_version.source_url}#page={page_num}"

        return {
            "document_id": doc.id,
            "title": doc.title,
            "department_id": doc.department_id,
            "classification": doc.classification,
            "source_url": current_version.source_url if current_version else "",
            "pdf_page_link": pdf_link,
            "page_number": page_num,
            "text": page_record.selected_text if page_record else "",
            "blocks": blocks_data,
        }

    @classmethod
    def _execute_list_collections(
        cls,
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only discovery of authorised collections."""
        sources = (
            session.query(Source)
            .filter(Source.status == SourceStatus.APPROVED.value)
            .all()
        )

        accessible_depts = set()
        collections = []
        for s in sources:
            if AclEnforcer.is_source_authorized(session, s, user_context):
                accessible_depts.add(s.department_id)
                collections.append({
                    "source_id": s.id,
                    "name": s.name,
                    "department_id": s.department_id,
                    "classification": s.access_classification,
                    "refresh_cadence": s.refresh_cadence,
                })

        return {
            "user_id": user_context.user_id,
            "clearance_level": user_context.clearance_level,
            "accessible_departments": sorted(list(accessible_depts)),
            "total_accessible_collections": len(collections),
            "collections": collections,
        }
