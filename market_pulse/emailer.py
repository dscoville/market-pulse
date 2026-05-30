"""Send the alert through the Resend transactional email API.

Uses only the standard library (urllib) so the project has zero runtime
dependencies.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

RESEND_URL = "https://api.resend.com/emails"


class EmailError(RuntimeError):
    pass


def send_email(
    api_key: str,
    sender: str,
    recipients: list[str],
    subject: str,
    html: str,
    text: str,
    timeout: int = 30,
) -> dict:
    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
        "text": text,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_URL,
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
        raise EmailError(f"Resend API returned {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise EmailError(f"Could not reach Resend API: {e.reason}") from e
