"""Emploi employer verification — deterministic trust scoring from real evidence.

Design principles:
- The trust score is computed IN CODE from weighted signals, never by asking an LLM
  for a number. Every point added or removed is traceable to a named piece of evidence.
- Network checks degrade gracefully: a failed lookup produces "unverified", never a crash
  and never a fabricated signal.
- All I/O (DNS, HTTP, LLM) is injectable so the whole engine is testable offline.
"""

import re
import socket

FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "proton.me", "protonmail.com", "mail.com", "yandex.com",
    "zoho.com", "gmx.com", "live.com", "msn.com", "rediffmail.com",
}

RED_FLAGS = [
    (r"registration\s+fee|application\s+fee|processing\s+fee|training\s+fee",
     "asks applicants to pay a fee"),
    (r"pay\s+for\s+(your\s+)?(training|equipment|software|kit)",
     "asks applicants to pay for training or equipment"),
    (r"(whatsapp|telegram)\s*(only|\+?\d)", "contact only via messaging app"),
    (r"no\s+experience\s+(needed|required).{0,60}?\$\s?\d{3,}",
     "high pay promised for no experience"),
    (r"earn\s+up\s+to\s+\$?\d{3,}\s*(per|a|/)\s*(day|week)",
     "unrealistic earnings claim"),
    (r"(crypto(currency)?|bitcoin|usdt)\s+(payment|salary|paid)",
     "salary paid in cryptocurrency"),
    (r"send\s+(your\s+)?(bvn|ssn|bank\s+details|card\s+details|passport)",
     "requests sensitive financial/identity details upfront"),
    (r"recruitment\s+agent.{0,40}fee", "recruitment agent requesting fees"),
    (r"reshipping|package\s+forwarding|money\s+transfer\s+agent",
     "known scam job category"),
]

EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
DOMAIN_RE = re.compile(r"(?:https?://)?(?:www\.)?([\w-]+(?:\.[\w-]+)+)")


# ---------------- Signal extraction (pure, no I/O) ----------------

def extract_domain(contact: str):
    """Pull a domain out of an email address or URL. Returns lowercase domain or None."""
    if not contact:
        return None
    m = EMAIL_RE.search(contact)
    if m:
        return m.group(1).lower()
    m = DOMAIN_RE.search(contact.strip())
    if m and "." in m.group(1):
        return m.group(1).lower()
    return None


def is_free_mail(domain: str) -> bool:
    return (domain or "").lower() in FREE_MAIL_DOMAINS


def scan_red_flags(text: str) -> list:
    """Return the list of scam-pattern descriptions found in the job text."""
    found = []
    low = (text or "").lower()
    for pattern, description in RED_FLAGS:
        if re.search(pattern, low):
            found.append(description)
    return found


def name_matches_domain(company: str, domain: str) -> bool:
    """Fuzzy check: do the company name's significant tokens appear in the domain?"""
    if not company or not domain:
        return False
    stop = {"the", "and", "of", "ltd", "llc", "inc", "co", "company", "digital",
            "media", "tech", "solutions", "group", "global", "agency", "studio"}
    tokens = [t for t in re.findall(r"[a-z0-9]+", company.lower()) if t not in stop]
    host = domain.split(".")[0].replace("-", "")
    if not tokens:
        return False
    return any(t in host for t in tokens if len(t) >= 3) or \
        "".join(tokens) in host


# ---------------- Network probes (injectable, graceful) ----------------

def dns_resolves(domain: str) -> bool:
    try:
        socket.getaddrinfo(domain, None)
        return True
    except OSError:
        return False


def has_mx(domain: str):
    """True/False if determinable, None if the resolver isn't available."""
    try:
        import dns.resolver
    except ImportError:
        return None
    try:
        return len(dns.resolver.resolve(domain, "MX")) > 0
    except Exception:
        return False


def fetch_site(domain: str, timeout: int = 6):
    """Fetch the homepage. Returns (status_code, text) or (None, '') on failure."""
    import requests
    for scheme in ("https", "http"):
        try:
            r = requests.get(f"{scheme}://{domain}", timeout=timeout,
                             headers={"User-Agent": "Mozilla/5.0 (Emploi verifier)"},
                             allow_redirects=True)
            text = re.sub(r"<[^>]+>", " ", r.text or "")
            text = re.sub(r"\s+", " ", text)[:4000]
            return r.status_code, text
        except Exception:
            continue
    return None, ""


