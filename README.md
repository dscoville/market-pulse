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

**Emails are rare by design** — one per extreme, never more than once every 7 days, and only at
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
| **Shiller CAPE** *(tilt)* | How expensive stocks are vs. a decade of earnings | Rich valuations make froth more dangerous |

CAPE is a **tilt, not a trigger**: it can move the score by at most 15 points
and never counts as a corroborating signal. It sits at the same reading for
years, so at full weight it made an ordinary day near the highs read
BE FEARFUL — and in summer 2026 that emailed every week. The market itself
has to do something unusual.

An email is sent **only if all** of these hold:
1. `|score|` ≥ `ALERT_THRESHOLD` (default **60** — a real extreme), and
2. at least `MIN_CORROBORATING` *market* signals (default **2**) agree, and
3. we haven't already alerted on this extreme: after an email, that side stays
   quiet until the score cools back inside ±`REARM_LEVEL` (default **30**) —
   **one email per episode**, however long it lasts, and
4. no alert has gone out in the last `COOLDOWN_DAYS` (default **7**).

The latch and cooldown are persisted in `state/last_alert.json`, which the
Action commits back to the repo whenever it changes.

### Backtest

```bash
python -m market_pulse.backtest                    # fetch history since 1990 and replay
python -m market_pulse.backtest --save-data hist/  # ...and cache it for offline re-runs
python -m market_pulse.backtest --data hist/
```

Replays the real engine and alert rules every trading day since 1990 and
reports how often each variant would have emailed and what the S&P did over
the following 3/6/12/24 months — including a "follow the emails" portfolio
versus simply holding. The **Backtest** GitHub Action runs it on every PR that
touches the engine and posts the table to the run summary.

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

> **Heads up:** Be Greedy runs in its **own dedicated Resend account** (the one
> where `begreedy.io` is verified) — Resend's free tier allows only one verified
> domain per account, so this can't share an account with another project's
> domain. Make sure you're configuring secrets from *that* account: the API key,
> the verified domain, and the Segment all have to live together, or Resend 403s
> with "domain is not verified" even though the domain looks green elsewhere.

1. **Get a Resend API key** at <https://resend.com/api-keys>, then **verify your
   sending domain** at <https://resend.com/domains>. A verified domain is
   **required** for the scheduled alerts: Resend rejects *Broadcasts* sent from
   the shared `onboarding@resend.dev` address with a 403. (That shared address
   works for one-off `--force`/`EMAIL_TO` tests, so a passing manual test does
   **not** prove the real Broadcast path will deliver — set `EMAIL_FROM` below.)
2. **Create an Audience** (now called a **Segment** — Resend renamed Audiences →
   Segments; a fresh account ships with a default `general` one) and copy its
   **ID** — it's the `segmentId` in the dashboard URL, e.g.
   `resend.com/audience?segmentId=1291173b-…`. Add yourself to it so you get the
   alerts too. The Broadcasts API still accepts this as `audience_id`, so it goes
   in the `RESEND_AUDIENCE_ID` secret. **Use the same account, key, and Segment
   ID as the signup Worker in `worker/`** — they must share one list.
3. In the repo, go to **Settings → Secrets and variables → Actions** and add:
   - `RESEND_API_KEY`
   - `RESEND_AUDIENCE_ID` — the Audience from step 2
   - `EMAIL_FROM` — a sender on your verified domain, e.g. `Be Greedy <alerts@begreedy.io>`. **Required** for the scheduled Broadcast; without it the run falls back to `onboarding@resend.dev` and Resend 403s every alert.
4. Under **Settings → Actions → General → Workflow permissions**, enable
   **Read and write** so the Action can commit the cooldown state back.
5. That's it. The `Be Greedy daily check` workflow runs weekday afternoons.
   Use **Actions → Run workflow → force = true** to send a test alert immediately.
   That sends a *transactional* email to `EMAIL_TO`; also tick **broadcast = true**
   to exercise the real Broadcast path (the whole Audience, from `EMAIL_FROM`) —
   the only way to prove a scheduled alert will actually deliver.

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
- **Richer "Buffett" valuation inputs:** Shiller CAPE ✅ (as a capped tilt);
  the Buffett Indicator (market cap / GDP) once a reliable free source exists.
- **A real app:** dashboard + history of past calls and how they played out.
- **Brokerage execution:** connect directly to Fidelity / Vanguard / Robinhood
  to act on signals — e.g. auto-buy on extreme fear, trim on extreme greed —
  with guardrails and explicit confirmation.

---

## Project layout

```
market_pulse/
  data.py      # fetch S&P 500 + VIX + CAPE for the daily run
  history.py   # fetch decades of history for the backtest
  signals.py   # pure, offline-testable scoring engine
  policy.py    # pure alert rules: threshold, corroboration, latch, cooldown
  backtest.py  # replay engine + rules over history
  report.py    # render the email (HTML + text)
  emailer.py   # send via Resend (stdlib only)
  state.py     # latch + cooldown persistence
  config.py    # env-var configuration
  main.py      # orchestrate: fetch → assess → maybe send
tests/         # offline unit tests for the engine
.github/workflows/daily.yml
.github/workflows/backtest.yml
```
