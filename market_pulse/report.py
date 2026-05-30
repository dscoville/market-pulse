"""Render an Assessment into an email (subject + HTML + plain text)."""

from __future__ import annotations

from .signals import Assessment

BUFFETT_QUOTES = {
    "BUY": "“Be fearful when others are greedy, and greedy when others are fearful.” — Warren Buffett",
    "TRIM": "“The most common cause of low prices is pessimism... we want to do business in such an environment, not because we like pessimism but because we like the prices it produces.” — Warren Buffett",
    "HOLD": "“The stock market is a device for transferring money from the impatient to the patient.” — Warren Buffett",
}

# Muted, elegant accents to match the landing page: sage / terracotta / warm gray.
_ACTION_COLOR = {"BUY": "#4f6b4e", "TRIM": "#a8472e", "HOLD": "#6f6a5d"}

# Email-safe display serif (Instrument Serif isn't available in most mail
# clients, so Georgia carries the same editorial feel everywhere).
_SERIF = "Georgia, 'Times New Roman', serif"
_SANS = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def subject(a: Assessment) -> str:
    if a.action == "BUY":
        return f"Be Greedy — the S&P 500 looks oversold (score {a.score:+.0f})"
    if a.action == "TRIM":
        return f"Be Fearful — the S&P 500 looks frothy (score {a.score:+.0f})"
    return f"Be Greedy: stand pat (score {a.score:+.0f})"


def render_text(a: Assessment, unsubscribe_url: str | None = None) -> str:
    lines = [
        "BE GREEDY",
        "be greedy when others are fearful",
        "",
        f"Stance:  {a.stance}  (action: {a.action})",
        f"Score:   {a.score:+.0f}  on a -100 (greed) .. +100 (fear) scale",
        f"S&P 500: {a.price:,.2f}" + (f"  as of {a.as_of}" if a.as_of else ""),
        "",
        a.headline,
        "",
        "What the data says:",
    ]
    for s in a.signals:
        arrow = {"fear": "↑buy", "greed": "↓trim", "neutral": "·"}[s.direction]
        lines.append(f"  - {s.label}: {s.display}  [{s.score:+.0f} {arrow}]")
        lines.append(f"      {s.note}")
    lines += [
        "",
        BUFFETT_QUOTES[a.action],
        "",
        "---",
        "Not financial advice. This is a heuristic signal on a broad index,",
        "for your own judgement. Be Greedy only emails at genuine extremes.",
    ]
    if unsubscribe_url:
        lines += ["", f"Unsubscribe: {unsubscribe_url}"]
    return "\n".join(lines)


def render_html(a: Assessment, unsubscribe_url: str | None = None) -> str:
    color = _ACTION_COLOR.get(a.action, "#6f6a5d")
    rows = []
    for s in a.signals:
        arrow = {"fear": "&#8593; buy", "greed": "&#8595; trim", "neutral": "&middot;"}[s.direction]
        sc = "#4f6b4e" if s.score > 0 else ("#a8472e" if s.score < 0 else "#6f6a5d")
        rows.append(
            f"""<tr>
              <td style="padding:12px 14px;border-bottom:1px solid #ddd7c8;">
                <strong style="font-weight:600;">{s.label}</strong><br>
                <span style="color:#6f6a5d;font-size:13px;">{s.note}</span>
              </td>
              <td style="padding:12px 14px;border-bottom:1px solid #ddd7c8;text-align:right;white-space:nowrap;">
                <span style="font-size:16px;">{s.display}</span><br>
                <span style="color:{sc};font-size:13px;">{s.score:+.0f} {arrow}</span>
              </td>
            </tr>"""
        )
    as_of = f" &middot; as of {a.as_of}" if a.as_of else ""
    unsub = (
        f'<br><a href="{unsubscribe_url}" style="color:#8a8576;">Unsubscribe</a>'
        if unsubscribe_url else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;background:#e7e2d6;font-family:{_SANS};color:#17160f;">
  <div style="max-width:560px;margin:0 auto;padding:28px;">
    <div style="background:#f1ede3;border:1px solid #d3cdbe;border-radius:6px;overflow:hidden;">
      <div style="background:#17160f;color:#e7e2d6;padding:30px 28px;">
        <div style="font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#a9a394;">Be Greedy &middot; be greedy when others are fearful</div>
        <div style="font-family:{_SERIF};font-size:40px;line-height:1.05;margin-top:12px;">{a.stance}</div>
        <div style="font-size:15px;margin-top:8px;color:#cac4b4;">{a.headline}</div>
      </div>
      <div style="padding:24px 28px;">
        <div style="margin-bottom:14px;font-size:15px;">
          <span style="color:#6f6a5d;">Conviction score</span>
          <strong style="float:right;font-family:{_SERIF};font-size:20px;color:{color};">{a.score:+.0f} / 100</strong>
        </div>
        <div style="margin-bottom:20px;font-size:15px;color:#6f6a5d;">
          <span>S&amp;P 500{as_of}</span>
          <strong style="float:right;color:#17160f;">{a.price:,.2f}</strong>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">{''.join(rows)}</table>
        <p style="margin:22px 0 0;font-family:{_SERIF};font-style:italic;color:#57534a;font-size:16px;line-height:1.5;">{BUFFETT_QUOTES[a.action]}</p>
      </div>
      <div style="padding:16px 28px;background:#e7e2d6;border-top:1px solid #ddd7c8;color:#8a8576;font-size:12px;line-height:1.6;">
        Not financial advice &mdash; a heuristic signal on a broad index for your own judgement.
        Be Greedy only emails at genuine extremes, and never more than once a week.{unsub}
      </div>
    </div>
  </div>
</body></html>"""
