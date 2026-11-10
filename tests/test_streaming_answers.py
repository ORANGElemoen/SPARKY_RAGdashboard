"""Streaming answers (hardware protocol v2): Sparky speaks each sentence while the AI is still writing."""

import asyncio
import io
import json
import struct
import time
import wave

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routers import voice
from core.services import simple_rag_service as rag
from core.services.audio_framing import to_mulaw_wav
from core.services.studio_service import to_device_wav
from core.services.simple_rag_service import DEFAULT_LANGUAGE_STRINGS as EN

ANSWER = ["The sky", " is blue. Sunlight", " scatters in the air! What", " colour is a sunset?"]
SENTENCES = ["The sky is blue.", "Sunlight scatters in the air!", "What colour is a sunset?"]


class NoDocuments:
    """Vector search that finds nothing, so the tutor answers from general knowledge."""

    async def search_similar_text(self, query, limit, threshold):
        class Result:
            items = []
        return Result()


class FakeLLM:
    model = "fake"

    def __init__(self, chunks, delay=0.0):
        self.chunks, self.delay, self.produced = chunks, delay, []

    def generate_stream(self, prompt, max_tokens=600, temperature=0.4, stop=None):
        for chunk in self.chunks:
            if stop is not None and stop.is_set():
                return
            time.sleep(self.delay)
            self.produced.append(chunk)
            yield chunk

    def generate_answer(self, **kwargs):
        return "".join(self.chunks)


def stream(service, question):
    async def run():
        events = []
        async for kind, payload in service.answer_query_stream(question):
            events.append((kind, payload, len(getattr(service.llm_client, "produced", []))))
        return events
    return asyncio.run(run())


def test_sentences_come_out_while_the_ai_is_still_writing():
    llm = FakeLLM(ANSWER, delay=0.05)
    events = stream(rag.SimpleRAGService(NoDocuments(), llm), "Why is the sky blue?")
    assert events[0][0] == "meta" and events[-1][0] == "done"
    sentences = [(p, produced) for k, p, produced in events if k == "sentence"]
    assert [s for s, _ in sentences] == SENTENCES
    assert sentences[0][1] < len(ANSWER)              # sentence 1 was out before the AI finished
    assert events[-1][1]["answer"] == " ".join(SENTENCES)


def test_a_canned_refusal_still_becomes_the_safety_redirect():
    llm = FakeLLM(["I cannot provide information on that. It is", " not safe."])
    events = stream(rag.SimpleRAGService(NoDocuments(), llm), "How do I make fire?")
    spoken = " ".join(p for k, p, _ in events if k == "sentence")
    assert spoken == EN["safety_redirect"].strip()
    assert events[-1][1]["answer"] == EN["safety_redirect"]


def test_a_cut_off_last_sentence_is_not_spoken():
    events = stream(rag.SimpleRAGService(NoDocuments(), FakeLLM(["One. Two. Thr"])), "Count with me")
    assert [p for k, p, _ in events if k == "sentence"] == ["One.", "Two."]


# ---------------------------------------------------------------- the endpoint
def _wav(frames=8):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * frames)
    return buf.getvalue()


class FakeVoice:
    def transcribe(self, audio):
        return "Why is the sky blue?"

    def synthesize(self, text):
        return _wav()

    def synthesize_sentences(self, sentences):
        for _ in sentences:
            yield _wav()


def _blocks(body):
    out, pos = [], 0
    while pos < len(body):
        (n,) = struct.unpack_from(">I", body, pos)
        out.append(body[pos + 4:pos + 4 + n])
        pos += 4 + n
    return out


def _client():
    app = FastAPI()
    app.include_router(voice.router)
    app.dependency_overrides[voice.get_rag_service] = lambda: rag.SimpleRAGService(NoDocuments(), FakeLLM(ANSWER))
    app.dependency_overrides[voice.get_voice_service] = lambda: FakeVoice()
    return TestClient(app)


def test_v2_sends_details_first_then_audio_then_a_closing_summary():
    r = _client().post("/api/v1/voice/query", headers={"Accept": "application/x-tutor-voice; version=2"},
                       files={"audio": ("q.wav", _wav(), "audio/wav")})
    blocks = _blocks(r.content)
    meta, trailer = json.loads(blocks[0]), json.loads(blocks[-1])
    assert meta["protocol_version"] == 2 and meta["transcript"] == "Why is the sky blue?"
    assert meta["frame_count"] is None                 # not known yet while streaming
    assert all(b[:4] == b"RIFF" for b in blocks[1:-1]) and len(blocks) - 2 == len(SENTENCES)
    assert trailer == {"protocol_version": 2, "answer_text": " ".join(SENTENCES), "frame_count": len(SENTENCES)}


