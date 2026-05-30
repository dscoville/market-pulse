"""Entry point: fetch data, assess the market, and email only at extremes.

Run locally:
    python -m market_pulse.main              # fetch, assess, maybe send
    python -m market_pulse.main --report      # print the report, never send
    python -m market_pulse.main --force       # ignore threshold + cooldown (test the pipe)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import data, report
from .config import Config
from .emailer import EmailError, send_email
from .signals import Assessment, evaluate
from .state import cooldown_active, load_state, save_state


def assess() -> Assessment:
    sp_dates, sp_closes = data.fetch_closes("sp500")
    as_of = sp_dates[-1] if sp_dates else ""
    try:
        _, vix_closes = data.fetch_closes("vix")
    except Exception as e:  # VIX is a nice-to-have; degrade gracefully
        print(f"warning: could not fetch VIX ({e}); proceeding without it", file=sys.stderr)
        vix_closes = None
    return evaluate(sp_closes, vix_closes=vix_closes, as_of=as_of)


def decide(a: Assessment, cfg: Config, state: dict) -> tuple[bool, str]:
    """Return (should_send, reason)."""
    if cfg.force:
        return True, "forced"
    if a.action == "HOLD":
        return False, "market is not out of whack (HOLD)"
    if abs(a.score) < cfg.alert_threshold:
        return False, f"|score| {abs(a.score):.0f} below threshold {cfg.alert_threshold:.0f}"
    if a.corroborating() < cfg.min_corroborating:
        return False, f"only {a.corroborating()} corroborating signals (need {cfg.min_corroborating})"
    if cooldown_active(state, cfg.cooldown_days):
        return False, f"cooldown active (last alert < {cfg.cooldown_days} days ago)"
    return True, "extreme reached and cooldown clear"


def run(cfg: Config, report_only: bool = False) -> int:
    a = assess()
    text = report.render_text(a)
    print(text)
    print()

    if report_only:
        return 0

    state = load_state(cfg.state_file)
    should_send, reason = decide(a, cfg, state)
    print(f"decision: {'SEND' if should_send else 'skip'} — {reason}")

    if not should_send:
        return 0

    if cfg.dry_run:
        print("DRY_RUN set — not actually sending.")
        return 0
    if not cfg.can_send:
        print("RESEND_API_KEY / EMAIL_TO not configured — cannot send.", file=sys.stderr)
        return 0

    try:
        result = send_email(
            cfg.resend_api_key, cfg.email_from, cfg.email_to,
            report.subject(a), report.render_html(a), text,
        )
    except EmailError as e:
        print(f"error sending email: {e}", file=sys.stderr)
        return 1

    print(f"sent: {result}")
    state["last_alert_at"] = datetime.now(timezone.utc).isoformat()
    state["last_alert_score"] = round(a.score, 1)
    state["last_alert_action"] = a.action
    save_state(cfg.state_file, state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Market Pulse — Buffett-style market extreme alerts")
    parser.add_argument("--report", action="store_true", help="print the assessment and exit (never send)")
    parser.add_argument("--force", action="store_true", help="ignore threshold + cooldown and send")
    parser.add_argument("--dry-run", action="store_true", help="run the send path but don't deliver")
    args = parser.parse_args(argv)

    cfg = Config.from_env()
    if args.force:
        cfg.force = True
    if args.dry_run:
        cfg.dry_run = True
    return run(cfg, report_only=args.report)


if __name__ == "__main__":
    raise SystemExit(main())
