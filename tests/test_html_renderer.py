from __future__ import annotations

from app.render.html_renderer import render_digest_html


def test_html_renderer_preserves_deep_dive_sections() -> None:
    html = render_digest_html(
        """
# Daily arXiv Digest - 2026-04-05

## Keyword: agent

### A Test Paper
- Quick summary: Short summary

#### Deep Dive
- Headline: Detailed headline
- Research question: What is being solved?
"""
    )

    assert "Deep Dive" in html
    assert "Detailed headline" in html
    assert "Categories" not in html
    assert "Matched keywords" not in html
    assert "Why matched" not in html
