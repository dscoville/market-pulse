# Be Greedy — running TODO

A living list of follow-ups and "someday" items. Add freely; check off when done.

## Open

- [ ] **Move the signup endpoint off the default `*.workers.dev` URL.**
  The landing page form POSTs to
  `https://market-pulse-subscribe.davidscoville.workers.dev`, which is public by
  necessity but exposes the username "davidscoville". Put the Worker behind a
  custom route on the brand domain (e.g. `api.begreedy.io` or
  `begreedy.io/subscribe`) via Cloudflare, then update `SUBSCRIBE_ENDPOINT` in
  `docs/index.html`. Cosmetic / privacy, not a security hole.

- [ ] **Branded email sender.** Alerts currently send from Resend's shared
  `onboarding@resend.dev`. Sending from `alerts@begreedy.io` needs a verified
  domain in Resend — but the free tier only allows one verified domain and it's
  used by the `unseen.movie` project ($20/mo to add a second). Alternative: move
  this project's email to a free provider that allows a custom domain
  (MailerSend, Brevo, or AWS SES). Requires a small change to `emailer.py`.

## Done

- [x] Rebrand "Market Pulse / What Would Warren Buffett Do?" → "Be Greedy".
- [x] Redesign landing page + alert email (cream/serif, muted palette).
- [x] Tabbed email preview on the homepage.
- [x] Detailed methodology page (`docs/methodology.html`).
- [x] Custom domain `begreedy.io` (GitHub Pages, HTTPS enforced).
- [x] Animated guilloché background + golden-brown favicon.
