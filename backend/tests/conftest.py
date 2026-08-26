"""Backend-wide test fixtures.

`GEMINI_API_KEY` lives in `backend/.env` (gitignored) and gets pulled into
`os.environ` process-wide the moment anything imports `app.db` (which calls
`load_dotenv()`), regardless of which test file triggered that import. Left
alone, that would make every existing "pure regex" unit test for
intent/chat-follow-up parsing silently start making live Gemini calls the
moment the key is present — slow, network-flaky, and not what those tests
are meant to verify. This fixture clears it by default for every test;
tests that specifically exercise the LLM-configured path opt back in with
`monkeypatch.setenv("GEMINI_API_KEY", "...")` and mock the actual call."""

import pytest


@pytest.fixture(autouse=True)
def _no_llm_key_by_default(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
