"""
Query Processing Service
Document chunk retrieval for the document viewer (GET /api/v1/documents/{id}/chunks).
"""

import logging
from typing import Any, Dict, Optional

from ..repositories.audit_repository import SwissAuditRepository
from ..repositories.interfaces import IDocumentRepository, IVectorSearchRepository

logger = logging.getLogger(__name__)


class QueryProcessingService:
    """Service for retrieving a document's chunks (paginated, optionally filtered)"""

    def __init__(
        self,
        doc_repo: IDocumentRepository,
        vector_repo: IVectorSearchRepository,
        audit_repo: SwissAuditRepository,
        ollama_client: Optional[Any] = None,
    ):
        self.doc_repo = doc_repo
        self.vector_repo = vector_repo
        self.audit_repo = audit_repo
        self.ollama_client = ollama_client

    async def get_document_chunks(
        self,
        document_id: int,
        page: int = 1,
        page_size: int = 20,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get chunks for a specific document"""
        try:
            # Verify document exists
            document = await self.doc_repo.get_by_id(document_id)
            if not document:
                raise ValueError(f"Document {document_id} not found")

            # Get chunks from vector repository
            if search_query:
                # Search within document
                chunks_result = await self.vector_repo.search_in_document(
                    document_id=document_id,
                    query=search_query,
                    limit=page_size,
                    offset=(page - 1) * page_size,
                )
            else:
                # Get all chunks for document
                chunks_result = await self.vector_repo.get_document_chunks(
                    document_id=document_id,
                    limit=page_size,
                    offset=(page - 1) * page_size,
                )

            # Format response
            formatted_chunks = []
            for chunk in chunks_result.items:
                formatted_chunks.append(
                    {
                        "chunk_id": getattr(chunk, "chunk_id", None),
                        "content": chunk.content,
                        "start_index": getattr(chunk, "start_index", 0),
                        "end_index": getattr(chunk, "end_index", len(chunk.content)),
                        "metadata": chunk.metadata or {},
                    }
                )

            return {
                "document_id": document_id,
                "chunks": formatted_chunks,
                "page": page,
                "page_size": page_size,
                "total_chunks": chunks_result.total_count,
                "search_query": search_query,
            }

        except Exception as e:
            logger.error(f"Error getting document chunks: {e}")
            raise
