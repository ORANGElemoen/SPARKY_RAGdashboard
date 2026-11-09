"""
Guided lessons, spoken: what Sparky says when a learner starts, follows or leaves a lesson.

The teacher chooses which lessons are on offer and sets the class grade, which gives the level
(R-3 easy, 4-6 intermediate, 7+ advanced). A learner says "lesson" ("Sparky, let's do a
lesson", "what lessons can I do?") and picks one of the lessons offered. Then:

    hook + what you'll learn  ->  steps, one at a time  ->  quiz  ->  score and recap

"next", "repeat" and "stop" (lesson_*_words in the language file) move through it. Anything
else during the steps is treated as a question: Sparky answers it normally, then says how to
carry on. Quiz answers are marked against the teacher's answer key.

Everything Sparky says comes from the language file. handle() returns None when the message
has nothing to do with a lesson, so Sparky answers it as usual.
"""

import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..repositories.lesson_repository import level_for_grade

logger = logging.getLogger(__name__)

MAX_NAV_WORDS = 5          # "next", "I'm done", "say that again": longer messages are questions
EASY_QUIZ_QUESTIONS = 2    # easy lessons ask fewer questions
MAX_QUIZ_QUESTIONS = 5

PICK_PROMPT = """A child was offered these lessons and replied. Which lesson did the child choose?

{options}

Child said: {message}

Reply with the lesson's number only, or 0 if the child chose none of them."""

MARK_PROMPT = """A child answered a quiz question out loud. Speech recognition may have misspelt some words.

Question: {question}
Correct answer: {answer}
Child's answer: {given}

Reply YES if the child's answer shows the same idea as the correct answer, even in other words or less complete.
Reply NO if it is wrong, a different idea, or doesn't answer the question.
Reply with one word: YES or NO."""


@dataclass
class LessonTurn:
    reply: str = ""   # Sparky says this instead of a normal answer
    after: str = ""   # or: Sparky answers the message normally, then says this
    progress_id: Optional[int] = None   # which lesson attempt this turn belongs to (for the results view)


def _words(text: str) -> List[str]:
    return re.findall(r"\w+", (text or "").lower())


def _has(words: List[str], vocabulary) -> bool:
    vocabulary = {w.lower() for w in vocabulary or []}
    return any(w in vocabulary for w in words)


