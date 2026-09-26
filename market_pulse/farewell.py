"""The one-time goodbye email sent when Be Greedy closed (September 2026).

Sent once, by hand, via the daily workflow's `farewell` input. Styled like the
alert email so subscribers recognise it.
"""

from __future__ import annotations

from .report import _SANS, _SERIF

SUBJECT = "Be Greedy is closing — and a correction"

# Paragraphs, shared by the HTML and plain-text versions.
PARAGRAPHS = [
    "This is the last email you’ll get from Be Greedy. The service is closing.",
    "First, a correction. Since early summer, Be Greedy sent a “Be Fearful — "
    "consider trimming” email almost every week. That was a bug: one valuation "
    "gauge was weighted so heavily that an ordinary market near its highs looked "
    "like an extreme. Please don’t act on those emails.",
    "While fixing it, I tested the signals against 36 years of market history "
    "(1990–2026). Selling on “Be Fearful” signals ended up behind simply staying "
    "invested, in every version I tried. “Be Greedy” days were only slightly "
    "better than average days to buy — not enough to justify an alert service.",
    "So the takeaway is the boring one: for most people, a low-cost index fund "
    "held through the ups and downs has been very hard to beat.",
    "You don’t need to do anything. The subscriber list will be deleted shortly. "
    "Thanks for signing up.",
]

FOOTER = "Not financial advice."


def render_text(unsubscribe_url: str | None = None) -> str:
    lines = ["BE GREEDY IS CLOSING", ""]
    for p in PARAGRAPHS:
        lines += [p, ""]
    lines.append(FOOTER)
    if unsubscribe_url:
        lines += ["", f"Unsubscribe: {unsubscribe_url}"]
    return "\n".join(lines)


def render_html(unsubscribe_url: str | None = None) -> str:
    body = "".join(
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.55;">{p}</p>'
        for p in PARAGRAPHS
    )
    unsub = (
        f' <a href="{unsubscribe_url}" style="color:#8a8576;text-decoration:underline;">Unsubscribe</a>.'
        if unsubscribe_url else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;background:#e7e2d6;font-family:{_SANS};color:#17160f;">
  <div style="max-width:560px;margin:0 auto;padding:28px;">
    <div style="background:#f1ede3;border:1px solid #d3cdbe;border-radius:6px;overflow:hidden;">
      <div style="background:#17160f;color:#e7e2d6;padding:30px 28px;">
        <div style="font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#a9a394;">be greedy</div>
        <div style="font-family:{_SERIF};font-size:40px;line-height:1.05;margin-top:12px;">Closing up shop</div>
      </div>
      <div style="padding:24px 28px 8px;">{body}</div>
      <div style="padding:16px 28px;background:#e7e2d6;border-top:1px solid #ddd7c8;color:#8a8576;font-size:12px;line-height:1.6;">
        {FOOTER}{unsub}
      </div>
    </div>
  </div>
</body></html>"""