def build_site_check_prompt(company: str, role: str, site_text: str) -> str:
    return f"""You are verifying an employer. Below is text from the website of "{company}",
which is supposedly hiring for "{role or 'a role'}".

Answer with EXACTLY one word:
- CONSISTENT — the site describes a real business plausibly consistent with that company and role
- INCONSISTENT — the site is a parked page, unrelated business, placeholder, or contradicts the claim
- UNCLEAR — not enough content to judge

Site text:
{site_text[:3000]}"""


def check_site_content(model, company: str, role: str, site_text: str):
    """One narrow LLM judgment on fetched evidence. Returns 'consistent'/'inconsistent'/None."""
    if not site_text or len(site_text) < 100 or model is None:
        return None
    try:
        word = (model.generate_content(
            build_site_check_prompt(company, role, site_text)).text or "").strip().upper()
    except Exception:
        return None
    if word.startswith("CONSISTENT"):
        return "consistent"
    if word.startswith("INCONSISTENT"):
        return "inconsistent"
    return None


# ---------------- Deterministic scoring ----------------

def compute_trust(signals: dict):
    """Weighted, transparent score. Returns (score 0-100, level, evidence list)."""
    score = 50
    evidence = []

    if signals.get("no_contact"):
        evidence.append("⚪ no contact details to verify")
        score = min(score, 40)

    if signals.get("free_mail") is True:
        score -= 15
        evidence.append("🔻 contact uses a free email service (gmail/yahoo/etc.)")
    elif signals.get("free_mail") is False:
        score += 15
        evidence.append("✅ contact uses a corporate email domain")

    if signals.get("dns") is True:
        score += 10
        evidence.append("✅ company domain exists (DNS resolves)")
    elif signals.get("dns") is False:
        score -= 25
        evidence.append("🚫 company domain does not resolve")

    if signals.get("mx") is True:
        score += 5
        evidence.append("✅ domain can receive email (MX records)")
    elif signals.get("mx") is False:
        score -= 10
        evidence.append("🔻 domain has no mail records")

    if signals.get("site_up") is True:
        score += 15
        evidence.append("✅ company website is live")
    elif signals.get("site_up") is False:
        score -= 15
        evidence.append("🔻 no reachable website")

    if signals.get("name_match") is True:
        score += 10
        evidence.append("✅ company name matches its domain")
    elif signals.get("name_match") is False:
        score -= 5
        evidence.append("🔻 company name doesn't match the contact domain")

    flags = signals.get("red_flags") or []
    for f in flags[:3]:
        score -= 15
        evidence.append(f"🚫 red flag: {f}")

    if signals.get("site_content") == "consistent":
        score += 10
        evidence.append("✅ website content matches the company and role")
    elif signals.get("site_content") == "inconsistent":
        score -= 20
        evidence.append("🚫 website content does not match the claimed business")

    score = max(0, min(100, score))
    if flags:
        score = min(score, 35)

    if score >= 75:
        level = "High trust"
    elif score >= 50:
        level = "Medium trust"
    elif score >= 25:
        level = "Low trust"
    else:
        level = "Avoid"
    return score, level, evidence


def verify_employer(company: str, contact: str, job_text: str = "", role: str = "",
                    model=None, dns_fn=dns_resolves, mx_fn=has_mx,
                    fetch_fn=fetch_site, cache: dict = None) -> dict:
    """Full verification pipeline. All I/O injectable; results cacheable by domain."""
    domain = extract_domain(contact or "")
    red_flags = scan_red_flags(job_text)

    cache_key = domain or f"__none__{company}"
    if cache is not None and cache_key in cache:
        cached = dict(cache[cache_key])
        signals = dict(cached["signals"])
        signals["red_flags"] = red_flags
        score, level, evidence = compute_trust(signals)
        return {"company": company, "domain": domain, "score": score,
                "level": level, "evidence": evidence, "signals": signals}

    signals = {"red_flags": red_flags}
    if not domain:
        signals["no_contact"] = True
    else:
        free = is_free_mail(domain)
        signals["free_mail"] = free
        if not free:
            signals["dns"] = dns_fn(domain)
            if signals["dns"]:
                signals["mx"] = mx_fn(domain)
                status, site_text = fetch_fn(domain)
                signals["site_up"] = (status is not None and status < 400)
                signals["name_match"] = name_matches_domain(company, domain)
                if signals["site_up"]:
                    signals["site_content"] = check_site_content(
                        model, company, role, site_text)

    score, level, evidence = compute_trust(signals)
    result = {"company": company, "domain": domain, "score": score,
              "level": level, "evidence": evidence, "signals": signals}
    if cache is not None:
        cache[cache_key] = result
    return result