class LessonService:
    def __init__(self, repo, llm_client=None, strings_loader=None, grade_loader=None):
        from .simple_rag_service import load_language_strings, load_learner_grade

        self.repo = repo
        self.llm_client = llm_client
        self.strings = strings_loader or load_language_strings
        self.grade = grade_loader or load_learner_grade

    # ------------------------------------------------------------------ entry point
    async def handle(self, query: str, session_id: Optional[str], device_id: Optional[int] = None,
                     idle_minutes: int = 60) -> Optional[LessonTurn]:
        if not session_id or self.repo is None:
            return None
        s = self.strings()
        words = _words(query)
        progress = await self.repo.active_progress(session_id, idle_minutes)
        if progress is None:
            if _has(words, s.get("lesson_start_words")):
                return await self._offer(session_id, device_id, s)
            return None
        turn = await self._continue(progress, query, words, s)
        if turn is not None:
            turn.progress_id = progress["id"]
        return turn

    async def _continue(self, progress, query, words, s) -> Optional[LessonTurn]:
        short = len(words) <= MAX_NAV_WORDS
        if short and _has(words, s.get("lesson_stop_words")):
            await self.repo.finish_progress(progress["id"], "stopped")
            return LessonTurn(reply=s["lesson_stopped"])
        stage = progress["stage"]
        if stage == "choosing":
            return await self._choose(progress, query, words, s)
        lesson = await self.repo.get_lesson(progress["lesson_id"]) if progress.get("lesson_id") else None
        if lesson is None:  # deleted by the teacher meanwhile
            await self.repo.finish_progress(progress["id"], "stopped")
            return None
        if stage == "ready":
            return await self._ready(progress, lesson, words, short, s)
        if stage == "steps":
            return await self._steps(progress, lesson, words, short, s)
        if stage == "quiz":
            return await self._quiz(progress, lesson, query, words, short, s)
        return None

    # ------------------------------------------------------------------ choosing a lesson
    async def _offer(self, session_id, device_id, s) -> LessonTurn:
        level = level_for_grade(self.grade())
        lessons = await self.repo.list_lessons(available_only=True, level=level)
        if not lessons:
            return LessonTurn(reply=s["lesson_none"])
        progress_id = await self.repo.start_progress(session_id, device_id, "choosing", level=level,
                                                     offered=[x["id"] for x in lessons])
        if len(lessons) == 1:
            return LessonTurn(reply=s["lesson_offer_one"].format(title=lessons[0]["title"]), progress_id=progress_id)
        return LessonTurn(reply=s["lesson_offer_many"].format(
            count=len(lessons), titles=self._join([x["title"] for x in lessons], s)), progress_id=progress_id)

    async def _choose(self, progress, query, words, s) -> LessonTurn:
        lessons = [x for x in [await self.repo.get_lesson(i) for i in progress["offered"]] if x]
        if not lessons:
            await self.repo.finish_progress(progress["id"], "stopped")
            return LessonTurn(reply=s["lesson_none"])
        short = len(words) <= MAX_NAV_WORDS
        if len(lessons) == 1 and short:
            if _has(words, s.get("lesson_no_words")):
                await self.repo.finish_progress(progress["id"], "stopped")
                return LessonTurn(reply=s["lesson_not_now"])
            if _has(words, s.get("lesson_next_words")):
                return await self._begin(progress, lessons[0], s)
        chosen = self._match_title(words, lessons) or await self._ask_which(query, lessons)
        if chosen:
            return await self._begin(progress, chosen, s)
        if short and _has(words, s.get("lesson_no_words")):
            await self.repo.finish_progress(progress["id"], "stopped")
            return LessonTurn(reply=s["lesson_not_now"])
        return LessonTurn(reply=s["lesson_which"].format(titles=self._join([x["title"] for x in lessons], s)))

    @staticmethod
    def _match_title(words, lessons) -> Optional[Dict[str, Any]]:
        """The lesson whose title shares the most real words (3+ letters) with the reply."""
        said = {w for w in words if len(w) >= 3}
        scores = [(len(said & {w for w in _words(x["title"]) if len(w) >= 3}), x) for x in lessons]
        scores.sort(key=lambda pair: -pair[0])
        if scores and scores[0][0] > 0 and (len(scores) == 1 or scores[0][0] > scores[1][0]):
            return scores[0][1]
        return None

    async def _ask_which(self, query, lessons) -> Optional[Dict[str, Any]]:
        """For "the first one", "the egg one" and mishearings: ask the model."""
        reply = await self._quick(PICK_PROMPT.format(
            options="\n".join(f"{i}. {x['title']}" for i, x in enumerate(lessons, 1)), message=query))
        number = re.search(r"\d+", reply or "")
        if number and 1 <= int(number.group()) <= len(lessons):
            return lessons[int(number.group()) - 1]
        return None

    async def _begin(self, progress, lesson, s) -> LessonTurn:
        content = lesson["content"]
        level = progress.get("level") or (lesson["levels"][0] if lesson["levels"] else "")
        quiz = content.get("quiz") or []
        total = min(len(quiz), EASY_QUIZ_QUESTIONS if level == "easy" else MAX_QUIZ_QUESTIONS)
        await self.repo.update_progress(progress["id"], lesson_id=lesson["id"], lesson_title=lesson["title"],
                                        level=level, stage="ready", step_index=-1, quiz_index=0, score=0,
                                        quiz_total=total)
        return LessonTurn(reply=self._intro(lesson, s))

    def _intro(self, lesson, s) -> str:
        content = lesson["content"]
        parts = [s["lesson_intro"].format(title=lesson["title"], hook=content.get("hook", "")).strip()]
        outcomes = [o.strip().rstrip(".") for o in content.get("outcomes") or [] if o.strip()]
        if outcomes:
            parts.append(s["lesson_outcomes"].format(outcomes=self._join(outcomes, s)))
        if content.get("safety"):
            parts.append(content["safety"].strip())
        parts.append(s["lesson_ready"])
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------------ the steps
    async def _ready(self, progress, lesson, words, short, s) -> LessonTurn:
        if short and _has(words, s.get("lesson_no_words")):
            return LessonTurn(reply=s["lesson_waiting"])
        if short and _has(words, s.get("lesson_repeat_words")):
            return LessonTurn(reply=self._intro(lesson, s))
        if short and _has(words, s.get("lesson_next_words")):
            return await self._show_step(progress, lesson, 0, s)
        return LessonTurn(after=s["lesson_after_question"])

    async def _steps(self, progress, lesson, words, short, s) -> LessonTurn:
        index = progress["step_index"]
        if short and _has(words, s.get("lesson_no_words")):
            return LessonTurn(reply=s["lesson_waiting"])
        if short and _has(words, s.get("lesson_repeat_words")):
            return await self._show_step(progress, lesson, index, s)
        if short and _has(words, s.get("lesson_next_words")):
            if index + 1 < len(lesson["content"].get("steps") or []):
                return await self._show_step(progress, lesson, index + 1, s)
            return await self._start_quiz(progress, lesson, s)
        return LessonTurn(after=s["lesson_after_question"])

    async def _show_step(self, progress, lesson, index, s) -> LessonTurn:
        steps = lesson["content"].get("steps") or []
        if not steps:
            return await self._start_quiz(progress, lesson, s)
        index = max(0, min(index, len(steps) - 1))
        await self.repo.update_progress(progress["id"], stage="steps", step_index=index)
        prompt = s["lesson_last_step_prompt"] if index == len(steps) - 1 else s["lesson_step_prompt"]
        return LessonTurn(reply=f"{s['lesson_step'].format(number=index + 1, text=steps[index].strip())} {prompt}")

    # ------------------------------------------------------------------ the quiz
    async def _start_quiz(self, progress, lesson, s) -> LessonTurn:
        if not progress.get("quiz_total"):
            return await self._wrap(progress, lesson, 0, s)
        await self.repo.update_progress(progress["id"], stage="quiz", quiz_index=0, score=0)
        question = lesson["content"]["quiz"][0]["question"]
        return LessonTurn(reply=f"{s['lesson_quiz_intro']} {s['lesson_question'].format(number=1, question=question)}")

    async def _quiz(self, progress, lesson, query, words, short, s) -> LessonTurn:
        quiz = lesson["content"].get("quiz") or []
        index, total = progress["quiz_index"], progress["quiz_total"]
        if index >= min(total, len(quiz)):
            return await self._wrap(progress, lesson, progress["score"], s)
        item = quiz[index]
        if short and _has(words, s.get("lesson_repeat_words")) and len(words) <= 2:
            return LessonTurn(reply=s["lesson_question"].format(number=index + 1, question=item["question"]))
        correct, marked_by = await self._is_correct(query, words, item)
        await self.repo.record_answer(progress["id"], index, item.get("question", ""), item.get("answer", ""),
                                      query, correct, marked_by)
        score = progress["score"] + (1 if correct else 0)
        if correct:
            feedback = random.choice(s.get("lesson_correct") or ["Correct!"])
        else:
            feedback = s["lesson_wrong"].format(answer=item["answer"].strip().rstrip("."))
        why = (item.get("why") or "").strip()
        if why:
            feedback = f"{feedback} {why}"
        if index + 1 < total and index + 1 < len(quiz):
            await self.repo.update_progress(progress["id"], quiz_index=index + 1, score=score)
            nxt = s["lesson_question"].format(number=index + 2, question=quiz[index + 1]["question"])
            return LessonTurn(reply=f"{feedback} {nxt}")
        wrap = await self._wrap(progress, lesson, score, s)
        return LessonTurn(reply=f"{feedback} {wrap.reply}")

    async def _is_correct(self, query, words, item):
        """(correct, how): "match" if the answer's words were all said, else the model's "ai" verdict."""
        key = [w for w in _words(item.get("answer", "")) if len(w) >= 2 or w.isdigit()]
        numbers = self._number_words()
        said = {numbers.get(w, w) for w in words}
        if key and all(numbers.get(w, w) in said for w in key):
            return True, "match"
        reply = await self._quick(MARK_PROMPT.format(question=item.get("question", ""),
                                                     answer=item.get("answer", ""), given=query))
        return (reply or "").strip().upper().startswith("YES"), "ai"

    def _number_words(self) -> Dict[str, str]:
        """'eight' and '8' count as the same answer (number words come from the language file)."""
        numbers = ((self.strings().get("maths_words") or {}).get("numbers")) or {}
        return {str(word).lower(): str(value) for word, value in numbers.items()}

    async def _wrap(self, progress, lesson, score, s) -> LessonTurn:
        await self.repo.update_progress(progress["id"], score=score, stage="done")
        await self.repo.finish_progress(progress["id"], "completed")
        recap = (lesson["content"].get("recap") or "").strip()
        return LessonTurn(reply=s["lesson_wrap"].format(score=score, total=progress["quiz_total"], recap=recap)
                          .replace("  ", " "))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _join(items: List[str], s) -> str:
        items = [i for i in items if i]
        if len(items) <= 1:
            return "".join(items)
        return s.get("lesson_list_join", ", ").join(items[:-1]) + s.get("lesson_list_last", " and ") + items[-1]

    async def _quick(self, prompt: str) -> str:
        if self.llm_client is None:
            return ""
        import asyncio

        try:
            return await asyncio.to_thread(self.llm_client.generate_answer, query=prompt, context="",
                                           max_tokens=4, temperature=0.0, max_retries=1,
                                           is_complete_prompt=True) or ""
        except Exception as e:
            logger.warning(f"Lesson check failed: {e}")
            return ""