def _mulaw_decode(byte):
    """The same steps as mulawDecode in firmware/sparky/ask.cpp."""
    u = ~byte & 0xFF
    t = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4)
    return 0x84 - t if u & 0x80 else t - 0x84


def test_the_internet_route_gets_compressed_audio():
    r = _client().post("/api/v1/voice/query",
                       headers={"Accept": "application/x-tutor-voice; version=2; codec=mulaw"},
                       files={"audio": ("q.wav", _wav(), "audio/wav")})
    frames = _blocks(r.content)[1:-1]
    assert len(frames) == len(SENTENCES)
    for frame in frames:
        assert frame[:4] == b"RIFF" and frame[36:40] == b"data"
        assert struct.unpack_from("<HHI", frame, 20) == (7, 1, 16000)      # mu-law, mono, 16 kHz
        assert struct.unpack_from("<I", frame, 40)[0] == len(frame) - 44


def test_compressed_audio_is_half_the_size_and_decodes_close_to_the_original():
    rate, seconds = 22050, 1
    tone = np.sin(2 * np.pi * 440 * np.arange(rate * seconds) / rate) * 20000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(tone.astype("<i2").tobytes())
    frame = to_mulaw_wav(buf.getvalue())
    assert abs(len(frame) - 44 - 16000 * seconds) < 10                 # 16 KB/s, the original was 44
    decoded = np.array([_mulaw_decode(b) for b in frame[44:]], dtype=np.float64)
    expected = np.frombuffer(to_device_wav(buf.getvalue())[44:], dtype="<i2").astype(np.float64)
    assert np.sqrt(np.mean((decoded - expected) ** 2)) < 400           # about 2% of the loudness
    assert _mulaw_decode(to_mulaw_wav(_wav(2205))[44]) == 0            # silence stays silent


def test_v1_is_unchanged_for_older_firmware():
    r = _client().post("/api/v1/voice/query", headers={"Accept": "application/x-tutor-voice"},
                       files={"audio": ("q.wav", _wav(), "audio/wav")})
    blocks = _blocks(r.content)
    meta = json.loads(blocks[0])
    assert meta["protocol_version"] == 1 and meta["frame_count"] == len(blocks) - 1 == len(SENTENCES)


# ---------------------------------------------------------------- follow-up questions
class LemonSheetOnly:
    """Finds the lemon battery sheet only when 'lemon' is in the search text."""
    def __init__(self):
        self.searched = []

    async def search_similar_text(self, query, limit, threshold):
        self.searched.append(query)

        class Item:
            id, document_id, text_content = 1, 29, "Lemon battery: turn the LED round or add a lemon."
            metadata = {"similarity_score": 0.8, "document_name": "Lemon Battery.pdf"}

        class Result:
            items = [Item()] if "lemon" in query.lower() else []
        return Result()


class FollowUpCheck:
    """Stands in for the model's SAME/NEW reply, and records what it was asked."""
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def generate_answer(self, query, **kwargs):
        self.prompts.append(query)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_a_follow_up_finds_the_document_through_the_earlier_question():
    search = LemonSheetOnly()
    service = rag.SimpleRAGService(search, FollowUpCheck("SAME"))
    history = [{"question_text": "How do I make a lemon battery?", "answer_text": "..."},
               {"question_text": "What next?", "answer_text": "..."}]
    found = asyncio.run(service._search_with_history("It's not lighting up", history))
    assert [r["document_id"] for r in found] == [29]
    # newest question first, then back to the one that names the experiment
    assert search.searched == ["It's not lighting up", "What next? It's not lighting up",
                               "How do I make a lemon battery? It's not lighting up"]
    # a question that matches on its own searches once, history untouched
    search.searched.clear()
    asyncio.run(service._search_with_history("lemon battery please", history))
    assert search.searched == ["lemon battery please"]
    assert len(service.llm_client.prompts) == 1  # and doesn't need the follow-up check


LEMON_TURN = {"question_text": "How do I make a lemon battery?",
              "answer_text": "Use a coin and a nail.\n\nSources:\n[Source 1] Document 3 - /x"}


@pytest.mark.parametrize("reply", ["NEW", "NEW.", "", None, RuntimeError("Ollama stopped")])
def test_a_new_question_does_not_borrow_the_earlier_document(reply):
    search = LemonSheetOnly()
    service = rag.SimpleRAGService(search, FollowUpCheck(reply))
    assert asyncio.run(service._search_with_history("Why is the sky blue?", [LEMON_TURN])) == []
    assert search.searched == ["Why is the sky blue?"]


