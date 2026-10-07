import io
import json
import shutil
from datetime import date, timedelta

import httpx
import nepali_datetime
import pytest
import respx
import yaml
from pypdf import PdfWriter

from app.engine import gate
from app.engine.rules import RULES_DIR, load_rule_file, rules_for_date
from app.watcher import __main__ as cli
from app.watcher import documents, impact, propose, sources
from app.watcher.extract import ChunkFindings, Confirmation, Extraction, ProposedChange, merge

LISTING = """
<html><body>
<a href="/content/13700/new-finance-ordinance/"><img src="x.png"></a>
<a href="/content/13700/new-finance-ordinance/">आयकर (सोह्रौँ संशोधन) नियमावली, २०८३</a>
<a href="/content/13701/tender/">मसलन्द खरिद सम्बन्धी बोलपत्र आव्हानको सूचना</a>
<a href="/content/13702/old/">आर्थिक ऐन, २०८३</a>
<a href="/category/notice/">सूचना</a>
</body></html>
"""

CONTENT_PAGE = """<html><script>viewer.load("https://giwmscdnone.gov.np/media/pdf_upload/%E0%A4%86%E0%A4%AF (x)_abc.pdf")</script></html>"""


def _pdf_bytes(pages=2) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(100, 100)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture
def cfg():
    return sources.load_config()


@pytest.fixture
def src():
    return sources.Source("ird_notice", "IRD", "https://ird.gov.np/category/notice/", r"/content/\d+/")


# --- scanning --------------------------------------------------------------------------------

def test_parse_listing_dedupes_and_keeps_titles(src):
    items = sources.parse_listing(src, LISTING)
    assert [i.url for i in items] == [
        "https://ird.gov.np/content/13700/new-finance-ordinance/",
        "https://ird.gov.np/content/13701/tender/",
        "https://ird.gov.np/content/13702/old/",
    ]
    assert items[0].title.startswith("आयकर")


@pytest.mark.parametrize(
    "title,expected",
    [
        ("आर्थिक ऐन, २०८४ (राजपत्रमा प्रकाशित)", True),
        ("आयकर (सोह्रौँ संशोधन) नियमावली", True),
        ("Ordinance to amend some Nepal Acts", True),
        ("TDS return filing notice", True),
        ("मसलन्द खरिद सम्बन्धी बोलपत्र आव्हानको सूचना", False),
        ("मूल्य अभिवृद्धि कर ऐन (आर्थिक ऐन,२०८२ ले गरेको संशोधन सहित)", False),
        ("Statistics on outstanding loans", False),  # 'tds' inside a word must not match
    ],
)
def test_relevance(cfg, title, expected):
    assert cfg.is_relevant(title) is expected


def test_diff_and_mark_seen(src):
    state = {"seen": {}}
    items = sources.parse_listing(src, LISTING)
    new = sources.diff_new(items + items, state)
    assert len(new) == 3
    sources.mark_seen(new, state, {new[0].url})
    assert sources.diff_new(items, state) == []
    assert state["seen"][new[0].url]["relevant"] is True


def test_find_pdf_links_in_cms_viewer_script():
    links = documents.find_pdf_links("https://ird.gov.np/content/1/x/", CONTENT_PAGE)
    assert links == ["https://giwmscdnone.gov.np/media/pdf_upload/%E0%A4%86%E0%A4%AF (x)_abc.pdf"]


# --- proposals -------------------------------------------------------------------------------

@pytest.fixture
def fy8384():
    return load_rule_file(RULES_DIR / "np" / "2083-84.yaml")


def change(param, value, page=12):
    return ProposedChange(param=param, proposed_value_json=json.dumps(value), page=page, quote="…", explanation="")


def test_apply_changes_creates_new_version_and_keeps_citations(fy8384):
    src_info = {"key": "doc_abc", "title": "Ordinance", "url": "https://x/y.pdf", "sha256": "ab" * 32}
    text, new = propose.apply_changes(fy8384, [change("insurance.life_cap", 50000)], source=src_info, effective_from_bs="2083-09-01")
    assert new.raw.version == 2
    assert new.value("insurance.life_cap") == 50000
    p = new.raw.params["insurance.life_cap"]
    assert p.status == "needs_review" and p.src == "doc_abc" and "PROPOSED from p.12" in p.ref
    assert new.raw.review.status == "draft"
    assert new.effective_from == nepali_datetime.date(2083, 9, 1).to_datetime_date()
    assert new.effective_to == fy8384.effective_to
    assert "# Nepal salary income-tax rules" in text  # comments preserved


def test_apply_changes_next_fiscal_year(fy8384):
    _, new = propose.apply_changes(fy8384, [change("nonresident.flat_rate", "0.20")], effective_from_bs="2084-04-01")
    assert new.fiscal_year == "2084/85" and new.raw.version == 1
    assert new.effective_from == date(2027, 7, 17)
    assert new.effective_to == nepali_datetime.date(2085, 4, 1).to_datetime_date() - timedelta(days=1)


def test_malformed_slabs_rejected(fy8384):
    with pytest.raises(Exception):
        propose.apply_changes(fy8384, [change("resident.slabs.single", [{"width": 100, "rate": "0.01"}])])


