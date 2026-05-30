/**
 * Market Pulse — signup endpoint (Cloudflare Worker).
 *
 * Receives an email from the static landing page and stores it as a contact
 * in a Resend Audience. The Resend API key never leaves the server, so the
 * landing page can stay a plain static file on GitHub Pages.
 *
 * Expected secrets / vars (set with `wrangler secret put` or in the dashboard):
 *   RESEND_API_KEY      — your Resend API key
 *   RESEND_AUDIENCE_ID  — the audience to add contacts to
 *   ALLOW_ORIGIN        — the site allowed to call this (e.g.
 *                         "https://dscoville.github.io"); defaults to "*"
 */

const RESEND_API = "https://api.resend.com";

// Pragmatic email check: one @, a dot in the domain, no spaces. Real
// validation is "can we deliver to it", which only the send proves.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOW_ORIGIN || "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

function json(body, status, env) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(env) },
  });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }
    if (request.method !== "POST") {
      return json({ error: "Method not allowed." }, 405, env);
    }
    if (!env.RESEND_API_KEY || !env.RESEND_AUDIENCE_ID) {
      return json({ error: "Server is not configured." }, 500, env);
    }

    let email;
    try {
      const data = await request.json();
      email = (data.email || "").trim().toLowerCase();
    } catch {
      return json({ error: "Send JSON like { \"email\": \"you@example.com\" }." }, 400, env);
    }

    if (!EMAIL_RE.test(email)) {
      return json({ error: "That doesn't look like a valid email." }, 400, env);
    }

    const res = await fetch(
      `${RESEND_API}/audiences/${env.RESEND_AUDIENCE_ID}/contacts`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, unsubscribed: false }),
      },
    );

    // Resend returns 201 on create. Adding an email that's already a contact
    // also comes back OK — we treat "you're on the list" as success either way.
    if (res.ok) {
      return json({ ok: true, message: "You're on the list." }, 200, env);
    }

    const detail = await res.text();
    console.error("Resend contact create failed:", res.status, detail);
    return json({ error: "Could not add you right now. Try again shortly." }, 502, env);
  },
};
