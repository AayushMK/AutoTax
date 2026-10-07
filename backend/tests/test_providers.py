import io
from types import SimpleNamespace

import pytest
from google.genai import errors
from pypdf import PdfWriter

from app.engine.rules import RULES_DIR, load_rule_file
from app.watcher import extract, providers
from app.watcher.schema import ChunkFindings, ProposedChange


def findings(**kw) -> ChunkFindings:
    return ChunkFindings(**{"changes": [], "confirmations": [], "unmapped_findings": [], **kw})


def test_pick_gemini_model_prefers_newest_stable_flash():
    names = [
        "models/gemini-2.5-flash",
        "models/gemini-3.5-flash",
        "models/gemini-3.8-flash-lite",
        "models/gemini-3.6-flash-preview-09-2026",
        "models/gemini-3.5-pro",
        "models/text-embedding-004",
    ]
    assert providers.pick_gemini_model(names) == "gemini-3.5-flash"
    assert providers.pick_gemini_model(["models/gemini-3.1-flash-lite"]) == "gemini-3.1-flash-lite"
    with pytest.raises(RuntimeError):
        providers.pick_gemini_model(["models/gemini-3.5-pro"])


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def ok_response(parsed, reason="STOP"):
    return SimpleNamespace(candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason))], parsed=parsed)


def gemini(outcomes, models=("gemini-test",)):
    fake = SimpleNamespace(models=FakeModels(outcomes))
    p = providers.GeminiProvider(model=models[0], client=fake)
    p.models = list(models)
    return p, fake.models


def quota_error():
    return errors.APIError(429, {"error": {"code": 429, "message": "quota", "details": [{"retryDelay": "2s"}]}})


def test_gemini_retries_rate_limits(monkeypatch):
    sleeps = []
    monkeypatch.setattr(providers.time, "sleep", sleeps.append)
    p, models = gemini([quota_error(), quota_error(), ok_response(findings(document_title="FA"))])
    assert p.read_chunk(b"%PDF", "prompt").document_title == "FA"
    assert models.calls == 3 and len(sleeps) == 2 and all(s <= 120 for s in sleeps)


def overloaded():
    return errors.APIError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


def test_gemini_exhausted_becomes_chunk_failure(monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    p, _ = gemini([overloaded()] * providers.GeminiProvider.max_attempts)
    with pytest.raises(providers.ChunkFailed, match="unavailable or out of quota"):
        p.read_chunk(b"%PDF", "prompt")


def test_gemini_falls_back_to_next_model_when_overloaded(monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    n = providers.GeminiProvider.max_attempts
    p, models = gemini([overloaded()] * n + [ok_response(findings(document_title="FA"))], models=("g-3.8-flash", "g-3.7-flash"))
    assert p.read_chunk(b"%PDF", "prompt").document_title == "FA"
    assert models.calls == n + 1 and p.model == "g-3.7-flash"


def test_rank_models():
    names = ["models/gemini-3.8-flash", "models/gemini-3.7-flash", "models/gemini-3.5-flash-lite", "models/gemini-3.6-flash"]
    assert providers.rank_gemini_models(names) == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]


@pytest.mark.parametrize("resp,msg", [(ok_response(None, "MAX_TOKENS"), "MAX_TOKENS"), (ok_response(None), "no parsable")])
def test_gemini_incomplete_output_rejected(resp, msg):
    p, _ = gemini([resp])
    with pytest.raises(providers.ChunkFailed, match=msg):
        p.read_chunk(b"%PDF", "prompt")


def test_get_provider_selection(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID", "AUTOTAX_EXTRACTOR"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(providers.Path, "home", lambda: providers.Path("/nonexistent"))
    assert providers.available() == [] and providers.get_provider() is None
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert providers.available() == ["gemini", "claude"]  # free one first
    with pytest.raises(ValueError):
        providers.get_provider("openai")


class FakeProvider:
    name, model, pages_per_chunk, max_chunk_bytes = "fake", "fake-1", 4, 10 * 1024 * 1024

    def __init__(self):
        self.prompts = []

    def read_chunk(self, pdf, prompt):
        self.prompts.append(prompt)
        if len(self.prompts) == 2:
            raise providers.ChunkFailed("overloaded")
        return findings(
            changes=[ProposedChange(param="insurance.life_cap", proposed_value_json="50000", page=3, quote="पचास हजार", explanation="")]
        ) if len(self.prompts) == 1 else findings()


def test_extract_chunks_pages_and_records_failures(tmp_path):
    w = PdfWriter()
    for _ in range(10):
        w.add_blank_page(100, 100)
    pdf = tmp_path / "doc.pdf"
    buf = io.BytesIO()
    w.write(buf)
    pdf.write_bytes(buf.getvalue())

    p = FakeProvider()
    x = extract.extract(pdf, load_rule_file(RULES_DIR / "np" / "2083-84.yaml"), p, log=lambda *_: None)
    assert x.chunks == 3 and x.provider == "fake:fake-1"
    assert "pages 1-4" in p.prompts[0] and "pages 9-10" in p.prompts[2]
    assert [c.param for c in x.changes] == ["insurance.life_cap"]
    assert x.rejected == ["pages 5-8: overloaded"]