def test_merge_validates_model_output(fy8384):
    x = Extraction()
    merge(
        x,
        ChunkFindings(
            effective_from_bs="2083-09-01",
            changes=[
                change("insurance.life_cap", 50000, page=12),  # valid
                change("insurance.health_cap", 20000, page=13),  # same as current -> confirmation
                change("made.up.param", 1, page=12),  # unknown
                change("insurance.building_cap", 7000, page=99),  # outside chunk
            ],
            confirmations=[Confirmation(param="nonresident.flat_rate", page=14, quote="२५ प्रतिशत")],
            unmapped_findings=["New allowance exemption for foreign employment"],
        ),
        fy8384,
        first=1,
        last=60,
    )
    assert [c.param for c in x.changes] == ["insurance.life_cap"]
    assert {c.param for c in x.confirmations} == {"insurance.health_cap", "nonresident.flat_rate"}
    assert len(x.rejected) == 2
    assert x.effective_from_bs == "2083-09-01"


def test_impact_shows_changed_cases(fy8384):
    _, new = propose.apply_changes(fy8384, [change("insurance.life_cap", 50000)])
    changed = {r.case: r.delta for r in impact.impact(fy8384, new) if r.delta}
    # life premium 50,000 now fully deductible: 10,000 more relief at 10% marginal rate
    assert changed == {"2083/84 insurance caps": -1000}


# --- multi-version rules and gates -----------------------------------------------------------

@pytest.fixture
def rules_dir(tmp_path, fy8384):
    d = tmp_path / "rules"
    shutil.copytree(RULES_DIR / "np", d / "np", ignore=shutil.ignore_patterns("proposed"))
    (d / "sources").mkdir()
    return d


def test_mid_year_version_takes_over_from_its_start_date(rules_dir, fy8384):
    text, v2 = propose.apply_changes(fy8384, [change("insurance.life_cap", 50000)], effective_from_bs="2083-09-01")
    (rules_dir / "np" / "2083-84.v2.yaml").write_text(text, encoding="utf-8")
    switch = v2.effective_from
    assert rules_for_date(switch - timedelta(days=1), rules_dir=rules_dir).raw.version == 1
    assert rules_for_date(switch, rules_dir=rules_dir).raw.version == 2


def test_gate_blocks_uncovered_and_unverified(rules_dir):
    with pytest.raises(gate.RuleCoverageError):
        gate.check_payroll_allowed(date(2027, 8, 1), rules_dir=rules_dir)
    with pytest.raises(gate.UnverifiedRulesError):
        gate.check_payroll_allowed(date(2026, 10, 1), rules_dir=rules_dir)
    ok = gate.check_payroll_allowed(date(2026, 10, 1), acknowledge_unverified=True, rules_dir=rules_dir)
    assert ok.acknowledged_unverified and ok.warnings


def test_gate_detects_tampered_source(rules_dir):
    data = yaml.safe_load((rules_dir / "np" / "2083-84.yaml").read_text())
    sha = data["sources"]["fa2083"]["sha256"]
    (rules_dir / "sources" / f"{sha[:16]}.pdf").write_bytes(b"not the gazette")
    with pytest.raises(gate.SourceIntegrityError):
        gate.check_payroll_allowed(date(2026, 10, 1), acknowledge_unverified=True, rules_dir=rules_dir)


def test_budget_season_alert(rules_dir):
    jestha_20 = nepali_datetime.date(2084, 2, 20).to_datetime_date()
    assert "Budget season" in gate.budget_season_alert(jestha_20, rules_dir=rules_dir)
    assert gate.budget_season_alert(date(2026, 10, 7), rules_dir=rules_dir) is None
    assert gate.budget_season_alert(date(2027, 8, 1), rules_dir=rules_dir).startswith("CRITICAL")


# --- end to end ------------------------------------------------------------------------------

@respx.mock
def test_run_end_to_end(tmp_path, monkeypatch):
    cfg_file = tmp_path / "watch_sources.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "sources": [{"id": "ird_notice", "name": "IRD", "url": "https://ird.gov.np/category/notice/", "item_pattern": r"/content/\d+/"}],
        "relevant_keywords": ["आयकर", "आर्थिक ऐन"],
        "ignore_keywords": ["बोलपत्र"],
    }, allow_unicode=True))
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"seen": {"https://ird.gov.np/content/13702/old/": {}}}))
    monkeypatch.setattr(sources, "SOURCES_FILE", cfg_file)
    monkeypatch.setattr(sources, "STATE_FILE", state_file)
    monkeypatch.setattr(documents, "ARCHIVE_DIR", tmp_path / "archive")

    respx.get("https://ird.gov.np/category/notice/").mock(return_value=httpx.Response(200, text=LISTING))
    respx.get("https://ird.gov.np/content/13700/new-finance-ordinance/").mock(return_value=httpx.Response(200, text=CONTENT_PAGE))
    respx.get(url__regex=r"https://giwmscdnone\.gov\.np/media/pdf_upload/.*").mock(return_value=httpx.Response(200, content=_pdf_bytes()))

    report = tmp_path / "report.md"
    code = cli.main(["--today", "2026-10-07", "run", "--no-extract", "--report", str(report)])
    assert code == cli.FOUND
    text = report.read_text()
    assert "आयकर (सोह्रौँ संशोधन) नियमावली" in text
    assert "2 pages" in text and "scanned (no text layer)" in text
    assert "बोलपत्र" in text  # listed under "not relevant", not as a finding
    assert len(list((tmp_path / "archive").glob("*.pdf"))) == 1
    # second run: nothing new
    assert cli.main(["--today", "2026-10-07", "run", "--no-extract", "--report", str(report)]) == 0
