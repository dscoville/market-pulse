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
from . import data, farewell, report
from .config import Config
from .emailer import UNSUBSCRIBE_TOKEN, EmailError, send_broadcast, send_email
from .policy import decide, rearm, record_alert
from .signals import Assessment, evaluate
from .state import load_state, save_state


def assess() -> Assessment:
    sp_dates, sp_closes = data.fetch_closes("sp500")
    as_of = sp_dates[-1] if sp_dates else ""
    try:
        _, vix_closes = data.fetch_closes("vix")
    except Exception as e:  # VIX is a nice-to-have; degrade gracefully
        print(f"warning: could not fetch VIX ({e}); proceeding without it", file=sys.stderr)
        vix_closes = None

    # Valuation gauges are slow-moving and best-effort: if a source is down we
    # just leave that signal out rather than fail the run.
    cape = data.fetch_cape()
    if cape is None:
        print("warning: Shiller CAPE unavailable; proceeding without it", file=sys.stderr)

    # The Buffett Indicator needs total US market cap; the free Wilshire 5000
    # feed on FRED was discontinued (every series 404s), so we lean on CAPE for
    # valuation until a reliable source is wired in. The engine still accepts a
    # buffett_indicator value if one becomes available.
    return evaluate(sp_closes, vix_closes=vix_closes, as_of=as_of, cape=cape)


def run(cfg: Config, report_only: bool = False) -> int:
    a = assess()
    text = report.render_text(a)
    print(text)
    print()

    if report_only:
        return 0

    state = load_state(cfg.state_file)
    if rearm(state, a.score, cfg.rearm_level):
        # Persist the latch change even if we don't send, so the Action
        # commits it and tomorrow's run sees the re-armed side.
        save_state(cfg.state_file, state)
    should_send, reason = decide(a, cfg, state)
    print(f"decision: {'SEND' if should_send else 'skip'} — {reason}")

    if not should_send:
        return 0

    if cfg.dry_run:
        print("DRY_RUN set — not actually sending.")
        return 0
    if cfg.send_mode is None:
        print(
            "Cannot send: need RESEND_API_KEY plus either RESEND_AUDIENCE_ID "
            "(the subscriber list) or EMAIL_TO (for testing).",
            file=sys.stderr,
        )
        return 0

    try:
        if cfg.send_mode == "broadcast":
            # Email the whole subscriber list; Resend injects each contact's
            # own unsubscribe link in place of the token.
            html = report.render_html(a, unsubscribe_url=UNSUBSCRIBE_TOKEN)
            broadcast_text = report.render_text(a, unsubscribe_url=UNSUBSCRIBE_TOKEN)
            result = send_broadcast(
                cfg.resend_api_key, cfg.email_from, cfg.audience_id,
                report.subject(a), html, broadcast_text,
            )
        else:
            result = send_email(
                cfg.resend_api_key, cfg.email_from, cfg.email_to,
                report.subject(a), report.render_html(a), text,
            )
    except EmailError as e:
        print(f"error sending email: {e}", file=sys.stderr)
        return 1

    print(f"sent ({cfg.send_mode}): {result}")
    record_alert(state, a)
    save_state(cfg.state_file, state)
    return 0


def send_farewell(cfg: Config) -> int:
    """Send the one-time goodbye email. Refuses a second send unless forced."""
    state = load_state(cfg.state_file)
    if state.get("farewell_sent_at") and not cfg.force:
        print(f"farewell already sent at {state['farewell_sent_at']} — not sending again.")
        return 0
    print(farewell.render_text())
    print()
    if cfg.dry_run:
        print("DRY_RUN set — not actually sending.")
        return 0
    if cfg.send_mode is None:
        print("Cannot send: need RESEND_API_KEY plus RESEND_AUDIENCE_ID or EMAIL_TO.", file=sys.stderr)
        return 1
    try:
        if cfg.send_mode == "broadcast":
            result = send_broadcast(
                cfg.resend_api_key, cfg.email_from, cfg.audience_id, farewell.SUBJECT,
                farewell.render_html(UNSUBSCRIBE_TOKEN), farewell.render_text(UNSUBSCRIBE_TOKEN),
            )
        else:
            result = send_email(
                cfg.resend_api_key, cfg.email_from, cfg.email_to, farewell.SUBJECT,
                farewell.render_html(), farewell.render_text(),
            )
    except EmailError as e:
        print(f"error sending farewell: {e}", file=sys.stderr)
        return 1
    print(f"sent farewell ({cfg.send_mode}): {result}")
    if cfg.send_mode == "broadcast":  # a direct test send shouldn't burn the one-shot
        state["farewell_sent_at"] = datetime.now(timezone.utc).isoformat()
        save_state(cfg.state_file, state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Be Greedy — contrarian market extreme alerts")
    parser.add_argument("--report", action="store_true", help="print the assessment and exit (never send)")
    parser.add_argument("--force", action="store_true", help="ignore threshold + cooldown and send")
    parser.add_argument("--dry-run", action="store_true", help="run the send path but don't deliver")
    parser.add_argument("--farewell", action="store_true", help="send the one-time goodbye email instead of an alert")
    args = parser.parse_args(argv)

    cfg = Config.from_env()
    if args.force:
        cfg.force = True
    if args.dry_run:
        cfg.dry_run = True
    if args.farewell:
        return send_farewell(cfg)
    return run(cfg, report_only=args.report)


if __name__ == "__main__":
    raise SystemExit(main())
