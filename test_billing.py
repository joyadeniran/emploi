"""Offline checks for billing.py (Paystack wrapper). No real network/keys —
post_fn/get_fn are injected fakes, same seam pattern as verify.py's
dns_fn/mx_fn/fetch_fn. Run: python3 test_billing.py"""
import billing

FAILURES = []


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    if not cond:
        FAILURES.append(label)


class FakeResp:
    def __init__(self, json_body, status_code=200):
        self._json = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


# ---------------- initialize_transaction ----------------
calls = []


def fake_post_ok(url, headers=None, json=None, timeout=None):
    calls.append((url, headers, json))
    return FakeResp({"status": True, "data": {
        "authorization_url": "https://checkout.paystack.com/abc123",
        "access_code": "abc123", "reference": "ref_1"}})


data = billing.initialize_transaction(
    "sk_test_x", "user@example.com", 3500, "PLN_pro",
    "https://app.emploihq.com/settings?billing=return",
    {"user_id": "u1", "tier": "pro"}, post_fn=fake_post_ok)
check("initialize_transaction posts to /transaction/initialize",
      calls[0][0] == "https://api.paystack.co/transaction/initialize")
check("initialize_transaction sends amount in kobo (x100)",
      calls[0][2]["amount"] == 350000)
check("initialize_transaction sends plan code", calls[0][2]["plan"] == "PLN_pro")
check("initialize_transaction returns authorization_url",
      data["authorization_url"] == "https://checkout.paystack.com/abc123")


def fake_post_fail(url, headers=None, json=None, timeout=None):
    return FakeResp({"status": False, "message": "Invalid plan"})


try:
    billing.initialize_transaction("sk", "u@e.com", 100, "bad", "cb", {}, post_fn=fake_post_fail)
    check("initialize_transaction raises on Paystack-reported failure", False)
except RuntimeError as exc:
    check("initialize_transaction raises on Paystack-reported failure", True)
    check("error message includes Paystack's reason", "Invalid plan" in str(exc))

# ---------------- verify_transaction ----------------
def fake_get_success(url, headers=None, timeout=None):
    return FakeResp({"status": True, "data": {
        "status": "success", "metadata": {"user_id": "u1", "tier": "pro"},
        "customer": {"customer_code": "CUS_1", "email": "user@example.com"}}})


data = billing.verify_transaction("sk", "ref_1", get_fn=fake_get_success)
check("verify_transaction returns data on success", data["status"] == "success")
check("verify_transaction preserves metadata", data["metadata"]["tier"] == "pro")


def fake_get_pending(url, headers=None, timeout=None):
    return FakeResp({"status": True, "data": {"status": "pending"}})


try:
    billing.verify_transaction("sk", "ref_2", get_fn=fake_get_pending)
    check("verify_transaction raises when not successful", False)
except RuntimeError:
    check("verify_transaction raises when not successful", True)

# ---------------- fetch_subscription / disable_subscription ----------------
def fake_get_sub(url, headers=None, timeout=None):
    return FakeResp({"status": True, "data": {"email_token": "tok_1", "status": "active"}})


sub = billing.fetch_subscription("sk", "SUB_1", get_fn=fake_get_sub)
check("fetch_subscription returns email_token", sub["email_token"] == "tok_1")

disable_calls = []


def fake_post_disable(url, headers=None, json=None, timeout=None):
    disable_calls.append(json)
    return FakeResp({"status": True})


billing.disable_subscription("sk", "SUB_1", "tok_1", post_fn=fake_post_disable)
check("disable_subscription sends code and token",
      disable_calls[0] == {"code": "SUB_1", "token": "tok_1"})

# ---------------- webhook signature + parsing ----------------
import hmac, hashlib, json as json_lib

body = b'{"event": "charge.success", "data": {"amount": 350000}}'
good_sig = hmac.new(b"sk_test_secret", body, hashlib.sha512).hexdigest()
check("verify_webhook_signature accepts a valid signature",
      billing.verify_webhook_signature("sk_test_secret", body, good_sig))
check("verify_webhook_signature rejects a wrong signature",
      not billing.verify_webhook_signature("sk_test_secret", body, "deadbeef"))
check("verify_webhook_signature rejects a missing signature",
      not billing.verify_webhook_signature("sk_test_secret", body, ""))

event = billing.parse_webhook_event(body)
check("parse_webhook_event extracts event name", event["event"] == "charge.success")
check("parse_webhook_event extracts data", event["data"]["amount"] == 350000)
check("parse_webhook_event returns {} on garbage", billing.parse_webhook_event(b"not json") == {})

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S)")
    import sys
    sys.exit(1)
print("ALL TESTS PASSED ✅")