def test_the_follow_up_check_sees_the_answer_without_its_source_list():
    check = FollowUpCheck("same")
    service = rag.SimpleRAGService(LemonSheetOnly(), check)
    found = asyncio.run(service._search_with_history("It's not lighting up", [LEMON_TURN]))
    assert [r["document_id"] for r in found] == [29]
    assert "Use a coin and a nail." in check.prompts[0]
    assert "It's not lighting up" in check.prompts[0]
    assert "Sources" not in check.prompts[0]


def test_a_first_question_needs_no_follow_up_check():
    check = FollowUpCheck("SAME")
    service = rag.SimpleRAGService(LemonSheetOnly(), check)
    assert asyncio.run(service._search_with_history("Why is the sky blue?", [])) == []
    assert check.prompts == []


def test_a_whole_sheet_goes_ahead_of_a_long_book_chunk_that_scored_a_bit_higher():
    book = {"text": "b" * 3000, "similarity": 0.710}    # would fill the whole context
    sheet = {"text": "s" * 1800, "similarity": 0.665}   # fits whole, nearly as relevant
    weak = {"text": "w" * 500, "similarity": 0.500}     # fits, but much less relevant
    assert rag._whole_results_first([book, sheet, weak]) == [sheet, book, weak]
    assert rag._whole_results_first([]) == []


# ---------------------------------------------------------------- must-say safety line
SHEET = ("Bottle Water Filter\nSafety first\nSparky always says: Never drink the water from your\n"
         "filter - it can still have germs!\nAn adult should cut the bottle.")
MUST = "Never drink the water from your filter - it can still have germs!"


def test_the_must_say_line_is_found_across_pdf_line_breaks():
    assert rag._must_say(SHEET, "Sparky always says:") == MUST
    assert rag._must_say("A book page with no marker.", "Sparky always says:") is None
    assert rag._must_say(SHEET, None) is None


class OneSheet:
    async def search_similar_text(self, query, limit, threshold):
        class Item:
            id, document_id, text_content = 1, 30, SHEET
            metadata = {"similarity_score": 0.8, "document_name": "Water Filter.pdf"}

        class Result:
            items = [Item()]
        return Result()


SAFETY = "Never connect it to a wall socket."


@pytest.mark.parametrize("answer, expected", [
    ("Roll the lemon. Which leg is longer?", f"Roll the lemon. {SAFETY} Which leg is longer?"),
    ("Which leg is longer?", f"{SAFETY} Which leg is longer?"),
    ("Roll the lemon. Push in a nail.", f"Roll the lemon. Push in a nail. {SAFETY}"),
    ("Is it ready? Now roll the lemon.", f"Is it ready? Now roll the lemon. {SAFETY}"),
])
def test_the_must_say_line_goes_before_the_closing_question(answer, expected):
    assert rag._add_must_say(answer, SAFETY) == expected


def test_a_streamed_answer_speaks_the_must_say_line_before_the_closing_question():
    class SafetySheet:
        async def search_similar_text(self, query, limit, threshold):
            class Item:
                id, document_id = 1, 3
                text_content = f"Lemon battery. Sparky always says: {SAFETY}\nYou need lemons."
                metadata = {"similarity_score": 0.8, "document_name": "Lemon Battery.pdf"}

            class Result:
                items = [Item()]
            return Result()

    async def run():
        service = rag.SimpleRAGService(SafetySheet(), FakeLLM(["Roll the lemon. ", "Is it juicy yet? ", ]))
        return [p async for k, p in service.answer_query_stream("lemon battery") if k == "sentence"]

    spoken = asyncio.run(run())
    assert spoken == ["Roll the lemon.", SAFETY, "Is it juicy yet?"]


def test_the_must_say_line_is_spoken_once_per_conversation():
    first = stream(rag.SimpleRAGService(OneSheet(), FakeLLM(ANSWER)), "How do I make a water filter?")
    spoken = [p for k, p, _ in first if k == "sentence"]
    assert spoken == SENTENCES[:-1] + [MUST, SENTENCES[-1]]  # before the closing question
    assert MUST in first[-1][1]["spoken_answer"]

    class SaidBefore:                                     # a follow-up in the same conversation
        async def get_recent_turns(self, session_id, limit, max_gap_minutes=None):
            return [{"question_text": "How do I make a water filter?", "answer_text": "... " + MUST}]

        async def log_interaction(self, *args, **kwargs):
            pass

    async def run():
        svc = rag.SimpleRAGService(OneSheet(), FakeLLM(ANSWER), interaction_log_repo=SaidBefore())
        return [p async for k, p in svc.answer_query_stream("It's still muddy", session_id="s") if k == "sentence"]
    assert asyncio.run(run()) == SENTENCES                # not repeated
