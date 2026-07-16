"""Emploi billing — thin wrapper over Paystack's Transactions/Subscriptions
APIs. UI-free and network calls are the only side effect, so this stays
importable/mockable in tests the same way core.py/verify.py are: every
function that hits the network takes an injectable `post_fn`/`get_fn`
(defaulting to `requests`), never calls `requests` directly at the top of
a function body without that seam.

Paystack is the source of truth for subscription lifecycle; our own
`subscriptions` table is a cache of it, kept in sync via `/billing/webhook`
(authoritative) and `/billing/verify` (instant feedback right after
checkout, since the webhook can lag a few seconds).
"""
import hashlib
import hmac
import json

PAYSTACK_BASE = "https://api.paystack.co"


def _headers(secret_key: str) -> dict:
    return {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}


def initialize_transaction(secret_key: str, email: str, amount_ngn: int,
                           plan_code: str, callback_url: str,
                           metadata: dict, post_fn=None) -> dict:
    """Start a Paystack hosted-checkout transaction for a subscription plan.
    Returns Paystack's `data` object ({authorization_url, access_code,
    reference}) on success; raises on any non-2xx or Paystack-reported
    failure (`status: false` in the body) — never returns a half-valid
    result the caller might mistake for success."""
    import requests
    post_fn = post_fn or requests.post
    resp = post_fn(
        f"{PAYSTACK_BASE}/transaction/initialize",
        headers=_headers(secret_key),
        json={
            "email": email,
            "amount": amount_ngn * 100,  # Paystack amounts are in kobo
            "plan": plan_code,
            "callback_url": callback_url,
            "metadata": metadata,
        },
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status"):
        raise RuntimeError(f"Paystack initialize failed: {body.get('message', 'unknown error')}")
    return body["data"]


def initialize_onetime_transaction(secret_key: str, email: str, amount_ngn: int,
                                   callback_url: str, metadata: dict,
                                   post_fn=None) -> dict:
    """One-time (non-subscription) hosted checkout — used for employer
    unlock-credit packs. Identical contract to initialize_transaction but
    sends no plan code, so Paystack charges once and never creates a
    subscription."""
    import requests
    post_fn = post_fn or requests.post
    resp = post_fn(
        f"{PAYSTACK_BASE}/transaction/initialize",
        headers=_headers(secret_key),
        json={
            "email": email,
            "amount": amount_ngn * 100,  # kobo
            "callback_url": callback_url,
            "metadata": metadata,
        },
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status"):
        raise RuntimeError(f"Paystack initialize failed: {body.get('message', 'unknown error')}")
    return body["data"]


def verify_transaction(secret_key: str, reference: str, get_fn=None) -> dict:
    """Confirm a transaction actually succeeded. Returns Paystack's `data`
    object; raises if the transaction wasn't found or wasn't successful."""
    import requests
    get_fn = get_fn or requests.get
    resp = get_fn(f"{PAYSTACK_BASE}/transaction/verify/{reference}",
                  headers=_headers(secret_key), timeout=20)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status") or body.get("data", {}).get("status") != "success":
        raise RuntimeError("transaction not successful")
    return body["data"]


def fetch_subscription(secret_key: str, subscription_code: str, get_fn=None) -> dict:
    import requests
    get_fn = get_fn or requests.get
    resp = get_fn(f"{PAYSTACK_BASE}/subscription/{subscription_code}",
                  headers=_headers(secret_key), timeout=20)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status"):
        raise RuntimeError(f"Paystack fetch subscription failed: {body.get('message')}")
    return body["data"]


def disable_subscription(secret_key: str, subscription_code: str, email_token: str,
                         post_fn=None) -> None:
    """Cancel a subscription. Paystack requires the subscription's own
    email_token (from fetch_subscription), not the account secret key,
    as proof of intent to cancel — by design, so a leaked API key alone
    can't mass-cancel subscriptions."""
    import requests
    post_fn = post_fn or requests.post
    resp = post_fn(f"{PAYSTACK_BASE}/subscription/disable",
                   headers=_headers(secret_key),
                   json={"code": subscription_code, "token": email_token},
                   timeout=20)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status"):
        raise RuntimeError(f"Paystack disable subscription failed: {body.get('message')}")


def verify_webhook_signature(secret_key: str, raw_body: bytes, signature: str) -> bool:
    """Paystack signs webhook bodies with HMAC-SHA512 of the secret key.
    Constant-time compare — never a plain ==, which leaks timing info."""
    computed = hmac.new(secret_key.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature or "")


def parse_webhook_event(raw_body: bytes) -> dict:
    """Parse a webhook body into {event, data}. Returns {} on garbage —
    callers must treat that as 'ignore this webhook', never crash on it."""
    try:
        payload = json.loads(raw_body)
        return {"event": payload.get("event", ""), "data": payload.get("data", {})}
    except (ValueError, TypeError):
        return {}
