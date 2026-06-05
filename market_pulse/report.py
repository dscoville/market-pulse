"""Render an Assessment into an email (subject + HTML + plain text).

Written for a human, not a quant: lead with the plain-English verdict, show a
simple greed-vs-fear gauge, and explain every number in one sentence. Mirrors
the email preview on the landing page.
"""

from __future__ import annotations

import re

from .signals import Assessment

BUFFETT_QUOTES = {
    "BUY": "“Be fearful when others are greedy, and greedy when others are fearful.” — Warren Buffett",
    "TRIM": "“The most common cause of low prices is pessimism… we want to do business in such an environment, not because we like pessimism but because we like the prices it produces.” — Warren Buffett",
    "HOLD": "“The stock market is a device for transferring money from the impatient to the patient.” — Warren Buffett",
}

# Muted, elegant accents to match the landing page: sage / terracotta / warm gray.
_ACTION_COLOR = {"BUY": "#4f6b4e", "TRIM": "#a8472e", "HOLD": "#6f6a5d"}

# Email-safe display serif (Instrument Serif isn't available in most mail
# clients, so Georgia carries the same editorial feel everywhere).
_SERIF = "Georgia, 'Times New Roman', serif"
_SANS = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Plain-English "here's what's going on" paragraph for each stance.
_SUMMARY = {
    "BE GREEDY":
        "Stocks have sold off hard and fear is running high — historically the "
        "kind of moment that rewards buyers. This is a rare “be greedy” signal.",
    "LEAN IN":
        "Fear is building and prices are starting to look cheap. Not a screaming "
        "buy, but a moment worth considering adding a little.",
    "STAND PAT":
        "Nothing unusual is happening — the market is behaving normally. The "
        "smart move here is almost always to do nothing.",
    "TRIM A LITTLE":
        "Stocks are running a bit hot and look expensive. Nothing alarming, but "
        "it’s a moment to be cautious rather than greedy — you might trim a little.",
    "BE FEARFUL":
        "The market is euphoric and stretched — the kind of greed that often "
        "comes before a pullback. A rare “be fearful” signal; consider taking "
        "a little off the top.",
}

# What the reader should actually consider doing.
_WHAT_TO_DO = {
    "BUY": "What this means for you: a window to consider buying while others are afraid.",
    "TRIM": "What this means for you: a moment to be cautious — maybe trim, don’t chase.",
    "HOLD": "What this means for you: nothing to do. Sit tight.",
}


def subject(a: Assessment) -> str:
    if a.action == "BUY":
        return "Be Greedy — the market is fearful and stocks look cheap"
    if a.action == "TRIM":
        return "Be Fearful — the market is greedy and stocks look expensive"
    return "Be Greedy: nothing unusual — stand pat"


def _reading(score: float) -> str:
    """Plain word for where we sit on the greed↔fear scale."""
    if score >= 60:
        return "Extreme Fear"
    if score >= 40:
        return "Fear"
    if score <= -60:
        return "Extreme Greed"
    if score <= -40:
        return "Greed"
    return "Normal"


def _num(display: str) -> float:
    """Pull the leading number out of a display string like '+11.0%' or '15.3'."""
    m = re.search(r"-?\d+(?:\.\d+)?", display.replace(",", ""))
    return float(m.group()) if m else 0.0


def _plain_signal(key: str, display: str) -> str:
    """One plain-English sentence explaining a signal's reading."""
    v = _num(display)
    if key == "drawdown":
        if v <= -10:
            return f"Down {abs(v):.0f}% from its 1-year high — a real sell-off; stocks are on sale."
        if v <= -3:
            return f"Down a modest {abs(v):.0f}% from its 1-year high."
        return "Right at its 1-year high — no pullback to buy."
    if key == "rsi":
        if v >= 70:
            return f"Overbought (RSI {v:.0f}) — buyers have piled in; momentum looks stretched."
        if v <= 30:
            return f"Oversold (RSI {v:.0f}) — heavy selling; momentum looks washed out."
        return f"Momentum is middling (RSI {v:.0f}) — nothing extreme."
    if key == "trend":
        if v >= 3:
            return f"Trading {v:.0f}% above its 200-day average — stretched above its long-term trend."
        if v <= -3:
            return f"Trading {abs(v):.0f}% below its 200-day average — at a discount to its long-term trend."
        return "Right around its 200-day average — on trend."
    if key == "range":
        if v >= 85:
            return "Near the very top of its 12-month price range."
        if v <= 15:
            return "Near the bottom of its 12-month range — close to its lows."
        return "Mid-way through its 12-month price range."
    if key == "vix":
        if v < 13:
            return f"Volatility is very low (VIX {v:.0f}) — investors are calm, even complacent."
        if v < 20:
            return f"Volatility is normal (VIX {v:.0f})."
        if v < 30:
            return f"Volatility is elevated (VIX {v:.0f}) — nerves are showing."
        return f"Volatility is high (VIX {v:.0f}) — real fear in the market."
    return ""


