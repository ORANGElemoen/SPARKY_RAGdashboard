"""
Simple Professional RAG Service
Clean, maintainable RAG system with AI answers only
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .response_cache import ResponseCache

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE_STRINGS = {
    "name": "English",
    "prompt_template": (
        "You are a friendly, encouraging STEM tutor for children. Use the documents "
        "below to help answer the question in a simple, fun, and engaging way, with "
        "everyday examples a child can relate to. If the documents don't fully cover "
        "the question, use your own knowledge to fill the gaps in the same fun, "
        "encouraging style.\n\n"
        "DOCUMENTS:\n{context}\n\nQUESTION: {query}\n\n"
        "ANSWER (simple, fun, and encouraging, for a child):"
    ),
    "general_prompt_template": (
        "You are a friendly, encouraging STEM tutor for children. Answer the "
        "question in a simple, fun, and engaging way using your own knowledge. "
        "Explain science, technology, engineering, mathematics, biology, or "
        "electricity concepts with simple language and relatable, everyday "
        "examples. Encourage curiosity and make learning exciting.\n\n"
        "QUESTION: {query}\n\n"
        "ANSWER (simple, fun, and encouraging, for a child):"
    ),
    "no_answer_generated": "No answer could be generated.",
    "answer_generation_error": "An error occurred while generating the answer.",
    "voice_retry_prompt": "I didn't quite catch that. Can you try asking again?",
    "voice_error_prompt": "Sorry, something went wrong while I was thinking. Can you try again?",
    "sources_label": "Sources",
    "source_line": "[Source {id}] Document {document_id} - {url}",
    "truncated_notice": "[...truncated for performance...]",
}


def load_language_strings() -> Dict[str, str]:
    """Load the active language's prompt/response strings.

    Falls back to English defaults if config is missing or malformed,
    so a bad language config never breaks query answering.
    """
    try:
        lang_config_path = Path("config/language_config.yaml")
        current_language = "en"
        if lang_config_path.exists():
            with open(lang_config_path, "r", encoding="utf-8") as f:
                lang_config = yaml.safe_load(f) or {}
            current_language = lang_config.get("current_language", "en")

        strings_path = Path(f"config/languages/{current_language}.yaml")
        if strings_path.exists():
            with open(strings_path, "r", encoding="utf-8") as f:
                strings = yaml.safe_load(f) or {}
            merged = dict(DEFAULT_LANGUAGE_STRINGS)
            merged.update(strings)
            return merged

        logger.warning(
            f"Language file for '{current_language}' not found, using English defaults"
        )
    except Exception as e:
        logger.warning(f"Failed to load language config, using English defaults: {e}")

    return dict(DEFAULT_LANGUAGE_STRINGS)


_SENTENCE_END_CHARS = ".!?…\"'”)"


def _trim_to_complete_sentence(text: str) -> str:
    """Trim a truncated LLM response back to its last complete sentence.

    Generation is capped by max_tokens, so long answers can be cut off
    mid-sentence. If that happens, drop the trailing fragment rather than
    showing the child half a sentence - but only if doing so keeps at
    least half the answer, otherwise leave it as-is.
    """
    text = text.rstrip()
    if not text or text[-1] in _SENTENCE_END_CHARS:
        return text

    last_end = max(text.rfind(c) for c in ".!?")
    if last_end != -1 and last_end + 1 >= len(text) * 0.5:
        return text[: last_end + 1]

    return text


class RAGConfig:
    """Simple configuration with environment variables"""

    def __init__(self):
        # Core settings - simple and clear
        self.similarity_threshold = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.3"))
        self.max_results = int(os.getenv("RAG_MAX_RESULTS", "3"))
        self.require_sources = bool(
            os.getenv("RAG_REQUIRE_SOURCES", "true").lower() == "true"
        )
        self.max_query_length = int(os.getenv("RAG_MAX_QUERY_LENGTH", "500"))

        logger.info(
            f"RAG Config: threshold={self.similarity_threshold}, max_results={self.max_results}, require_sources={self.require_sources}"
        )


class SimpleRAGService:
    """Clean, professional RAG service - AI answers only"""

    def __init__(self, vector_repo, llm_client, audit_repo=None):
        self.vector_repo = vector_repo
        self.llm_client = llm_client
        self.audit_repo = audit_repo
        self.config = RAGConfig()
        self.cache = ResponseCache()  # Add response caching for performance

        logger.info("Simple RAG Service initialized with caching")

    async def answer_query(self, query: str) -> Dict[str, Any]:
        """
        Process query and return AI answer with sources

        Args:
            query: User question

        Returns:
            Dict with answer, sources, and metadata
        """
        try:
            # 1. Validate input
            if not self._is_valid_query(query):
                return self._error_response("Invalid query")

            # 2. Search for relevant documents
            search_results = await self._search_documents(query)

            # 3. Generate AI answer (grounded in documents if any were found,
            # otherwise the tutor falls back to its own general knowledge)
            ai_response = await self._generate_answer(query, search_results)

            # 4. Format response
            response = {
                "answer": ai_response["text"],
                "spoken_answer": ai_response.get("spoken_text", ai_response["text"]),
                "sources": ai_response["sources"],
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "confidence": ai_response["confidence"],
            }

            # 5. Audit log
            if self.audit_repo:
                self._audit_successful_query(query, response)

            return response

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return self._error_response(f"Processing failed: {str(e)}")

    def _is_valid_query(self, query: str) -> bool:
        """Simple query validation"""
        if not query or len(query.strip()) < 3:
            return False
        if len(query) > self.config.max_query_length:
            return False
        return True

    async def _search_documents(self, query: str) -> List[Dict[str, Any]]:
        """Search for relevant documents"""
        try:
            # Get search results
            search_results = await self.vector_repo.search_similar_text(
                query=query,
                limit=self.config.max_results,
                threshold=0.01,  # Very low threshold, we'll filter later
            )

            if not search_results.items:
                return []

            # Filter by threshold and format
            relevant_results = []
            for item in search_results.items:
                similarity = item.metadata.get("similarity_score", 0.0)

                if similarity >= self.config.similarity_threshold:
                    relevant_results.append(
                        {
                            "text": item.text_content,
                            "document_id": item.document_id,
                            "similarity": similarity,
                            "chunk_id": item.id,
                        }
                    )

            logger.info(
                f"Found {len(relevant_results)} relevant documents (threshold: {self.config.similarity_threshold})"
            )
            return relevant_results

        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []

    async def _generate_answer(
        self, query: str, search_results: List[Dict]
    ) -> Dict[str, Any]:
        """Generate AI answer from search results"""
        strings = load_language_strings()
        try:
            if not search_results:
                # No relevant documents: fall back to the tutor's own
                # general knowledge instead of refusing to answer
                return await self._generate_general_answer(query, strings)

            # Prepare context from the actual retrieved document chunks
            context_parts = []
            sources = []

            for i, result in enumerate(search_results, 1):
                context_parts.append(f"[{i}]: {result['text']}")
                sources.append(
                    {
                        "id": i,
                        "document_id": result["document_id"],
                        "similarity": result["similarity"],
                        "download_url": f"/api/v1/documents/{result['document_id']}/download",
                    }
                )

            context = "\n\n".join(context_parts)

            # Truncate context if too long for performance
            max_context_length = 2000  # Increased to provide meaningful context
            if len(context) > max_context_length:
                context = (
                    context[:max_context_length] + "\n\n" + strings["truncated_notice"]
                )

            # TEMPORARILY DISABLE CACHE to debug
            # cached_response = self.cache.get(query, context)
            # if cached_response:
            #     return cached_response

            logger.debug(f"Context for prompt: {context[:800]}...")

            prompt = strings["prompt_template"].format(context=context, query=query)

            response = self.llm_client.generate_answer(
                query=prompt,
                context="",  # Context is already embedded in the prompt
                max_tokens=600,  # Enough room to finish a full explanation
                temperature=0.4,  # Some room for a fun, engaging tone
                max_retries=1,  # Single attempt only
                is_complete_prompt=True,
            )

            answer_text = response if response else strings["no_answer_generated"]
            answer_text = _trim_to_complete_sentence(answer_text)
            spoken_text = answer_text  # Citations below are for display, not speech

            # Add source footer
            if sources and self.config.require_sources:
                source_footer = f"\n\n{strings['sources_label']}:\n" + "\n".join(
                    [
                        strings["source_line"].format(
                            id=s["id"],
                            document_id=s["document_id"],
                            url=s["download_url"],
                        )
                        for s in sources
                    ]
                )
                answer_text += source_footer

            result = {
                "text": answer_text,
                "spoken_text": spoken_text,
                "sources": sources,
                "confidence": max(r["similarity"] for r in search_results),
                "debug_context": (
                    context[:500] + "..." if len(context) > 500 else context
                ),
                "debug_prompt": prompt[:500] + "..." if len(prompt) > 500 else prompt,
            }

            # Cache the result for future queries
            self.cache.set(query, context, result)

            return result

        except Exception as e:
            logger.error(f"AI answer generation failed: {e}")
            return {
                "text": strings["answer_generation_error"],
                "spoken_text": strings["answer_generation_error"],
                "sources": [],
                "confidence": 0.0,
            }

    async def _generate_general_answer(
        self, query: str, strings: Dict[str, str]
    ) -> Dict[str, Any]:
        """Answer using the tutor's own knowledge when no uploaded document is relevant"""
        try:
            prompt = strings["general_prompt_template"].format(query=query)

            response = self.llm_client.generate_answer(
                query=prompt,
                context="",
                max_tokens=600,  # Enough room to finish a full explanation
                temperature=0.6,  # More creative/exploratory for open-ended teaching
                max_retries=1,
                is_complete_prompt=True,
            )

            answer_text = response if response else strings["no_answer_generated"]
            answer_text = _trim_to_complete_sentence(answer_text)

            return {
                "text": answer_text,
                "spoken_text": answer_text,
                "sources": [],
                "confidence": 0.0,
            }

        except Exception as e:
            logger.error(f"General answer generation failed: {e}")
            return {
                "text": strings["answer_generation_error"],
                "spoken_text": strings["answer_generation_error"],
                "sources": [],
                "confidence": 0.0,
            }

    def _error_response(self, message: str) -> Dict[str, Any]:
        """Response for errors"""
        return {"error": message, "timestamp": datetime.utcnow().isoformat()}

    def _audit_successful_query(self, query: str, response: Dict[str, Any]):
        """Simple audit logging"""
        try:
            if self.audit_repo:
                # Simple synchronous audit logging (non-blocking)
                logger.info(
                    f"Query audit: query_length={len(query)}, sources={len(response.get('sources', []))}, confidence={response.get('confidence', 0.0)}"
                )
        except Exception as e:
            logger.warning(f"Audit logging failed: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        return {
            "service": "Simple RAG Service",
            "mode": "AI answers only",
            "config": {
                "similarity_threshold": self.config.similarity_threshold,
                "max_results": self.config.max_results,
                "require_sources": self.config.require_sources,
                "max_query_length": self.config.max_query_length,
            },
            "healthy": True,
        }
