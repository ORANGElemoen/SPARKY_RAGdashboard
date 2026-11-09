"""Guided lessons: a learner says "lesson", picks one, follows the steps and does the quiz."""
import asyncio

import pytest

from core.repositories.lesson_repository import LessonRepository, level_for_grade
from core.services import simple_rag_service as rag
from core.services.lesson_service import LessonService

S = rag.load_language_strings()

SPIDER = {
    "title": "Spider Legs", "topic": "Biology", "levels": ["easy", "intermediate"], "available": True,
    "content": {
        "hook": "Did you know spiders are not insects?",
        "outcomes": ["how many legs a spider has", "why spiders are not insects"],
        "steps": ["Look at a picture of a spider.", "Count its legs one by one."],
        "quiz": [
            {"question": "How many legs does a spider have?", "answer": "8", "why": "Spiders have eight legs."},
            {"question": "Is a spider an insect?", "answer": "No", "why": "Insects have six legs."},
            {"question": "What do spiders spin?", "answer": "Webs", "why": ""},
        ],
        "safety": "Never touch a real spider.",
        "recap": "Spiders have eight legs and are not insects.",
    },
}
VOLCANO = {**SPIDER, "title": "Volcano Eruptions", "topic": "Earth", "levels": ["advanced"],
           "content": {**SPIDER["content"], "hook": "Volcanoes are mountains that can erupt."}}
EGG = {**SPIDER, "title": "Floating Egg", "topic": "Forces", "levels": ["easy", "intermediate", "advanced"],
       "available": False}


class Marker:
    """Stands in for the model's quick checks: answers 'NO' to marking, '0' to picking."""
    def __init__(self, pick="0", mark="NO"):
        self.pick, self.mark = pick, mark

    def generate_answer(self, query, **kwargs):
        return self.mark if "Reply YES if the child" in query else self.pick


@pytest.fixture
def setup(tmp_path):
    repo = LessonRepository(str(tmp_path / "lessons.db"))
    for lesson in (SPIDER, VOLCANO, EGG):
        asyncio.run(repo.save_lesson(lesson))
    return repo


def say(service, text, session="board"):
    return asyncio.run(service.handle(text, session))


def test_grades_map_to_levels():
    assert [level_for_grade(g) for g in ("R", "3", "4", "6", "7", "12", "")] == \
        ["easy", "easy", "intermediate", "intermediate", "advanced", "advanced", ""]


def test_ordinary_questions_are_not_lessons(setup):
    assert say(LessonService(setup, Marker(), grade_loader=lambda: "5"), "Why is the sky blue?") is None


def test_a_whole_lesson(setup):
    svc = LessonService(setup, Marker(), grade_loader=lambda: "5")    # Grade 5: intermediate
    subjects = say(svc, "Sparky, what lessons can I do?").reply
    assert subjects == S["lesson_offer_categories"].format(categories="Biology")  # volcano: advanced; egg: off
    assert say(svc, "Biology please").reply == S["lesson_offer_one"].format(title="Spider Legs")

    intro = say(svc, "Yes please!").reply
    assert "Did you know spiders are not insects?" in intro and "Never touch a real spider." in intro
    assert intro.endswith(S["lesson_ready"])

    assert say(svc, "ready").reply == f"{S['lesson_step'].format(number=1, text='Look at a picture of a spider.')} {S['lesson_step_prompt']}"
    question = say(svc, "Why do spiders have so many legs, Sparky?")
    assert not question.reply and question.after == S["lesson_after_question"]   # answered normally
    assert "Look at a picture of a spider." in say(svc, "repeat that again").reply   # same step again
    step2 = say(svc, "I'm done").reply
    assert "Count its legs one by one." in step2 and S["lesson_last_step_prompt"] in step2

    quiz = say(svc, "next").reply
    assert quiz.startswith(S["lesson_quiz_intro"]) and "How many legs does a spider have?" in quiz
    right = say(svc, "eight").reply                                  # "eight" matches the key "8"
    assert any(right.startswith(c) for c in S["lesson_correct"]) and "Is a spider an insect?" in right
    wrong = say(svc, "yes it is").reply                              # the model's check says NO
    assert wrong.startswith(S["lesson_wrong"].format(answer="No")) and "What do spiders spin?" in wrong
    end = say(svc, "webs").reply
    assert S["lesson_wrap"].format(score=2, total=3, recap="Spiders have eight legs and are not insects.") in end

    assert say(svc, "Why is the sky blue?") is None                  # the lesson is over
    results = asyncio.run(setup.list_results())
    assert results[0]["lesson_title"] == "Spider Legs" and results[0]["score"] == 2
    assert results[0]["outcome"] == "completed"


