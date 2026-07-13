"""Offline tests for the employer verification engine. Run: python3 test_verify.py
All network I/O is injected — no real DNS/HTTP calls, fully deterministic."""

import sys

from verify import (compute_trust, extract_domain, is_free_mail,
                    name_matches_domain, scan_red_flags, verify_employer,
                    check_site_content, load_lists)


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


class FakeModel:
    def __init__(self, text):
        self._t = text

    def generate_content(self, prompt):
        class R: pass
        r = R(); r.text = self._t
        return r


dns_up = lambda d: True
dns_down = lambda d: False
mx_yes = lambda d: True
mx_no = lambda d: False
site_up = lambda d, timeout=6: (200, "Acme Corp is a marketing agency. " * 20)
site_down = lambda d, timeout=6: (None, "")

ok = True

# 1. Domain extraction
ok &= check("email -> domain", extract_domain("info@graylinedigital.com") == "graylinedigital.com")
ok &= check("url -> domain", extract_domain("https://www.acme.co/careers") == "acme.co")
ok &= check("junk -> None", extract_domain("call me on whatsapp") is None)
ok &= check("empty -> None", extract_domain("") is None)

# 2. Free-mail detection
ok &= check("gmail is free mail", is_free_mail("gmail.com"))
ok &= check("corporate is not", not is_free_mail("graylinedigital.com"))

# 3. Red-flag lexicon
ok &= check("fee request flagged",
            scan_red_flags("Pay a small registration fee to start") != [])
ok &= check("whatsapp-only flagged",
            scan_red_flags("Contact us on WhatsApp only") != [])
ok &= check("crypto salary flagged",
            scan_red_flags("Salary paid in USDT payment weekly") != [])
ok &= check("clean JD not flagged",
            scan_red_flags("We seek a marketing manager with 3 years experience") == [])

# 4. Name/domain matching
ok &= check("Grayline Digital ~ graylinedigital.com",
            name_matches_domain("Grayline Digital", "graylinedigital.com"))
ok &= check("Omx Digital !~ gmail.com", not name_matches_domain("Omx Digital", "gmail.com"))
ok &= check("Eco Green Developers ~ eco-greendevelopers.com",
            name_matches_domain("Eco Green Developers", "eco-greendevelopers.com"))

# 5. Deterministic scoring
s, level, ev = compute_trust({"free_mail": False, "dns": True, "mx": True,
                              "site_up": True, "name_match": True,
                              "site_content": "consistent", "red_flags": []})
ok &= check("all-good employer -> High trust (>=75)", s >= 75 and level == "High trust")

s, level, ev = compute_trust({"free_mail": True, "red_flags": []})
ok &= check("gmail-only employer -> Medium/Low", s < 50)

s, level, ev = compute_trust({"free_mail": False, "dns": True, "mx": True,
                              "site_up": True, "name_match": True,
                              "red_flags": ["asks applicants to pay a fee"]})
ok &= check("red flag caps score at 35 regardless of good signals", s <= 35)

s, level, ev = compute_trust({"no_contact": True, "red_flags": []})
ok &= check("no contact -> capped at 40, evidence says unverifiable",
            s <= 40 and any("no contact" in e for e in ev))

s, level, ev = compute_trust({"free_mail": False, "dns": False, "red_flags": []})
ok &= check("dead domain tanks the score", s < 50)

# 6. Full pipeline with fakes
v = verify_employer("Grayline Digital", "info@graylinedigital.com",
                    "Design role, portfolio required", "Graphic Designer",
                    model=FakeModel("CONSISTENT"), dns_fn=dns_up, mx_fn=mx_yes,
                    fetch_fn=site_up)
ok &= check("legit employer end-to-end -> High trust",
            v["level"] == "High trust" and v["domain"] == "graylinedigital.com")

v = verify_employer("Omx Digital", "omxdigitals@gmail.com",
                    "Video editor role", "Video Editor",
                    model=None, dns_fn=dns_up, mx_fn=mx_yes, fetch_fn=site_up)
ok &= check("gmail employer end-to-end -> below High, no site checks run",
            v["score"] < 75 and "dns" not in v["signals"])

v = verify_employer("Scammy Ltd", "scam@fakejobs.biz",
                    "No experience needed! Pay a registration fee to begin. Earn up to $500 per day",
                    "Data Entry", model=None, dns_fn=dns_down, mx_fn=mx_no, fetch_fn=site_down)
ok &= check("scam posting end-to-end -> Avoid", v["level"] == "Avoid")

v = verify_employer("Mystery Co", "", "Nice role", "", model=None)
ok &= check("no contact end-to-end -> unverified, no network calls",
            v["score"] <= 40 and v["signals"].get("no_contact"))

# 7. Caching: second call must not re-run network probes
calls = {"n": 0}
def counting_dns(d):
    calls["n"] += 1
    return True
cache = {}
for _ in range(3):
    verify_employer("Acme", "hr@acme.com", "role", "x", model=None,
                    dns_fn=counting_dns, mx_fn=mx_yes, fetch_fn=site_up, cache=cache)
ok &= check("cache prevents repeat network probes", calls["n"] == 1)

# 8. Site-content check is narrow and safe
ok &= check("site check: consistent",
            check_site_content(FakeModel("CONSISTENT"), "Acme", "VA", "x" * 200) == "consistent")
