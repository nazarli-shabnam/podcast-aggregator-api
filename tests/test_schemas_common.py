from __future__ import annotations

from app.schemas.common import Page


def test_page_pages_computes_total_page_count() -> None:
    page = Page[str](items=["a", "b"], total=25, page=1, page_size=10)
    assert page.pages == 3


def test_page_pages_rounds_up_a_partial_final_page() -> None:
    page = Page[str](items=[], total=21, page=1, page_size=10)
    assert page.pages == 3
