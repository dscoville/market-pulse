# Be Greedy 📈

**be greedy when others are fearful**

> *"Be fearful when others are greedy, and greedy when others are fearful."* — Warren Buffett

Be Greedy watches the broad US market and emails you **only when things are
genuinely out of whack** — a fear-driven sell-off worth buying into, or a
greed-driven melt-up worth trimming. The rest of the time it stays quiet, which
is most of the time. That silence is the feature.

- 🟢 **BE GREEDY** — the market is oversold and panicked. A buying window.
- 🔴 **BE FEARFUL** — the market is frothy and euphoric. Consider taking a little off the top.
- ⚪️ **STAND PAT** — nothing unusual. No email. Do nothing.

**Emails are rare by design** — never more than once every 7 days, and only at
real extremes.

---

## How it works

Every weekday after the US close, a GitHub Action pulls daily price history for
the **S&P 500** and the **VIX** (keyless — from Stooq, falling back to Yahoo
Finance if Stooq rate-limits the runner), then scores the market on
a single conviction scale:

```
   +100  ······  extreme FEAR    →  BE GREEDY (buy)
      0  ······  business as usual →  STAND PAT
   -100  ······  extreme GREED   →  BE FEARFUL (trim)
```

The score blends several orthogonal signals so no single noisy reading can trip
an alert on its own:

| Signal | What it captures | Buffett read |
| --- | --- | --- |
| **Drawdown from 1-yr high** | How far the index has fallen | Deep declines put great businesses on sale |
| **14-day RSI** | Momentum extreme | Oversold = panic selling; overbought = euphoria |
| **Distance from 200-day avg** | Trend stretch | Far below = bargain; far above = stretched |
| **Position in 52-week range** | Where price sits low→high | Near lows the crowd is fearful; near highs, greedy |
| **VIX (fear gauge)** | Volatility / fear | A spiking VIX is the market screaming |

An email is sent **only if all** of these hold:
1. `|score|` ≥ `ALERT_THRESHOLD` (default **60** — a real extreme), and
2. at least `MIN_CORROBORATING` signals (default **2**) agree, and
3. no alert has gone out in the last `COOLDOWN_DAYS` (default **7**).

The cooldown is persisted in `state/last_alert.json`, which the Action commits
back to the repo after each run.

> ⚠️ **Not financial advice.** This is a heuristic on a broad index to inform
> *your own* judgement — not an instruction.

---

## Quick start (local)

No runtime dependencies — pure Python standard library.

```bash
# See today's read without sending anything:
python -m market_pulse.main --report

# Test the full email path (needs RESEND_API_KEY + EMAIL_TO; ignores limits):
cp .env.example .env   # fill in your values, then export them
python -m market_pulse.main --force
```

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest
```

---

## Hosted setup (GitHub Actions)

Be Greedy emails **a list of subscribers** — you're just the first name on
it. When an alert fires it goes out as a Resend **Broadcast** to everyone in
your Audience, each with their own unsubscribe link.

1. **Get a Resend API key** at <https://resend.com/api-keys>. For testing you can
   send from `onboarding@resend.dev`; for production, verify your own domain.
2. **Create an Audience** at <https://resend.com/audiences> (this is the
   subscriber list) and copy its **Audience ID**. Add yourself to it so you get
   the alerts too.
3. In the repo, go to **Settings → Secrets and variables → Actions** and add:
   - `RESEND_API_KEY`
   - `RESEND_AUDIENCE_ID` — the Audience from step 2
   - `EMAIL_FROM` *(optional)* — e.g. `Be Greedy <alerts@begreedy.io>` (the domain must be verified in Resend)
4. Under **Settings → Actions → General → Workflow permissions**, enable
   **Read and write** so the Action can commit the cooldown state back.
5. That's it. The `Be Greedy daily check` workflow runs weekday afternoons.
   Use **Actions → Run workflow → force = true** to send a test alert immediately.

> **Local testing without a list:** set `EMAIL_TO` (and no `RESEND_AUDIENCE_ID`)
> to send a one-off email to yourself via `python -m market_pulse.main --force`.

### Tuning

All knobs are environment variables (see `.env.example`):

| Var | Default | Meaning |
| --- | --- | --- |
| `ALERT_THRESHOLD` | `60` | Higher = rarer, stronger-conviction alerts |
| `MIN_CORROBORATING` | `2` | Signals that must agree before alerting |
| `COOLDOWN_DAYS` | `7` | Minimum gap between emails |

---

## Landing page + signups

There's a public landing page in [`docs/`](docs/index.html) (servable via
**GitHub Pages → Settings → Pages → Source: `main` / `/docs`**) where visitors
can subscribe with their email. Because the page is static, the email form
POSTs to a small **Cloudflare Worker** ([`worker/`](worker/README.md)) that
holds the Resend key and adds the address to a **Resend Audience** — so the API
key never touches the browser.

```
docs/index.html (GitHub Pages)  ──POST {email}──▶  worker/  ──▶  Resend Audience
                                                                       │
                            daily check ── if extreme ── Broadcast ────┘──▶ every subscriber
```

The same Audience is both ends of the loop: the landing page adds people to it,
and the daily check broadcasts the alert to everyone on it. See
[`worker/README.md`](worker/README.md) for the one-time deploy steps, then paste
the Worker URL into `SUBSCRIBE_ENDPOINT` in `docs/index.html`.

---

## Roadmap

- **P0 (this repo):** rare, high-conviction email alerts. ✅
- **Richer "Buffett" valuation inputs:** Shiller CAPE and the Buffett Indicator
  (market cap / GDP) as additional greed/fear signals.
- **A real app:** dashboard + history of past calls and how they played out.
- **Brokerage execution:** connect directly to Fidelity / Vanguard / Robinhood
  to act on signals — e.g. auto-buy on extreme fear, trim on extreme greed —
  with guardrails and explicit confirmation.

---

## Project layout

```
market_pulse/
  data.py      # fetch S&P 500 + VIX (the only networked module)
  signals.py   # pure, offline-testable scoring engine
  report.py    # render the email (HTML + text)
  emailer.py   # send via Resend (stdlib only)
  state.py     # cooldown persistence
  config.py    # env-var configuration
  main.py      # orchestrate: fetch → assess → maybe send
tests/         # offline unit tests for the engine
.github/workflows/daily.yml
```
