from __future__ import annotations

import markdown


def render_digest_html(markdown_text: str) -> str:
    body = markdown.markdown(markdown_text, extensions=["extra", "sane_lists"])
    return (
        "<html><body>"
        "<style>"
        "body{font-family:Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;}"
        "h1,h2,h3{color:#1f2937;}"
        "a{color:#0f766e;}"
        "li{margin:6px 0;}"
        "</style>"
        f"{body}</body></html>"
    )
