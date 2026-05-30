"""Render an Assessment into an email (subject + HTML + plain text)."""

from __future__ import annotations

from .signals import Assessment

BUFFETT_QUOTES = {
    "BUY": "“Be fearful when others are greedy, and greedy when others are fearful.” — Warren Buffett",
    "TRIM": "“The most common cause of low prices is pessimism... we want to do business in such an environment, not because we like pessimism but because we like the prices it produces.” — Warren Buffett",
    "HOLD": "“The stock market is a device for transferring money from the impatient to the patient.” — Warren Buffett",
}

_ACTION_COLOR = {"BUY": "#1a7f37", "TRIM": "#b35900", "HOLD": "#57606a"}


def subject(a: Assessment) -> str:
    if a.action == "BUY":
        return f"\U0001F7E2 Market Pulse: BE GREEDY — S&P 500 looks oversold (score {a.score:+.0f})"
    if a.action == "TRIM":
        return f"\U0001F534 Market Pulse: BE FEARFUL — S&P 500 looks frothy (score {a.score:+.0f})"
    return f"Market Pulse: stand pat (score {a.score:+.0f})"


def render_text(a: Assessment, unsubscribe_url: str | None = None) -> str:
    lines = [
        "MARKET PULSE",
        "What Would Warren Buffett Do?",
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
        "for your own judgement. Market Pulse only emails at genuine extremes.",
    ]
    if unsubscribe_url:
        lines += ["", f"Unsubscribe: {unsubscribe_url}"]
    return "\n".join(lines)


def render_html(a: Assessment, unsubscribe_url: str | None = None) -> str:
    color = _ACTION_COLOR.get(a.action, "#57606a")
    rows = []
    for s in a.signals:
        arrow = {"fear": "&#8593; buy", "greed": "&#8595; trim", "neutral": "&middot;"}[s.direction]
        sc = "#1a7f37" if s.score > 0 else ("#b35900" if s.score < 0 else "#57606a")
        rows.append(
            f"""<tr>
              <td style="padding:8px 12px;border-bottom:1px solid #eaecef;">
                <strong>{s.label}</strong><br>
                <span style="color:#57606a;font-size:13px;">{s.note}</span>
              </td>
              <td style="padding:8px 12px;border-bottom:1px solid #eaecef;text-align:right;white-space:nowrap;">
                <span style="font-size:16px;">{s.display}</span><br>
                <span style="color:{sc};font-size:13px;">{s.score:+.0f} {arrow}</span>
              </td>
            </tr>"""
        )
    as_of = f" &middot; as of {a.as_of}" if a.as_of else ""
    unsub = (
        f'<br><a href="{unsubscribe_url}" style="color:#8b949e;">Unsubscribe</a>'
        if unsubscribe_url else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;background:#f6f8fa;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#24292f;">
  <div style="max-width:560px;margin:0 auto;padding:24px;">
    <div style="background:#fff;border:1px solid #d0d7de;border-radius:12px;overflow:hidden;">
      <div style="background:{color};color:#fff;padding:20px 24px;">
        <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;">Market Pulse &middot; What Would Warren Buffett Do?</div>
        <div style="font-size:26px;font-weight:700;margin-top:6px;">{a.stance}</div>
        <div style="font-size:15px;margin-top:4px;opacity:.95;">{a.headline}</div>
      </div>
      <div style="padding:20px 24px;">
        <div style="display:flex;justify-content:space-between;font-size:15px;margin-bottom:14px;">
          <span>Conviction score</span>
          <strong style="color:{color};">{a.score:+.0f} / 100</strong>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:15px;margin-bottom:18px;color:#57606a;">
          <span>S&amp;P 500{as_of}</span>
          <strong style="color:#24292f;">{a.price:,.2f}</strong>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">{''.join(rows)}</table>
        <p style="margin:18px 0 0;font-style:italic;color:#57606a;font-size:14px;">{BUFFETT_QUOTES[a.action]}</p>
      </div>
      <div style="padding:14px 24px;background:#f6f8fa;border-top:1px solid #eaecef;color:#8b949e;font-size:12px;">
        Not financial advice &mdash; a heuristic signal on a broad index for your own judgement.
        Market Pulse only emails at genuine extremes, and never more than once a week.{unsub}
      </div>
    </div>
  </div>
</body></html>"""