def render_text(a: Assessment, unsubscribe_url: str | None = None) -> str:
    lines = [
        "BE GREEDY — be greedy when others are fearful",
        "",
        f">> {a.stance}",
        "",
        _SUMMARY.get(a.stance, a.headline),
        "",
        f"Reading: {_reading(a.score)}  (on a Greed <-> Fear scale)",
        f"S&P 500: {a.price:,.2f}" + (f"  as of {a.as_of}" if a.as_of else ""),
        "",
        "Why:",
    ]
    for s in a.signals:
        lines.append(f"  • {_plain_signal(s.key, s.display) or s.note}")
    lines += [
        "",
        _WHAT_TO_DO.get(a.action, ""),
        "",
        BUFFETT_QUOTES[a.action],
        "",
        "---",
        "Not financial advice — a simple read on the whole US market to inform",
        "your own judgement. We only email at genuine extremes, never more than",
        "once a week.",
    ]
    if unsubscribe_url:
        lines += [
            "",
            "You're receiving this because you subscribed to Be Greedy alerts.",
            f"Unsubscribe anytime: {unsubscribe_url}",
        ]
    return "\n".join(lines)


def _gauge_html(score: float, color: str) -> str:
    """Five labelled zones from Greed (left) to Fear (right), active one lit."""
    zones = [
        ("Extreme<br>Greed", -100, -60),
        ("Greed", -60, -40),
        ("Normal", -40, 40),
        ("Fear", 40, 60),
        ("Extreme<br>Fear", 60, 101),
    ]
    cells = []
    for label, lo, hi in zones:
        active = lo <= score < hi
        bg = color if active else "#e3ddcd"
        fg = "#fff" if active else "#8a8576"
        mark = "▲ now<br>" if active else ""
        cells.append(
            f'<td style="background:{bg};color:{fg};padding:7px 3px;text-align:center;'
            f'font-size:10px;line-height:1.25;font-weight:{600 if active else 400};border-radius:6px;">'
            f"{mark}{label}</td>"
        )
    return (
        '<table style="width:100%;border-collapse:separate;border-spacing:3px;margin:4px 0 18px;">'
        f"<tr>{''.join(cells)}</tr></table>"
    )


def render_html(a: Assessment, unsubscribe_url: str | None = None) -> str:
    color = _ACTION_COLOR.get(a.action, "#6f6a5d")
    why = "".join(
        f'<li style="padding:9px 0;border-bottom:1px solid #ddd7c8;line-height:1.45;font-size:14px;">'
        f"{_plain_signal(s.key, s.display) or s.note}</li>"
        for s in a.signals
    )
    as_of = f" &middot; as of {a.as_of}" if a.as_of else ""
    unsub = (
        '<div style="margin-top:10px;padding-top:10px;border-top:1px solid #ddd7c8;">'
        "You&rsquo;re receiving this because you subscribed to Be Greedy alerts. "
        f'<a href="{unsubscribe_url}" style="color:#8a8576;text-decoration:underline;">Unsubscribe</a>.'
        "</div>"
        if unsubscribe_url else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;background:#e7e2d6;font-family:{_SANS};color:#17160f;">
  <div style="max-width:560px;margin:0 auto;padding:28px;">
    <div style="background:#f1ede3;border:1px solid #d3cdbe;border-radius:6px;overflow:hidden;">
      <div style="background:#17160f;color:#e7e2d6;padding:30px 28px;">
        <div style="font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#a9a394;">be greedy when others are fearful</div>
        <div style="font-family:{_SERIF};font-size:40px;line-height:1.05;margin-top:12px;">{a.stance}</div>
      </div>
      <div style="padding:24px 28px;">
        <p style="margin:0 0 18px;font-size:16px;line-height:1.55;">{_SUMMARY.get(a.stance, a.headline)}</p>
        {_gauge_html(a.score, color)}
        <div style="margin-bottom:18px;font-size:14px;color:#6f6a5d;">
          <span>S&amp;P 500{as_of}</span>
          <strong style="float:right;color:#17160f;">{a.price:,.2f}</strong>
        </div>
        <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#8a8576;margin-bottom:2px;">Why</div>
        <ul style="list-style:none;padding:0;margin:0;">{why}</ul>
        <p style="margin:20px 0 0;font-size:15px;font-weight:600;">{_WHAT_TO_DO.get(a.action, '')}</p>
        <p style="margin:16px 0 0;font-family:{_SERIF};font-style:italic;color:#57534a;font-size:16px;line-height:1.5;">{BUFFETT_QUOTES[a.action]}</p>
      </div>
      <div style="padding:16px 28px;background:#e7e2d6;border-top:1px solid #ddd7c8;color:#8a8576;font-size:12px;line-height:1.6;">
        Not financial advice &mdash; a simple read on the whole US market to inform your own judgement.
        We only email at genuine extremes, never more than once a week.{unsub}
      </div>
    </div>
  </div>
</body></html>"""
