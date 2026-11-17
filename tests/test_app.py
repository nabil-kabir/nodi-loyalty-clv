"""Phase 7 tests: every page renders headless from app_data/, key interactions work, no truth access."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from nodi.config import ROOT

APP = str(ROOT / "app" / "streamlit_app.py")
PAGES = ["pages/executive.py", "pages/segments.py", "pages/allocator.py", "pages/studio.py"]


def run_page(page: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    if page != PAGES[0]:
        at.switch_page(page).run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_banner(page):
    at = run_page(page)
    assert not at.exception, [e.value for e in at.exception]
    assert any("Synthetic data" in m.value for m in at.markdown), "synthetic-data banner missing"


def test_executive_numbers_match_headline():
    h = json.loads((ROOT / "app_data" / "headline.json").read_text(encoding="utf-8"))
    at = run_page(PAGES[0])
    roi = f"৳{h['plans']['optimised']['roi']:.2f}"
    assert any(m.value == roi for m in at.metric)


def test_budget_slider_reallocates_live():
    at = run_page(PAGES[2])
    before = next(m.value for m in at.metric if m.label == "Expected net margin (12m)")
    at.slider[0].set_value(0.5).run()
    after = next(m.value for m in at.metric if m.label == "Expected net margin (12m)")
    assert not at.exception and before != after
    at.radio[0].set_value("face").run()                       # face-value costing view
    assert not at.exception


def test_studio_validator_rejects_a_bad_edit():
    at = run_page(PAGES[3])
    at.radio[0].set_value("en").run()
    at.text_area[0].set_value("Gift: 3 GB free data, valid 7 days. Dial *121*2#. STOP: 21212").run()
    assert any("not in the offer record" in e.value for e in at.error)


def test_app_reads_only_app_data():
    for py in (ROOT / "app").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "warehouse" not in text and "ground_truth" not in text and "data/raw" not in text, py
