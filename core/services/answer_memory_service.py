"""
Answer Memory Service

Promotes a thumbs-up rated tutor answer (from the interaction log) into a
small "virtual document" that's embedded and added to the live vector
index exactly like an uploaded document's chunks - so future questions,
from any learner in any session, can retrieve it through the same
similarity search used for the curriculum documents. Demoting (thumbs-down
or un-rating) removes it again.

Deliberately global rather than session-scoped: the whole point is that
one learner's good answer can help a different learner later. Contrast
with SimpleRAGService's conversation memory (core/services/simple_rag_service.py),
which is scoped per session on purpose so one learner's chat can't leak
into another's.
"""

import logging
from typing import List

from ..repositories.models import Document, DocumentStatus, Embedding
from ..services.simple_rag_service import load_language_strings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Same model used for document chunks


class AnswerMemoryService:
    """Promotes/demotes rated tutor answers to/from the searchable index."""

    def __init__(self, doc_repo, vector_repo):
        self.doc_repo = doc_repo
        self.vector_repo = vector_repo

    async def promote(
        self, interaction_id: int, question_text: str, answer_text: str
    ) -> int:
        """Embed a rated-good Q&A pair and add it to the live vector index.

        Returns the id of the virtual document created for it.
        """
        strings = load_language_strings()
        clean_answer = answer_text.split(f"\n\n{strings['sources_label']}:")[0]
        text_to_embed = f"Q: {question_text}\nA: {clean_answer}"

        document = await self.doc_repo.create(
            Document(
                filename=f"{self.doc_repo.TUTOR_ANSWER_FILENAME_PREFIX}{interaction_id}",
                original_filename="Tutor's earlier answer (rated helpful)",
                file_path="",
                content_type="text/tutor-answer",
                file_size=len(text_to_embed),
                status=DocumentStatus.COMPLETED,
                uploader="system:rating",
                description=(
                    f"Auto-added from a thumbs-up rating on interaction log #{interaction_id}"
                ),
                tags=["tutor_answer"],
                metadata={
                    "source_type": "tutor_answer",
                    "interaction_log_id": interaction_id,
                },
            )
        )

        chunk_id = await self.doc_repo.create_chunk(document.id, 0, text_to_embed)

        embedding_vector = self._embed(text_to_embed)
        embedding_id = await self.doc_repo.create_embedding(
            chunk_id, document.id, embedding_vector, EMBEDDING_MODEL
        )

        await self.vector_repo.add_to_index(
            [
                Embedding(
                    id=embedding_id,
                    chunk_id=chunk_id,
                    document_id=document.id,
                    embedding_vector=embedding_vector,
                    embedding_model=EMBEDDING_MODEL,
                    vector_dimension=len(embedding_vector),
                )
            ]
        )

        logger.info(
            f"Promoted interaction {interaction_id} to answer memory as document {document.id}"
        )
        return document.id

    async def demote(self, promoted_document_id: int) -> None:
        """Remove a previously-promoted answer from the index and delete it.

        Chunks/embeddings rows cascade-delete with the document (see the
        ON DELETE CASCADE foreign keys in sqlite_repository.py's schema),
        but the live in-memory vector index doesn't know about that, so its
        embedding ids must be removed explicitly first.
        """
        embedding_ids = await self.doc_repo.get_embedding_ids_for_document(
            promoted_document_id
        )
        if embedding_ids:
            await self.vector_repo.remove_from_index(embedding_ids)

        await self.doc_repo.delete(promoted_document_id)
        logger.info(f"Demoted answer-memory document {promoted_document_id}")

    def _embed(self, text: str) -> List[float]:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBEDDING_MODEL)
        return model.encode([text], convert_to_numpy=True)[0].tolist()
