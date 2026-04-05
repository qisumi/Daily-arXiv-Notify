from __future__ import annotations

import markdown


def render_digest_html(markdown_text: str) -> str:
    body = markdown.markdown(markdown_text, extensions=["extra", "sane_lists"])
    return (
        "<html><body>"
        "<style>"
        "body{margin:0;background:#f3f6fb;color:#1f2937;font-family:Arial,sans-serif;}"
        ".digest{max-width:920px;margin:0 auto;padding:24px 16px 40px;}"
        "h1,h2,h3,h4{color:#1f2937;}"
        "h1{margin-bottom:20px;}"
        "h2{margin-top:28px;padding-top:8px;border-top:1px solid #d7e0ea;}"
        "h3{margin-top:24px;padding:16px 0 0;border-top:1px solid #e5ebf3;}"
        "h4{margin-top:16px;color:#0f766e;}"
        "a{color:#0f766e;text-decoration:none;}"
        "a:hover{text-decoration:underline;}"
        "p,li{line-height:1.6;}"
        "ul{padding-left:22px;}"
        "li{margin:6px 0;}"
        "code{background:#e8eef6;border-radius:4px;padding:1px 4px;}"
        "</style>"
        f"<div class=\"digest\">{body}</div></body></html>"
    )
