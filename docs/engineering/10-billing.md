# 10 — Billing

Emploi uses **Paystack** for payments. Target market is Nigeria; Paystack settles to a Nigerian bank account on T+1 (vs Flutterwave's T+2–7), has a cleaner subscription API, and has stronger community reputation for reliability.

## Tiers

| Tier | Price (₦/mo) | Monthly draft limit | Paystack plan |
|---|---|---|---|
| Free | 0 | 10 | no Paystack plan (no row in `subscriptions` = free) |
| Pro | 3,500 | 50 | `PAYSTACK_PRO_PLAN_CODE` env var |
| Max | 7,500 | 300 (fair-use) | `PAYSTACK_MAX_PLAN_CODE` env var |

Constants live in `core.py`:
```python
TIER_LIMITS     = {"free": 10, "pro": 50, "max": 300}
TIER_PRICES_NGN = {"free": 0,  "pro": 3500, "max": 7500}
```

## Quota metric

Quota counts **successful AI draft completions** stored in `generation_log` — one row per `db.log_generation()` call, written only after both Gemini calls succeed. This is intentional:

- Applying without a draft (skip-draft) costs nothing → shouldn't count.
- Failed Gemini calls don't count (user didn't get value).
- `db.count_generations_this_month()` queries `generation_log` for rows in the current calendar month (UTC) for the user.

## `billing.py` — injectable Paystack seam

Same pattern as `verify.py` (injected `dns_fn`/`mx_fn`/`fetch_fn`). All HTTP is injectable for offline testing. Public surface:

| Function | Purpose |
|---|---|
| `initialize_transaction(secret_key, email, amount_ngn, plan_code, callback_url, metadata, post_fn)` | Open a Paystack hosted checkout. Returns `{authorization_url, access_code, reference}`. Amount converted to kobo (×100). |
| `verify_transaction(secret_key, reference, get_fn)` | Confirm a completed payment. Raises on non-success status. |
| `fetch_subscription(secret_key, subscription_code, get_fn)` | Get subscription data including `email_token` (required to cancel). |
| `disable_subscription(secret_key, subscription_code, email_token, post_fn)` | Cancel a Paystack subscription. Requires `email_token` — Paystack design prevents mass-cancel from a leaked API key alone. |
| `verify_webhook_signature(secret_key, raw_body, signature)` | HMAC-SHA512 constant-time compare against `X-Paystack-Signature`. |
| `parse_webhook_event(raw_body)` | Returns `{event, data}` or `{}` on malformed JSON. |

## Database tables

### `subscriptions`
Implicit-free pattern: **no row = free tier**. Never write a `free` row — checking `get_subscription()` returns a `free` default when the user has no row.

```sql
CREATE TABLE subscriptions (
    user_id TEXT PRIMARY KEY,
    tier TEXT NOT NULL DEFAULT 'free',    -- free | pro | max
    status TEXT NOT NULL DEFAULT 'active',-- active | past_due | canceled
    paystack_customer_code TEXT,
    paystack_subscription_code TEXT,      -- arrives via subscription.create webhook
    paystack_email TEXT,
    current_period_end TEXT,
    created_at TEXT ..., updated_at TEXT ...
);
```

`upsert_subscription(conn, user_id, **fields)` filters to known columns to prevent injection; `updated_at` is always refreshed.

### `generation_log`
One row per successful draft. Indexed `(user_id, created_at)` for fast monthly count.

## Webhook lifecycle

Paystack sends events to `POST /billing/webhook`. The endpoint verifies the HMAC signature first; unknown events return `{ok}` (idempotent). Handled events:

| Event | Action |
|---|---|
| `charge.success` | Activate subscription: `upsert_subscription(tier=..., status='active')`. Tier determined from `plan.plan_code` matched against `PAYSTACK_PRO_PLAN_CODE` / `PAYSTACK_MAX_PLAN_CODE`. |
| `subscription.create` | Record `paystack_subscription_code` (this is the only place it arrives — it's NOT in the verify-transaction response). |
| `subscription.disable` / `subscription.not_renew` | Revert to free: `upsert_subscription(tier='free', status='canceled')`. |
| `invoice.payment_failed` | Mark `status='past_due'`; UI shows "Payment failed — update your card in Settings." |

## Checkout flow

1. User clicks Upgrade in `PlanCard` or `BillingSection`.
2. `POST /billing/checkout {tier}` → `billing.initialize_transaction(...)` → returns `{authorization_url, reference}`.
3. Frontend redirects to Paystack hosted checkout (`window.location.assign(authorization_url)`).
4. On return, Paystack redirects to `WEB_APP_URL + ?billing=return&reference=...`.
5. `BillingSection` detects `billing=return` in the URL query string, calls `POST /billing/verify {reference}` to confirm, then refreshes billing status.
6. `charge.success` webhook also fires independently and is the authoritative activation signal.

## Cancel flow

1. `POST /billing/cancel` fetches the subscription (needs `email_token`), then calls `billing.disable_subscription(...)`.
2. Tier reverts to free immediately in the DB.
3. Paystack also sends `subscription.disable` webhook; the handler is idempotent.

## AI model fallback

Generation endpoints use a `FallbackModel(primary, fallback)` that transparently retries on the fallback if the primary raises:

- Primary: `TimeoutGeminiModel` — wraps `genai` with `request_options={"timeout": GENERATE_CALL_TIMEOUT_S}` (25 s).
- Fallback: `GroqModel` — `groq` SDK, 25 s timeout, `llama-3.1-70b-versatile` (or nearest current model).

`GROQ_API_KEY` env var on `emploi-api`; if absent, `GroqModel` raises and generation fails with a clear 502.

## Deployment checklist (Paystack)

Before going live:

1. Create a Paystack business account for Crost Limited.
2. In the Paystack dashboard, create two **recurring monthly** plans:
   - Pro — ₦3,500/month → copy the plan code
   - Max — ₦7,500/month → copy the plan code
3. Set on `emploi-api` (Render → Environment, `sync: false`):
   - `PAYSTACK_SECRET_KEY` — live secret key from Paystack settings
   - `PAYSTACK_PRO_PLAN_CODE` — e.g. `PLN_xxx`
   - `PAYSTACK_MAX_PLAN_CODE` — e.g. `PLN_yyy`
   - `GROQ_API_KEY` — from console.groq.com
4. Register the webhook in Paystack settings:
   - URL: `https://emploi-api.onrender.com/billing/webhook`
   - Events: `charge.success`, `subscription.create`, `subscription.disable`, `subscription.not_renew`, `invoice.payment_failed`
5. Test in Paystack **test mode** (set `PAYSTACK_SECRET_KEY` to the test key first):
   - Complete a checkout with a test card → verify tier activates
   - Trigger `subscription.disable` from the dashboard → verify reverts to free
   - Confirm quota gate (402) fires correctly at the limit
6. Switch to the live key in Render.

## Acceptance criteria

- `python3 test_billing.py` — 17 checks, all offline (injected Paystack HTTP).
- `python3 test_api.py` — quota and async generation tests pass.
- Subscribing upgrades tier; canceling reverts to free; quota 402 fires at the limit; `generation_log` row written only on success.
- `db.clear_user()` wipes `subscriptions` and `generation_log` (NDPA/GDPR).
