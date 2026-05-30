# Market Pulse — signup Worker

A tiny [Cloudflare Worker](https://workers.cloudflare.com/) that backs the
landing page's email form. It receives an email and adds it as a contact to a
**Resend Audience**, so your Resend API key never has to live in the static
page.

```
landing page (GitHub Pages)  ──POST {email}──▶  this Worker  ──▶  Resend Audience
```

## One-time setup

1. **Create a Resend Audience** at <https://resend.com/audiences> and copy its
   **Audience ID**.

2. **Install Wrangler** (Cloudflare's CLI) and log in:
   ```bash
   npm install -g wrangler   # or use: npx wrangler ...
   wrangler login
   ```

3. **Add secrets** (from inside this `worker/` directory):
   ```bash
   wrangler secret put RESEND_API_KEY      # your Resend API key
   wrangler secret put RESEND_AUDIENCE_ID  # the Audience ID from step 1
   ```

4. **Lock down the origin** — edit `wrangler.toml` so `ALLOW_ORIGIN` matches
   your published landing page (e.g. `https://dscoville.github.io`). Use `"*"`
   only while testing.

5. **Deploy:**
   ```bash
   wrangler deploy
   ```
   Wrangler prints the live URL, e.g.
   `https://market-pulse-subscribe.<your-subdomain>.workers.dev`.

6. **Wire up the page:** paste that URL into `SUBSCRIBE_ENDPOINT` near the
   bottom of `../docs/index.html`, then commit. Done — signups now flow into
   your Resend Audience.

## Test it

```bash
curl -X POST https://market-pulse-subscribe.<your-subdomain>.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com"}'
# => {"ok":true,"message":"You're on the list."}
```

## Next step (out of scope here)

The daily GitHub Action currently emails the single `EMAIL_TO` address. To mail
the whole list, have it read contacts from this same Resend Audience
(`GET /audiences/{id}/contacts`) and send to each. That's the next milestone.
