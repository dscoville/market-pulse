"""Send the alert through the Resend API.

Two delivery paths, both stdlib-only (urllib), so the project keeps zero
runtime dependencies:

* ``send_email``     — a one-off transactional email to explicit recipients.
                       Used for local ``--force`` smoke tests when no Audience
                       is configured.
* ``send_broadcast`` — email the whole subscriber list via a Resend *Broadcast*
                       tied to an Audience. Resend handles per-recipient
                       unsubscribe links and skips anyone who opted out. This
                       is the path the daily service uses.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

RESEND_BASE = "https://api.resend.com"

# Resend replaces this token per recipient with that contact's own one-click
# unsubscribe link. It must appear in a Broadcast's content.
UNSUBSCRIBE_TOKEN = "{{{RESEND_UNSUBSCRIBE_URL}}}"


class EmailError(RuntimeError):
    pass


def _post(path: str, api_key: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{RESEND_BASE}{path}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise EmailError(f"Resend API returned {e.code} for {path}: {body}") from e
    except urllib.error.URLError as e:
        raise EmailError(f"Could not reach Resend API: {e.reason}") from e


def send_email(
    api_key: str,
    sender: str,
    recipients: list[str],
    subject: str,
    html: str,
    text: str,
    timeout: int = 30,
) -> dict:
    """Send a single transactional email to explicit recipients."""
    return _post(
        "/emails",
        api_key,
        {
            "from": sender,
            "to": recipients,
            "subject": subject,
            "html": html,
            "text": text,
        },
        timeout,
    )


def send_broadcast(
    api_key: str,
    sender: str,
    audience_id: str,
    subject: str,
    html: str,
    text: str,
    timeout: int = 30,
) -> dict:
    """Create and immediately send a Broadcast to everyone in an Audience.

    The content must contain ``UNSUBSCRIBE_TOKEN`` so Resend can inject each
    recipient's unsubscribe link; we guard against forgetting it.
    """
    if UNSUBSCRIBE_TOKEN not in html or UNSUBSCRIBE_TOKEN not in text:
        raise EmailError(
            "Broadcast content must include the unsubscribe token "
            f"{UNSUBSCRIBE_TOKEN} in both html and text."
        )
    created = _post(
        "/broadcasts",
        api_key,
        {
            "audience_id": audience_id,
            "from": sender,
            "subject": subject,
            "html": html,
            "text": text,
        },
        timeout,
    )
    broadcast_id = created.get("id")
    if not broadcast_id:
        raise EmailError(f"Resend did not return a broadcast id: {created}")
    sent = _post(f"/broadcasts/{broadcast_id}/send", api_key, {}, timeout)
    return {"broadcast_id": broadcast_id, "send": sent}