ok &= check("site check: inconsistent",
            check_site_content(FakeModel("INCONSISTENT — parked page"), "Acme", "VA", "x" * 200) == "inconsistent")
ok &= check("site check: unclear -> None",
            check_site_content(FakeModel("UNCLEAR"), "Acme", "VA", "x" * 200) is None)
ok &= check("site check: no model -> None",
            check_site_content(None, "Acme", "VA", "x" * 200) is None)
ok &= check("site check: thin content -> None",
            check_site_content(FakeModel("CONSISTENT"), "Acme", "VA", "hi") is None)

class BoomModel:
    def generate_content(self, p):
        raise RuntimeError("api down")
ok &= check("site check: model error -> None (never crashes)",
            check_site_content(BoomModel(), "Acme", "VA", "x" * 200) is None)

# 9. Shared blacklist / whitelist
lists = {"blacklist": {"fakejobs.biz"}, "whitelist": {"halojobs.co"}}

s, level, ev = compute_trust({"free_mail": False, "dns": True, "mx": True,
                              "site_up": True, "name_match": True,
                              "site_content": "consistent",
                              "blacklisted": True, "red_flags": []})
ok &= check("blacklisted domain caps score at 10 -> Avoid even with good signals",
            s <= 10 and level == "Avoid")

s_wl, _, ev = compute_trust({"free_mail": False, "dns": True,
                             "whitelisted": True, "red_flags": []})
s_plain, _, _ = compute_trust({"free_mail": False, "dns": True, "red_flags": []})
ok &= check("whitelisted domain boosts score with named evidence",
            s_wl > s_plain and any("whitelist" in e for e in ev))

s, _, _ = compute_trust({"free_mail": False, "dns": True, "mx": True,
                         "site_up": True, "whitelisted": True,
                         "red_flags": ["asks applicants to pay a fee"]})
ok &= check("whitelist never overrides red flags (cap 35 stands)", s <= 35)

v = verify_employer("Fake Jobs", "hr@fakejobs.biz", "Nice role", "x",
                    model=None, dns_fn=dns_up, mx_fn=mx_yes, fetch_fn=site_up,
                    lists=lists)
ok &= check("blacklisted employer end-to-end -> Avoid with evidence",
            v["level"] == "Avoid" and any("blacklist" in e for e in v["evidence"]))

v = verify_employer("Halo Jobs", "team@halojobs.co", "Nice role", "x",
                    model=None, dns_fn=dns_up, mx_fn=mx_yes, fetch_fn=site_up,
                    lists=lists)
ok &= check("whitelisted employer end-to-end gets the boost",
            v["signals"].get("whitelisted") is True)

# Bot-blocked sites (CDN 403 etc.) — a configured server answered, so the
# site-exists signal holds; content is unverifiable, so the LLM is never asked.
class ExplodingModel:
    def generate_content(self, prompt):
        raise AssertionError("content check must not run on a bot-blocked site")

site_403 = lambda d, timeout=6: (403, "Access denied")
v_blocked = verify_employer("Paystack", "careers@paystack.com", "", "Engineer",
                            model=ExplodingModel(), dns_fn=dns_up, mx_fn=mx_yes,
                            fetch_fn=site_403)
v_live = verify_employer("Paystack", "careers@paystack.com", "", "Engineer",
                         model=None, dns_fn=dns_up, mx_fn=mx_yes, fetch_fn=site_up)
ok &= check("403 (bot defense) -> site_up True, content check skipped",
            v_blocked["signals"]["site_up"] is True
            and v_blocked["signals"]["site_blocked"] is True
            and "site_content" not in v_blocked["signals"])
ok &= check("403 scores same as a live site with no content judgment",
            v_blocked["score"] == v_live["score"])
ok &= check("403 evidence names the bot block honestly",
            any("bot protection" in e for e in v_blocked["evidence"]))

site_404 = lambda d, timeout=6: (404, "not found")
v_404 = verify_employer("Ghost Co", "jobs@ghostco.dev", "", "",
                        model=None, dns_fn=dns_up, mx_fn=mx_yes, fetch_fn=site_404)
ok &= check("404 still counts as no reachable website",
            v_404["signals"]["site_up"] is False)
v_conn = verify_employer("Dead Co", "jobs@deadco.dev", "", "",
                         model=None, dns_fn=dns_up, mx_fn=mx_yes, fetch_fn=site_down)
ok &= check("connection failure still counts as no reachable website",
            v_conn["signals"]["site_up"] is False)

import json as _json, os as _os, tempfile as _tempfile
with _tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    _json.dump({"blacklist": ["  BadCo.COM "], "whitelist": ["good.co"]}, f)
    _tmp = f.name
loaded = load_lists(_tmp)
ok &= check("load_lists normalizes domains to lowercase/stripped",
            "badco.com" in loaded["blacklist"] and "good.co" in loaded["whitelist"])
_os.unlink(_tmp)
ok &= check("load_lists on missing file -> empty sets, never raises",
            load_lists("/nonexistent/x.json") == {"blacklist": set(), "whitelist": set()})
ok &= check("default lists file ships empty (no behavior change)",
            load_lists() == {"blacklist": set(), "whitelist": set()})

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
