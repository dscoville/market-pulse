# Be Greedy — signup Worker

A tiny [Cloudflare Worker](https://workers.cloudflare.com/) that backs the
landing page's email form. It receives an email and adds it as a contact to a
**Resend Segment** (Resend renamed *Audiences* → *Segments*), so your Resend
API key never has to live in the static page.

```
landing page (GitHub Pages)  ──POST {email}──▶  this Worker  ──▶  Resend Segment
```

> **⚠️ Must match the daily-check Action.** This Worker *writes* signups to a
> Resend Segment; the `Be Greedy daily check` GitHub Action *broadcasts* to that
> same Segment. They must use the **same Resend account, API key, and Segment
> ID**, or signups land in one list while alerts go to another. Be Greedy runs
> in its **own dedicated Resend account** (where `begreedy.io` is verified) —
> Resend's free tier allows only one verified domain per account, so it can't
> share with another project's domain. The `RESEND_API_KEY` / `RESEND_AUDIENCE_ID`
> here and in the repo's GitHub Actions secrets must be identical.

## One-time setup

1. **Find your Segment** (a fresh account ships with a default `general` one).
   Open it in the dashboard and copy its **ID** — it's the `segmentId` in the
   URL, e.g. `resend.com/audience?segmentId=1291173b-…`. The Resend API still
   accepts this value as `audience_id`, which is why the env var below keeps the
   `RESEND_AUDIENCE_ID` name.

2. **Install Wrangler** (Cloudflare's CLI) and log in:
   ```bash
   npm install -g wrangler   # or use: npx wrangler ...
   wrangler login
   ```

3. **Add secrets** (from inside this `worker/` directory). Run each command on
   its own — Wrangler prompts for the value so it stays out of your shell
   history; don't pass the secret as an argument:
   ```bash
   wrangler secret put RESEND_API_KEY      # paste your Resend API key at the prompt
   wrangler secret put RESEND_AUDIENCE_ID  # paste the Segment ID from step 1
   ```

4. **Lock down the origin** — edit `wrangler.toml` so `ALLOW_ORIGIN` matches
   your published landing page (e.g. `https://begreedy.io`). Use `"*"`
   only while testing.

5. **Deploy:**
   ```bash
   wrangler deploy
   ```
   Wrangler prints the live URL, e.g.
   `https://market-pulse-subscribe.<your-subdomain>.workers.dev`.

6. **Wire up the page:** paste that URL into `SUBSCRIBE_ENDPOINT` near the
   bottom of `../docs/index.html`, then commit. Done — signups now flow into
   your Resend Segment.

## Test it

```bash
curl -X POST https://market-pulse-subscribe.<your-subdomain>.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com"}'
# => {"ok":true,"message":"You're on the list."}
```

## How this connects to the daily alert

The `Be Greedy daily check` GitHub Action sends each alert as a Resend
**Broadcast** to this same Segment — so everyone who signs up here receives the
alerts, each with their own unsubscribe link. The only requirement is that the
Action's `RESEND_API_KEY` and `RESEND_AUDIENCE_ID` secrets point at the **same
account and Segment** this Worker writes to (see the warning at the top).
