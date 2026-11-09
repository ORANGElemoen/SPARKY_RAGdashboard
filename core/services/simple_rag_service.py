"""
Simple Professional RAG Service
Clean, maintainable RAG system with AI answers only
"""

import asyncio
import logging
import os
import random
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .maths_helper import maths_note
from .response_cache import ResponseCache

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE_STRINGS = {
    "name": "English",
    "prompt_template": (
        "Your name is Sparky, a friendly little robot. For any experiment or "
        "activity, always tell the child to do it with a grown-up, and never "
        "suggest eating or tasting anything used in an experiment. "
        "You are a friendly, encouraging STEM tutor for children. Use the documents "
        "below to help answer the question in a simple, fun, and engaging way, with "
        "everyday examples a child can relate to. If the documents don't fully cover "
        "the question, use your own knowledge to fill the gaps in the same fun, "
        "encouraging style.\n\n"
        "DOCUMENTS:\n{context}\n\n{conversation_history}QUESTION: {query}\n\n"
        "ANSWER (simple, fun, and encouraging, for a child):"
    ),
    "general_prompt_template": (
        "Your name is Sparky, a friendly little robot. For any experiment or "
        "activity, always tell the child to do it with a grown-up, and never "
        "suggest eating or tasting anything used in an experiment. "
        "You are a friendly, encouraging STEM tutor for children. Answer the "
        "question in a simple, fun, and engaging way using your own knowledge. "
        "Explain science, technology, engineering, mathematics, biology, or "
        "electricity concepts with simple language and relatable, everyday "
        "examples. Encourage curiosity and make learning exciting.\n\n"
        "{conversation_history}QUESTION: {query}\n\n"
        "ANSWER (simple, fun, and encouraging, for a child):"
    ),
    "no_answer_generated": "No answer could be generated.",
    "answer_generation_error": "An error occurred while generating the answer.",
    "voice_retry_prompt": "I didn't quite catch that. Can you try asking again?",
    "voice_error_prompt": "Sorry, something went wrong while I was thinking. Can you try again?",
    "sources_label": "Sources",
    "source_line": "[Source {id}] Document {document_id} - {url}",
    "truncated_notice": "[...truncated for performance...]",
    "conversation_history_label": "CONVERSATION SO FAR",
    "conversation_learner_label": "Learner",
    "conversation_tutor_label": "Sparky",
    "speech_fractions": {
        "1/2": "one half", "1/3": "one third", "2/3": "two thirds",
        "1/4": "a quarter", "3/4": "three quarters",
    },
    "speech_fraction_template": "{numerator} over {denominator}",
    "grade_instruction": (
        "The child is in Grade {grade}, about {age} years old. Use words, ideas and "
        "examples a child of that age knows: keep it very simple for young children, "
        "and go deeper with proper science words for older ones. Do not mention their "
        "grade or age."
    ),
    "refusal_pattern": r"I (cannot|can't|can not|won't|am not able to|'m not able to) (provide|help(?! but)|assist|give|offer|share|answer|fulfil)",
    "safety_redirect": (
        "That sounds like something that could be really dangerous, so please don't "
        "try it, and talk to a grown-up you trust about it. There's lots of exciting "
        "science we can explore safely together. What else are you curious about?"
    ),
    "must_say_marker": "Sparky always says:",
    "stt_hotwords": "Sparky grass science experiment battery lemon gravity",
    # What Sparky says first, by the kind of message (see MESSAGE_TYPE_PROMPT); voice only
    "openers": {
        "question": ["Good question!", "Ooh, great question!", "Hmm, let me think!"],
        "answer": ["Okay, let's see!", "Hmm, let's see!"],
        "statement": [],
    },
    # Added under the child's message in the prompt, by the kind of message
    "message_type_notes": {
        "question": "",
        "answer": (
            "(The child is replying to what you asked last. If you asked a quiz question with a "
            "right answer, tell them kindly whether they are right and why. If you asked what "
            "they want, like whether to hear more, just do what they chose.)"
        ),
        "statement": (
            "(The child is telling you something, not asking a question. Reply warmly to what "
            "they said.)"
        ),
    },
    "opener_note": "(You have already said \"{opener}\" out loud. Carry straight on without repeating it.)",
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
            # Lesson phrases not yet translated into this language come from English, so
            # lessons still work (in English) instead of quietly not starting at all
            english = Path("config/languages/en.yaml")
            if current_language != "en" and english.exists():
                with open(english, "r", encoding="utf-8") as f:
                    merged.update({k: v for k, v in (yaml.safe_load(f) or {}).items() if k.startswith("lesson_")})
            merged.update(strings)
            # Not a real language string - used to keep the response cache key
            # scoped to the language active when the answer was generated, so
            # switching languages can never surface a stale answer written in
            # a different one (see ResponseCache._get_cache_key).
            merged["_language_code"] = current_language
            return merged

        logger.warning(
            f"Language file for '{current_language}' not found, using English defaults"
        )
    except Exception as e:
        logger.warning(f"Failed to load language config, using English defaults: {e}")

    defaults = dict(DEFAULT_LANGUAGE_STRINGS)
    defaults["_language_code"] = "en"
    return defaults


LEARNER_CONFIG_PATH = Path("config/learner_config.yaml")


def load_learner_grade() -> str:
    """Learner grade set in the admin dashboard ("R", "1".."12"), or "" if unset."""
    try:
        if LEARNER_CONFIG_PATH.exists():
            with open(LEARNER_CONFIG_PATH, "r", encoding="utf-8") as f:
                return str((yaml.safe_load(f) or {}).get("grade") or "")
    except Exception as e:
        logger.warning(f"Failed to read learner config, ignoring grade: {e}")
    return ""


def grade_instruction(strings: Dict[str, str]) -> str:
    """The language file's grade sentence for the configured grade, or ""."""
    grade = load_learner_grade()
    if not (grade.upper() == "R" or grade.isdigit()):
        return ""  # unset, or a hand-edited config value we can't use
    age = 5 if grade.upper() == "R" else int(grade) + 6  # Grade R is the year children turn 6
    return strings.get("grade_instruction", "").format(grade=grade, age=age)


def _soften_refusal(text: str, strings: Dict[str, str]) -> str:
    """Replace the LLM's canned safety refusal with a warm, kid-friendly one.

    llama3.2's built-in safety training answers some risky questions with a
    flat "I cannot provide information on..." that the prompt can't override.
    Sparky shouldn't just refuse (see CLAUDE.md), so swap in the language
    file's safety_redirect. The English pattern is always checked too, since
    the model often refuses in English whatever the prompt language.
    """
    for pattern in {strings.get("refusal_pattern"), DEFAULT_LANGUAGE_STRINGS["refusal_pattern"]}:
        if pattern and re.match(pattern, text.strip(), re.IGNORECASE):
            return strings["safety_redirect"]
    return text


# How much retrieved text the LLM reads per answer (more = slower answers on a small model)
MAX_CONTEXT_CHARS = 2000
# A result this close to the best score counts as "about as relevant"
CLOSE_SIMILARITY = 0.15  # 0.1 let a 0.65 book chunk beat the 0.55 red cabbage sheet


def _whole_results_first(results: List[Dict]) -> List[Dict]:
    """Put results that fit in the context whole (a short experiment sheet, a saved good answer)
    ahead of long book chunks that would be cut off - if they are about as relevant as the best.

    Otherwise one ~3000-character book chunk that scored slightly higher fills the whole context
    and the sheet written for exactly that question never reaches the LLM.
    """
    if not results:
        return results
    best = max(r["similarity"] for r in results)

    def fits(r):
        return len(r["text"]) <= MAX_CONTEXT_CHARS and r["similarity"] >= best - CLOSE_SIMILARITY

    return sorted(results, key=lambda r: not fits(r))  # stable: score order kept within each group


def _must_say(text: str, marker: Optional[str]) -> Optional[str]:
    """The sentence after the language's must-say marker in a document ("Sparky always says:
    Never drink the water from your filter!"), or None. The small LLM often drops a sheet's most
    important safety line from a 60-word answer, so the tutor adds this one itself."""
    if not marker or marker not in text:
        return None
    rest = " ".join(text.split(marker, 1)[1].split())   # PDF text breaks lines anywhere
    found = re.match(r"(.+?[.!?])(\s|$)", rest)
    return found.group(1) if found else None


def _is_repeated_opener(sentence: str, strings: Dict[str, Any]) -> bool:
    """True if the model began with its own "Good question!" after Sparky already said an opener.
    Matches the language file's openers, and its repeated_opener_pattern for other wordings."""
    def plain(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())
    said = plain(sentence)
    if any(said == plain(o) for kind in (strings.get("openers") or {}).values() for o in kind or []):
        return True
    pattern = strings.get("repeated_opener_pattern")
    try:
        return bool(pattern and re.fullmatch(pattern, said))
    except re.error:
        return False


def _strip_repeated_opener(text: str, strings: Dict[str, Any]) -> str:
    sentences = _split_spoken(text)
    while sentences and _is_repeated_opener(sentences[0], strings):
        sentences.pop(0)
    return " ".join(sentences)


def _add_must_say(answer: str, must_say: str) -> str:
    """Add a safety line before the closing question, so the answer still ends on the question."""
    sentences = _SENTENCE_RE.split(answer.strip())
    if sentences[-1].endswith("?"):
        return " ".join([*sentences[:-1], must_say, sentences[-1]])
    return f"{answer} {must_say}"


# Internal check, never shown to the child, so it stays in English whatever language they speak.
FOLLOW_UP_CHECK_PROMPT = """A child is talking to a science tutor. Decide if the child's new message continues the same topic or starts a different one.

Tutor was asked: {question}
Tutor answered: {answer}
Child's new message: {message}

Reply SAME if the message only makes sense with the earlier conversation, or is about the same activity (for example asking for help, the next step, a repeat, or why it happened).
Reply NEW if it asks about something else, even a science topic.
Reply with one word: SAME or NEW."""

# What kind of message the child said, so Sparky doesn't say "Good question!" to an answer
MESSAGE_TYPES = ("question", "answer", "statement")
MESSAGE_TYPE_PROMPT = """A child is talking to Sparky, a science tutor robot. Decide what kind of message the child just said.

Sparky's last reply: {last_reply}
Child's message: {message}

Reply ANSWER if Sparky's last reply asked something and the child is replying to it: a guess, a number, a choice, yes or no, "tell me more", or "I don't know".
Reply QUESTION if the child asks Sparky a new question of their own.
Reply STATEMENT if the child is telling Sparky something, for example their name, what happened or how they feel.
Reply with one word: ANSWER, QUESTION or STATEMENT."""


# Sentence boundary for spoken answers: end punctuation followed by space, so "3.5" stays whole.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_spoken(text: str) -> List[str]:
    return [x.strip() for x in _SENTENCE_RE.split(text.strip()) if x.strip()]


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
        self.similarity_threshold = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.45"))
        self.max_results = int(os.getenv("RAG_MAX_RESULTS", "3"))
        self.require_sources = bool(
            os.getenv("RAG_REQUIRE_SOURCES", "true").lower() == "true"
        )
        self.max_query_length = int(os.getenv("RAG_MAX_QUERY_LENGTH", "500"))
        # Sparky remembers the current conversation, up to this many prior turns.
        # Ten turns measured about 3,100 prompt tokens, within OLLAMA_NUM_CTX.
        self.max_conversation_turns = int(
            os.getenv("RAG_MAX_CONVERSATION_TURNS", "10")
        )
        # A pause longer than this ends a conversation. A board keeps one session for life, so
        # the next question after a long pause is probably a new conversation, maybe with a
        # different child. Keeping old turns also let the model repeat an old mistake.
        self.conversation_gap_minutes = int(
            os.getenv("RAG_CONVERSATION_GAP_MINUTES", "60")
        )

        logger.info(
            f"RAG Config: threshold={self.similarity_threshold}, max_results={self.max_results}, require_sources={self.require_sources}"
        )


class SimpleRAGService:
    """Clean, professional RAG service - AI answers only"""

    def __init__(self, vector_repo, llm_client, interaction_log_repo=None, lessons=None):
        self.vector_repo = vector_repo
        self.llm_client = llm_client
        self.interaction_log_repo = interaction_log_repo
        self.lessons = lessons  # LessonService: guided lessons, if set up
        self.config = RAGConfig()
        self.cache = ResponseCache()  # Add response caching for performance

        logger.info("Simple RAG Service initialized with caching")

    async def _lesson_turn(self, query: str, session_id: Optional[str], device_id: Optional[int]):
        """The lesson's part of this message (see LessonService), or None if it isn't about a lesson."""
        if not self.lessons or not session_id:
            return None
        try:
            return await self.lessons.handle(query, session_id, device_id,
                                             idle_minutes=self.config.conversation_gap_minutes)
        except Exception as e:
            logger.error(f"Lesson handling failed, answering normally: {e}")
            return None

    @staticmethod
    def _lesson_response(query: str, lesson) -> Dict[str, Any]:
        """A lesson's next part, said as the teacher approved it (so no sources or match score)."""
        return {"answer": lesson.reply, "spoken_answer": lesson.reply, "message_type": "lesson", "sources": [],
                "timestamp": datetime.utcnow().isoformat(), "query": query, "confidence": 1.0,
                "used_general_knowledge": False, "lesson_progress_id": lesson.progress_id}

    async def answer_query(
        self,
        query: str,
        query_type: str = "text",
        session_id: Optional[str] = None,
        device_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process query and return AI answer with sources

        Args:
            query: User question
            query_type: "text" or "voice" - which endpoint this came through,
                recorded in the interaction log
            session_id: Identifies one learner's conversation (one browser
                tab or one ESP32 device). Scopes both which prior turns are
                pulled in as follow-up context and which turns this one is
                logged against - never shared across sessions, so one
                learner's question can't leak into another's follow-up.
            device_id: Registered hardware device this came from, if any
                (see DeviceRepository) - recorded on the interaction log
                only, has no effect on retrieval/memory scoping.

        Returns:
            Dict with answer, sources, and metadata
        """
        try:
            # 1. Validate input
            if not self._is_valid_query(query):
                return self._error_response("Invalid query")

            # 2. Pull in recent turns from this same session only, so
            # follow-ups like "how does that work?" resolve correctly
            conversation_history = []
            if session_id and self.interaction_log_repo:
                conversation_history = await self.interaction_log_repo.get_recent_turns(
                    session_id, limit=self.config.max_conversation_turns,
                    max_gap_minutes=self.config.conversation_gap_minutes,
                )

            # A guided lesson's next part is said as written, without the model
            lesson = await self._lesson_turn(query, session_id, device_id)
            if lesson and lesson.reply:
                response = self._lesson_response(query, lesson)
                if self.interaction_log_repo:
                    asyncio.create_task(self._log_interaction(query, response, query_type, session_id, device_id))
                return response

            # 3. Search for relevant documents, and work out what kind of message this is
            search_results, message_type, opener = await self._understand(
                query, conversation_history, spoken=query_type == "voice"
            )

            # 4. Generate AI answer (grounded in documents if any were found,
            # otherwise the tutor falls back to its own general knowledge)
            ai_response = await self._generate_answer(
                query, search_results, conversation_history, message_type, opener
            )
            if opener:
                ai_response = {**ai_response, "text": f"{opener} {ai_response['text']}",
                               "spoken_text": f"{opener} {ai_response.get('spoken_text', ai_response['text'])}"}
            if lesson and lesson.after:  # a question in the middle of a lesson: then how to carry on
                ai_response = {**ai_response, "text": f"{ai_response['text']} {lesson.after}",
                               "spoken_text": f"{ai_response.get('spoken_text', ai_response['text'])} {lesson.after}"}

            # 5. Format response
            response = {
                "answer": ai_response["text"],
                "spoken_answer": ai_response.get("spoken_text", ai_response["text"]),
                "message_type": message_type,
                "sources": ai_response["sources"],
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "confidence": ai_response["confidence"],
                "used_general_knowledge": ai_response.get(
                    "used_general_knowledge", False
                ),
                "lesson_progress_id": lesson.progress_id if lesson else None,
            }

            # 6. Interaction log - fire-and-forget, must never slow down or
            # break the response already being returned to the user
            if self.interaction_log_repo:
                asyncio.create_task(
                    self._log_interaction(
                        query, response, query_type, session_id, device_id
                    )
                )

            return response

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return self._error_response(f"Processing failed: {str(e)}")

    async def _log_interaction(
        self,
        query: str,
        response: Dict[str, Any],
        query_type: str,
        session_id: Optional[str],
        device_id: Optional[int] = None,
    ) -> None:
        """Persist the exchange to the interaction log. Swallows all errors."""
        try:
            await self.interaction_log_repo.log_interaction(
                query_type=query_type,
                question_text=query,
                answer_text=response.get("answer", ""),
                used_general_knowledge=response.get("used_general_knowledge", False),
                confidence=response.get("confidence", 0.0),
                sources=response.get("sources", []),
                session_id=session_id,
                device_id=device_id,
                lesson_progress_id=response.get("lesson_progress_id"),
                message_type=response.get("message_type"),
            )
        except Exception as e:
            logger.warning(f"Interaction logging failed: {e}")

    def _build_conversation_history_block(
        self, turns: List[Dict[str, str]], strings: Dict[str, str]
    ) -> str:
        """Render prior turns as a prompt block, or "" if there are none.

        Strips the source-citation footer off prior answers (matched via
        the language file's own sources_label, so this stays language-
        agnostic) - those citations are for on-screen display, not useful
        as conversation context and would just eat into the prompt budget.
        """
        if not turns:
            return ""

        # Keep the start (the topic) AND the end: Sparky's answers end with a
        # question for the child, and cutting it off made follow-up answers
        # like "a zebra!" meaningless to the model.
        max_answer_chars, keep_head, keep_tail = 700, 250, 400
        sources_marker = f"\n\n{strings['sources_label']}:"
        lines = [f"{strings['conversation_history_label']}:"]
        for turn in turns:
            answer = turn["answer_text"].split(sources_marker)[0]
            if len(answer) > max_answer_chars:
                answer = answer[:keep_head] + strings["truncated_notice"] + answer[-keep_tail:]
            lines.append(f"{strings['conversation_learner_label']}: {turn['question_text']}")
            lines.append(f"{strings['conversation_tutor_label']}: {answer}")

        return "\n".join(lines) + "\n\n"

    def _is_valid_query(self, query: str) -> bool:
        """Simple query validation"""
        # Any non-empty text is valid: children answer Sparky's own questions
        # with "No", "8" or "Ja", which a minimum length would reject.
        if not query or not query.strip():
            return False
        if len(query) > self.config.max_query_length:
            return False
        return True

    async def _search_with_history(
        self, query: str, history: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, Any]]:
        """Search for the question; if nothing matches and it's part of a conversation, retry
        with each earlier question (newest first). A follow-up like "It's not lighting up"
        matches no document on its own, but "make a lemon battery ... It's not lighting up" does."""
        results = await self._search_documents(query)
        if results or not history or not await self._is_follow_up(query, history[-1]):
            return results
        for turn in reversed(history):
            results = await self._search_documents(f"{turn['question_text']} {query}")
            if results:
                break
        return results

    async def _is_follow_up(self, query: str, last_turn: Dict[str, str]) -> bool:
        """Ask the model whether this message continues the last turn. Without this check, adding
        the earlier question to the search makes any new question ("Why is the sky blue?") match
        the earlier question's document. Similarity scores can't tell the two apart: a vague
        "Why does that happen?" scores about the same as an unrelated "What do lions eat?"."""
        sources_marker = f"\n\n{load_language_strings()['sources_label']}:"
        prompt = FOLLOW_UP_CHECK_PROMPT.format(
            question=last_turn["question_text"],
            answer=(last_turn.get("answer_text") or "").split(sources_marker)[0],
            message=query,
        )
        try:
            reply = await asyncio.to_thread(
                self.llm_client.generate_answer, query=prompt, context="", max_tokens=6,
                temperature=0.0, max_retries=1, is_complete_prompt=True,
            )
        except Exception as e:
            logger.warning(f"Follow-up check failed, treating the message as a new question: {e}")
            return False
        # On doubt, answer from general knowledge with the conversation in the prompt: that's
        # better than a wrong document steering the answer and being cited as its source.
        return (reply or "").strip().upper().startswith("SAME")

    async def _classify_message(self, query: str, history: Optional[List[Dict[str, str]]]) -> str:
        """Ask the model whether the child asked a question, answered Sparky's question or just
        told Sparky something. One of MESSAGE_TYPES. If the model can't say, punctuation decides."""
        sources_marker = f"\n\n{load_language_strings()['sources_label']}:"
        last_reply = ""
        if history:
            last_reply = (history[-1].get("answer_text") or "").split(sources_marker)[0].strip()
        prompt = MESSAGE_TYPE_PROMPT.format(
            last_reply=last_reply[-400:] or "(nothing yet: this is the start of the conversation)",
            message=query,
        )
        try:
            reply = await asyncio.to_thread(
                self.llm_client.generate_answer, query=prompt, context="", max_tokens=4,
                temperature=0.0, max_retries=1, is_complete_prompt=True,
            )
            word = (reply or "").strip().upper()
            for kind in MESSAGE_TYPES:
                if word.startswith(kind.upper()):
                    return kind
            logger.info(f"Unclear message type {word[:20]!r}, guessing from punctuation")
        except Exception as e:
            logger.warning(f"Message type check failed, guessing from punctuation: {e}")
        if query.strip().endswith("?"):
            return "question"
        return "answer" if last_reply.endswith("?") else "statement"

    async def _understand(self, query: str, history: List[Dict[str, str]], spoken: bool):
        """Search the sheets and classify the message at the same time. Returns
        (search_results, message_type, opener); the opener is only for spoken answers."""
        search_results, message_type = await asyncio.gather(
            self._search_with_history(query, history), self._classify_message(query, history)
        )
        opener = ""
        if spoken:
            choices = (load_language_strings().get("openers") or {}).get(message_type) or []
            opener = random.choice(choices) if choices else ""
        logger.info(f"Message type: {message_type}{f', opener: {opener!r}' if opener else ''}")
        return search_results, message_type, opener

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
                            "document_name": item.metadata.get("document_name"),
                            "similarity": similarity,
                            "chunk_id": item.id,
                            "has_file": item.metadata.get("has_file", True),
                        }
                    )

            logger.info(
                f"Found {len(relevant_results)} relevant documents (threshold: {self.config.similarity_threshold})"
            )
            return relevant_results

        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []

    def _prepare_answer(
        self,
        query: str,
        search_results: List[Dict],
        conversation_history: Optional[List[Dict[str, str]]],
        strings: Dict[str, str],
        message_type: str = "question",
        opener: str = "",
    ) -> Dict[str, Any]:
        """Everything before the LLM call: maths note, prompt and sources.

        Shared by the whole-answer path (_generate_answer) and the streaming path
        (answer_query_stream), so both answer in exactly the same way.
        """
        # Small models get arithmetic wrong, so any sum in the message is
        # worked out exactly here and given to the model to explain.
        try:
            previous = conversation_history[-1]["question_text"] if conversation_history else None
            note = maths_note(query, previous, strings)
        except Exception as e:
            logger.warning(f"Maths helper failed, answering without it: {e}")
            note = ""
        # What kind of message this is, and the opener already spoken, so the model replies to
        # an answer as an answer and doesn't say "Good question!" a second time
        notes = [note, (strings.get("message_type_notes") or {}).get(message_type, "")]
        if opener and strings.get("opener_note"):
            notes.append(strings["opener_note"].format(opener=opener))
        query = "\n".join([query] + [n for n in notes if n])
        history_block = self._build_conversation_history_block(conversation_history or [], strings)

        if not search_results:
            # No relevant documents: fall back to the tutor's own general
            # knowledge instead of refusing to answer
            prompt = strings["general_prompt_template"].format(
                query=query,
                conversation_history=history_block,
                grade_instruction=grade_instruction(strings),
            )
            return {"prompt": prompt, "sources": [], "confidence": 0.0, "used_general_knowledge": True,
                    "temperature": 0.6,  # More creative/exploratory for open-ended teaching
                    "cacheable": False, "context": "", "must_say": None, "opener": opener}

        # Prepare context from the actual retrieved document chunks
        search_results = _whole_results_first(search_results)
        context_parts = []
        sources = []
        for i, result in enumerate(search_results, 1):
            context_parts.append(f"[{i}]: {result['text']}")
            sources.append(
                {
                    "id": i,
                    "document_id": result["document_id"],
                    "document_name": result.get("document_name"),
                    "similarity": result["similarity"],
                    "download_url": (
                        f"/api/v1/documents/{result['document_id']}/download"
                        if result.get("has_file", True)
                        else ""
                    ),
                    "text": result["text"],
                    "chunk_id": result["chunk_id"],
                }
            )

        context = "\n\n".join(context_parts)
        if len(context) > MAX_CONTEXT_CHARS:
            context = context[:MAX_CONTEXT_CHARS] + "\n\n" + strings["truncated_notice"]
        logger.debug(f"Context for prompt: {context[:800]}...")

        prompt = strings["prompt_template"].format(
            context=context,
            query=query,
            conversation_history=history_block,
            grade_instruction=grade_instruction(strings),
        )
        # Cache on the full prompt plus the model, so a hit can never
        # return an answer made for a different conversation, language,
        # grade, prompt wording or model (switching models in the admin
        # dashboard used to keep serving the old model's answers).
        # The top document's must-say safety line - once per conversation, not on every follow-up
        must_say = _must_say(search_results[0]["text"], strings.get("must_say_marker"))
        if must_say and any(must_say.lower() in (turn.get("answer_text") or "").lower()
                            for turn in conversation_history or []):
            must_say = None
        return {"prompt": prompt, "sources": sources,
                "confidence": max(r["similarity"] for r in search_results),
                "used_general_knowledge": False,
                "temperature": 0.4,  # Some room for a fun, engaging tone
                "cacheable": True, "context": context, "must_say": must_say, "opener": opener}

    def _finish_answer(self, response: str, prep: Dict[str, Any], strings: Dict[str, str]) -> Dict[str, Any]:
        """Everything after the LLM call: tidy the text, soften refusals, add citations."""
        if response and prep.get("opener"):
            response = _strip_repeated_opener(response, strings)  # Sparky already said one
        answer_text = response if response else strings["no_answer_generated"]
        trimmed = _trim_to_complete_sentence(answer_text)
        answer_text = _soften_refusal(trimmed, strings)
        must_say = prep.get("must_say")
        if response and must_say and answer_text == trimmed and must_say.lower() not in answer_text.lower():
            answer_text = _add_must_say(answer_text, must_say)  # not onto a refusal's safety redirect
        spoken_text = answer_text  # Citations below are for display, not speech

        # Add source footer - only when an answer was actually generated,
        # otherwise this would cite sources for an answer that doesn't exist
        sources = prep["sources"]
        if response and sources and self.config.require_sources:
            answer_text += f"\n\n{strings['sources_label']}:\n" + "\n".join(
                strings["source_line"].format(id=s["id"], document_id=s["document_id"], url=s["download_url"])
                for s in sources
            )

        result = {
            "text": answer_text,
            "spoken_text": spoken_text,
            "sources": sources,
            "confidence": prep["confidence"],
            "used_general_knowledge": prep["used_general_knowledge"],
        }
        if not prep["used_general_knowledge"]:
            context, prompt = prep["context"], prep["prompt"]
            result["debug_context"] = context[:500] + "..." if len(context) > 500 else context
            result["debug_prompt"] = prompt[:500] + "..." if len(prompt) > 500 else prompt
        return result

    async def _generate_answer(
        self,
        query: str,
        search_results: List[Dict],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        message_type: str = "question",
        opener: str = "",
    ) -> Dict[str, Any]:
        """Generate the whole AI answer (grounded in documents if any were found)"""
        strings = load_language_strings()
        try:
            prep = self._prepare_answer(query, search_results, conversation_history, strings,
                                        message_type, opener)
            model = getattr(self.llm_client, "model", "")
            if prep["cacheable"]:
                cached_response = self.cache.get(prep["prompt"], "", extra=model)
                if cached_response:
                    return cached_response

            response = await asyncio.to_thread(
                self.llm_client.generate_answer,
                query=prep["prompt"],
                context="",  # Context is already embedded in the prompt
                max_tokens=600,  # Enough room to finish a full explanation
                temperature=prep["temperature"],
                max_retries=1,  # Single attempt only
                is_complete_prompt=True,
            )
            result = self._finish_answer(response, prep, strings)

            # Cache the result for future queries - but only a real answer.
            # Caching a "no answer" fallback would keep serving it to every
            # future learner who hits the same query/context for up to the
            # cache's TTL, even after the LLM recovers from a transient failure.
            if response and prep["cacheable"]:
                self.cache.set(prep["prompt"], "", result, extra=model)
            return result

        except Exception as e:
            logger.error(f"AI answer generation failed: {e}")
            return {
                "text": strings["answer_generation_error"],
                "spoken_text": strings["answer_generation_error"],
                "sources": [],
                "confidence": 0.0,
                "used_general_knowledge": not search_results,
            }

    async def answer_query_stream(
        self,
        query: str,
        query_type: str = "text",
        session_id: Optional[str] = None,
        device_id: Optional[int] = None,
    ):
        """Like answer_query, but hands the answer over while the LLM is still writing it.

        Async generator of (kind, payload):
          ("meta", {sources, confidence, used_general_knowledge})  - once, before the answer
          ("sentence", text)                                         - each finished sentence
          ("done", <the same dict answer_query returns>)             - last
        The voice pipeline speaks sentence 1 while sentence 2 is being written, so the
        child hears the answer start seconds earlier (REQ-N-01).
        """
        strings = load_language_strings()
        if not self._is_valid_query(query):
            yield ("done", self._error_response("Invalid query"))
            return
        try:
            history = []
            if session_id and self.interaction_log_repo:
                history = await self.interaction_log_repo.get_recent_turns(
                    session_id, limit=self.config.max_conversation_turns,
                    max_gap_minutes=self.config.conversation_gap_minutes,
                )
            lesson = await self._lesson_turn(query, session_id, device_id)
            if not (lesson and lesson.reply):
                search_results, message_type, opener = await self._understand(
                    query, history, spoken=query_type == "voice"
                )
                prep = self._prepare_answer(query, search_results, history, strings, message_type, opener)
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            yield ("done", self._error_response(f"Processing failed: {str(e)}"))
            return

        if lesson and lesson.reply:  # a guided lesson's next part, said as written
            yield ("meta", {"sources": [], "confidence": 1.0, "used_general_knowledge": False})
            for sentence in _split_spoken(lesson.reply):
                yield ("sentence", sentence)
            response = self._lesson_response(query, lesson)
            if self.interaction_log_repo:
                asyncio.create_task(self._log_interaction(query, response, query_type, session_id, device_id))
            yield ("done", response)
            return

        # If the listener goes away mid-answer (the child pressed the button to ask something
        # else), the caller closes this generator: the model then stops writing, and only what
        # was actually handed out to be spoken is remembered.
        stop, said, logged = threading.Event(), [], False
        try:
            yield ("meta", {k: prep[k] for k in ("sources", "confidence", "used_general_knowledge")})
            if opener:
                said.append(opener)
                yield ("sentence", opener)  # spoken while the model is still writing the answer

            model = getattr(self.llm_client, "model", "")
            cached = self.cache.get(prep["prompt"], "", extra=model) if prep["cacheable"] else None
            spoken: List[str] = []
            if cached:
                result = cached
            else:
                text, refused, used = "", False, 0
                try:
                    async for chunk in self._stream_llm(prep, stop):
                        text += chunk
                        finished = [x.strip() for x in _SENTENCE_RE.split(text)[:-1] if x.strip()]
                        # This might be the closing question, which a safety line has to go before
                        if prep.get("must_say") and finished and finished[-1].endswith("?"):
                            finished = finished[:-1]
                        for sentence in finished[used:]:
                            used += 1
                            # The model's own "Good question!" after Sparky already said an opener
                            if not spoken and opener and _is_repeated_opener(sentence, strings):
                                continue
                            # A canned refusal shows in the first sentence: stop and redirect instead
                            if not spoken and _soften_refusal(sentence, strings) != sentence:
                                refused = True
                                break
                            spoken.append(sentence)
                            said.append(sentence)
                            yield ("sentence", sentence)
                        if refused:
                            stop.set()
                            break
                except Exception as e:
                    logger.error(f"Streaming answer failed: {e}")
                    text = " ".join(spoken)  # keep what was already said
                if refused:
                    result = self._finish_answer(strings["safety_redirect"], {**prep, "must_say": None}, strings)
                elif not text and not spoken:
                    result = self._finish_answer("", prep, strings)
                else:
                    result = self._finish_answer(text, prep, strings)
                    if prep["cacheable"]:
                        self.cache.set(prep["prompt"], "", result, extra=model)

            # Whatever the finished answer has beyond what was already said (or all of it, from the cache)
            for sentence in _split_spoken(result["spoken_text"])[len(spoken):]:
                said.append(sentence)
                yield ("sentence", sentence)
            tail = f" {lesson.after}" if lesson and lesson.after else ""  # mid-lesson: how to carry on
            for sentence in _split_spoken(tail):
                said.append(sentence)
                yield ("sentence", sentence)

            lead = f"{opener} " if opener else ""
            response = {
                "answer": lead + result["text"] + tail,
                "spoken_answer": lead + result.get("spoken_text", result["text"]) + tail,
                "message_type": message_type,
                "sources": result["sources"],
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "confidence": result["confidence"],
                "used_general_knowledge": result.get("used_general_knowledge", False),
                "lesson_progress_id": lesson.progress_id if lesson else None,
            }
            if self.interaction_log_repo:
                asyncio.create_task(self._log_interaction(query, response, query_type, session_id, device_id))
            logged = True
            yield ("done", response)
        finally:
            stop.set()
            if not logged and said and self.interaction_log_repo:
                logger.info(f"Answer cut off after {len(said)} sentence(s): remembering only what was said")
                partial = {"answer": " ".join(said), "confidence": prep["confidence"],
                           "sources": prep["sources"], "used_general_knowledge": prep["used_general_knowledge"],
                           "message_type": message_type,
                           "lesson_progress_id": lesson.progress_id if lesson else None}
                asyncio.create_task(self._log_interaction(query, partial, query_type, session_id, device_id))

    async def _stream_llm(self, prep: Dict[str, Any], stop: "threading.Event"):
        """The LLM's text, piece by piece, from a worker thread (generation blocks)."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        end = object()

        def worker():
            try:
                for chunk in self.llm_client.generate_stream(
                    prep["prompt"], max_tokens=600, temperature=prep["temperature"], stop=stop
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:  # handed to the reader, which raises it
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, end)

        loop.run_in_executor(None, worker)
        try:
            while True:
                item = await queue.get()
                if item is end:
                    return
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            stop.set()  # the reader stopped early: let the worker end the generation

    def _error_response(self, message: str) -> Dict[str, Any]:
        """Response for errors"""
        return {"error": message, "timestamp": datetime.utcnow().isoformat()}

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