def test_easy_lessons_ask_fewer_questions(setup):
    svc = LessonService(setup, Marker(), grade_loader=lambda: "2")
    say(svc, "lesson")
    say(svc, "biology")
    say(svc, "yes")
    say(svc, "next")
    say(svc, "next")
    say(svc, "next")                                                 # quiz starts
    say(svc, "8")
    assert S["lesson_wrap"].split("{")[0] in say(svc, "no").reply  # 2 questions, then the score


def test_choosing_between_lessons_by_title_or_by_the_model(setup):
    asyncio.run(setup.set_available(3, True))                      # the egg (Forces) is on offer too
    svc = LessonService(setup, Marker(pick="2"), grade_loader=lambda: "5")
    subjects = say(svc, "let's do a lesson").reply
    assert subjects == S["lesson_offer_categories"].format(categories="Biology and Forces")
    assert "spiders are not insects" in say(svc, "the spider one").reply   # a lesson by name, straight away

    assert say(svc, "stop", session="other") is None                    # nothing to stop: not a lesson turn
    say(svc, "lesson", session="other")
    listed = say(svc, "the second one", session="other").reply           # the model picked subject 2
    assert listed == S["lesson_offer_one"].format(title="Floating Egg")
    back = say(svc, "go back", session="other").reply                    # changed their mind
    assert back == S["lesson_offer_categories"].format(categories="Biology and Forces")
    assert say(svc, "forces", session="other").reply == listed
    started = say(svc, "can I do spider legs instead", session="other").reply   # a lesson from another subject
    assert "spiders are not insects" in started


def test_stopping_a_lesson(setup):
    svc = LessonService(setup, Marker(), grade_loader=lambda: "5")
    say(svc, "lesson")
    say(svc, "biology")
    say(svc, "yes")
    assert say(svc, "stop the lesson").reply == S["lesson_stopped"]
    assert say(svc, "next") is None
    assert asyncio.run(setup.list_results())[0]["outcome"] == "stopped"


def test_no_lessons_on_offer(tmp_path):
    repo = LessonRepository(str(tmp_path / "empty.db"))
    assert say(LessonService(repo, Marker(), grade_loader=lambda: ""), "lesson please").reply == S["lesson_none"]


class NoDocuments:
    async def search_similar_text(self, query, limit, threshold):
        class Result:
            items = []
        return Result()


class NoModel:
    model = "none"

    def generate_answer(self, **kwargs):
        raise AssertionError("a lesson's part should be said as written, without the model")

    def generate_stream(self, *a, **k):
        raise AssertionError("a lesson's part should be said as written, without the model")


def test_sparky_speaks_the_lesson_without_the_model(setup):
    lessons = LessonService(setup, Marker(), grade_loader=lambda: "5")
    service = rag.SimpleRAGService(NoDocuments(), NoModel(), None, lessons=lessons)

    async def run(text):
        return [p async for k, p in service.answer_query_stream(text, query_type="voice", session_id="s")
                if k == "sentence"]
    assert asyncio.run(run("What lessons can I do?")) == rag._split_spoken(
        S["lesson_offer_categories"].format(categories="Biology"))
    assert asyncio.run(service.answer_query("biology", query_type="text", session_id="s"))["message_type"] == "lesson"


def test_lessons_work_in_a_language_without_lesson_phrases_yet(tmp_path, monkeypatch):
    (tmp_path / "config" / "languages").mkdir(parents=True)
    import shutil
    shutil.copy("config/languages/en.yaml", tmp_path / "config/languages/en.yaml")
    (tmp_path / "config/languages/xx.yaml").write_text("name: Test\nsources_label: Quellen\n", encoding="utf-8")
    (tmp_path / "config/language_config.yaml").write_text("current_language: xx\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    strings = rag.load_language_strings()
    assert strings["sources_label"] == "Quellen" and strings["lesson_none"] == S["lesson_none"]



def test_a_question_mid_lesson_searches_the_lessons_own_sheet_first():
    """'Why do the metals have to be different?' matched the lemon sheet at only 34% on its own."""

    class Search:
        def __init__(self):
            self.calls = []

        async def search_similar_text(self, query, limit, threshold):
            self.calls.append((query, limit))

            class Item:
                id, document_id, text_content = 9, 3, "Zinc and copper are different metals."
                metadata = {"similarity_score": 0.62 if query.startswith("Lemon Battery:") else 0.34}

            class Result:
                items = [Item()]
            return Result()

    from core.services.lesson_service import LessonTurn

    search = Search()
    service = rag.SimpleRAGService(search, NoModel(), None)
    lesson = LessonTurn(after="say next", source_document_id=3, lesson_title="Lemon Battery")
    found = asyncio.run(service._search_for("Why do the metals have to be different?", [], lesson))
    assert [r["chunk_id"] for r in found] == [9] and found[0]["similarity"] == 0.62
    assert search.calls[-1][0] == "Lemon Battery: Why do the metals have to be different?"
    assert asyncio.run(service._search_for("Why do the metals have to be different?", [], None)) == []
