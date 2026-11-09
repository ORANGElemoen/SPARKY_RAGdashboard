"""Sparky works out whether the child asked a question, answered one or just said something,
so it doesn't say "Good question!" to an answer."""
import asyncio

from core.services import simple_rag_service as rag

STRINGS = rag.load_language_strings()
OPENERS = STRINGS["openers"]
ASKED = [{"question_text": "How many legs does a spider have?",
          "answer_text": "Spiders are amazing! How many legs do you think a spider has?"}]


class NoDocuments:
    async def search_similar_text(self, query, limit, threshold):
        class Result:
            items = []
        return Result()


class FakeLLM:
    """Answers the type check with `kind` and the real prompt with a short answer."""
    model = "fake"

    def __init__(self, kind):
        self.kind, self.prompts = kind, []

    def generate_answer(self, query, **kwargs):
        if "Decide what kind of message" in query:
            if isinstance(self.kind, Exception):
                raise self.kind
            return self.kind
        self.prompts.append(query)
        return "That's right, eight legs! What else has eight legs?"

    def generate_stream(self, prompt, max_tokens=600, temperature=0.4, stop=None):
        self.prompts.append(prompt)
        yield "That's right, eight legs! What else has eight legs?"


class History:
    def __init__(self, turns):
        self.turns = turns

    async def get_recent_turns(self, session_id, limit, max_gap_minutes=None):
        return self.turns

    async def log_interaction(self, *args, **kwargs):
        pass


def ask(kind, message, turns=(), query_type="voice"):
    llm = FakeLLM(kind)
    service = rag.SimpleRAGService(NoDocuments(), llm, interaction_log_repo=History(list(turns)))
    result = asyncio.run(service.answer_query(message, query_type=query_type, session_id="s"))
    return result, llm


def test_a_question_gets_a_question_opener():
    result, _ = ask("QUESTION", "Why is the sky blue?")
    assert result["message_type"] == "question"
    assert any(result["spoken_answer"].startswith(o) for o in OPENERS["question"])


def test_an_answer_gets_no_good_question(tmp_path):
    result, llm = ask("ANSWER", "Eight", ASKED)
    assert result["message_type"] == "answer"
    assert not any(o in result["spoken_answer"] for o in OPENERS["question"])
    assert any(result["spoken_answer"].startswith(o) for o in OPENERS["answer"])
    assert STRINGS["message_type_notes"]["answer"] in llm.prompts[-1]  # the model is told too


def test_a_statement_gets_no_opener():
    result, llm = ask("STATEMENT", "My name is Thabo", [])
    assert result["message_type"] == "statement"
    assert result["spoken_answer"].startswith("That's right")
    assert STRINGS["message_type_notes"]["statement"] in llm.prompts[-1]


def test_the_model_is_told_the_opener_was_already_said():
    result, llm = ask("QUESTION", "Why is the sky blue?")
    opener = result["spoken_answer"][:-len("That's right, eight legs! What else has eight legs?")].strip()
    assert STRINGS["opener_note"].format(opener=opener) in llm.prompts[-1]


def test_text_chat_gets_no_opener():
    result, _ = ask("QUESTION", "Why is the sky blue?", query_type="text")
    assert result["answer"].startswith("That's right")


def test_if_the_check_fails_punctuation_decides():
    assert ask(RuntimeError("down"), "Why is the sky blue?")[0]["message_type"] == "question"
    assert ask(RuntimeError("down"), "Eight", ASKED)[0]["message_type"] == "answer"
    assert ask("banana", "My name is Thabo")[0]["message_type"] == "statement"


def test_the_streamed_answer_speaks_the_opener_first():
    llm = FakeLLM("ANSWER")
    service = rag.SimpleRAGService(NoDocuments(), llm, interaction_log_repo=History(ASKED))

    async def run():
        return [p async for k, p in service.answer_query_stream("Eight", query_type="voice", session_id="s")
                if k == "sentence"]
    spoken = asyncio.run(run())
    assert spoken[0] in OPENERS["answer"]
    assert spoken[1:] == ["That's right, eight legs!", "What else has eight legs?"]


class RepeatsOpener(FakeLLM):
    """A model that starts with its own "Good question!" anyway."""
    def generate_answer(self, query, **kwargs):
        if "Decide what kind of message" in query:
            return "QUESTION"
        return "Great question! The sky is blue because of sunlight. Can you guess why?"

    def generate_stream(self, prompt, max_tokens=600, temperature=0.4, stop=None):
        yield "What a great question! The sky is blue because of sunlight. Can you guess why?"


def test_the_models_own_good_question_is_not_said_twice():
    service = rag.SimpleRAGService(NoDocuments(), RepeatsOpener("QUESTION"), interaction_log_repo=History([]))
    result = asyncio.run(service.answer_query("Why is the sky blue?", query_type="voice", session_id="s"))
    opener = result["spoken_answer"][:-len("The sky is blue because of sunlight. Can you guess why?")].strip()
    assert opener in OPENERS["question"]  # Sparky's opener, and not the model's "Great question!" too

    async def run():
        return [p async for k, p in service.answer_query_stream("Why is the sky blue?", query_type="voice",
                                                                session_id="s") if k == "sentence"]
    spoken = asyncio.run(run())
    assert spoken[0] in OPENERS["question"]
    assert spoken[1:] == ["The sky is blue because of sunlight.", "Can you guess why?"]


def test_text_chat_keeps_the_models_own_words():
    service = rag.SimpleRAGService(NoDocuments(), RepeatsOpener("QUESTION"), interaction_log_repo=History([]))
    result = asyncio.run(service.answer_query("Why is the sky blue?", query_type="text", session_id="s"))
    assert result["answer"].startswith("Great question!")  # no opener was spoken, so nothing to repeat


class SlowLLM(FakeLLM):
    """Writes a long answer slowly and records whether it was told to stop."""
    def __init__(self):
        super().__init__("QUESTION")
        self.stopped = False

    def generate_stream(self, prompt, max_tokens=600, temperature=0.4, stop=None):
        import time
        for i in range(50):
            if stop is not None and stop.is_set():
                self.stopped = True
                return
            time.sleep(0.02)
            yield f"Sentence number {i}. "


class Remembers(History):
    def __init__(self):
        super().__init__([])
        self.logged = []

    async def log_interaction(self, **kwargs):
        self.logged.append(kwargs)


def test_a_cut_off_answer_stops_the_model_and_remembers_only_what_was_said():
    llm, log = SlowLLM(), Remembers()
    service = rag.SimpleRAGService(NoDocuments(), llm, interaction_log_repo=log)

    async def run():
        answer = service.answer_query_stream("Why is the sky blue?", query_type="voice", session_id="s")
        said = []
        async for kind, payload in answer:
            if kind == "sentence":
                said.append(payload)
                if len(said) == 3:  # the opener and two sentences, then the child presses the button
                    break
        await answer.aclose()
        await asyncio.sleep(0.3)  # the worker thread notices the stop; the log task runs
        return said

    said = asyncio.run(run())
    assert llm.stopped
    assert len(log.logged) == 1
    assert log.logged[0]["answer_text"] == " ".join(said)
    assert "Sentence number 5" not in log.logged[0]["answer_text"]
