"""Offline checks for the static landing site (landing/).

Audits every link in the landing pages: in-page anchors resolve to real ids,
local file links exist, app links point at the product, no stale waitlist
copy, social handles are @emploihq, and legal pages link back correctly.
No network, no dependencies beyond the stdlib.
"""
import os
import re
import sys

FAILURES = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"{status} - {label}")
    if not cond:
        FAILURES.append(label)


LANDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing")
PAGES = ["index.html", "privacy.html", "terms.html"]

html = {}
for page in PAGES:
    path = os.path.join(LANDING, page)
    check(f"{page} exists", os.path.exists(path))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            html[page] = f.read()

HREF_RE = re.compile(r'href=["\']([^"\']+)["\']')
ID_RE = re.compile(r'id=["\']([^"\']+)["\']')

for page, src in html.items():
    hrefs = HREF_RE.findall(src)
    ids = set(ID_RE.findall(src))
    check(f"{page}: has links", len(hrefs) > 0)
    for href in hrefs:
        if href.startswith("#"):
            frag = href[1:]
            check(f"{page}: anchor '{href}' resolves",
                  frag == "" or frag in ids)
        elif href.startswith(("http://", "https://", "mailto:", "data:")):
            pass  # external / mail / inline — validated separately below
        else:
            target = href.split("#")[0]
            check(f"{page}: local link '{href}' exists",
                  os.path.exists(os.path.join(LANDING, target)))

index = html.get("index.html", "")

# --- app links: every CTA goes to the product, none to a waitlist ---
applinks = re.findall(r'class="[^"]*applink[^"]*"[^>]*href="([^"]+)"', index) \
         + re.findall(r'href="([^"]+)"[^>]*class="[^"]*applink[^"]*"', index)
check("index: has app links (CTAs into the product)", len(applinks) >= 4)
check("index: all app links point at https://app.emploihq.com",
      all(u == "https://app.emploihq.com" for u in applinks))
check("index: no waitlist copy remains", "waitlist" not in index.lower())
check("index: canonical points to the production landing domain",
      'rel="canonical" href="https://emploihq.com/"' in index)
check("index: pricing includes every live billing tier",
      all(label in index for label in ["₦0", "₦3,500", "₦7,500"]))
check("index: mockup uses the honest company-checked label",
      "company checked" in index and ">✓ verified<" not in index)
check("index: JS rewrites app links to localhost:3000 (Next.js dashboard) for local dev",
      "localhost:3000" in index and "applink" in index)

# --- mobile navigation ---
check("index: hamburger menu button present", 'id="menuBtn"' in index)
mm = re.search(r'id="mobileMenu".*?</nav>', index, re.S)
check("index: mobile menu present", mm is not None)
if mm:
    for frag in ["#how", "#why", "#trust", "#pricing", "app.emploihq.com"]:
        check(f"index: mobile menu links to {frag}", frag in mm.group(0))

# --- social handles: @emploihq everywhere ---
for net, pat in [("X", r"x\.com/emploihq"),
                 ("Instagram", r"instagram\.com/emploihq"),
                 ("TikTok", r"tiktok\.com/@emploihq"),
                 ("GitHub", r"github\.com/emploihq")]:
    check(f"index: {net} link uses @emploihq", re.search(pat, index) is not None)

# --- contact emails on the final domain ---
check("index: contact email hello@emploihq.com present", "mailto:hello@emploihq.com" in index)
check("index: support email support@emploihq.com present", "mailto:support@emploihq.com" in index)
check("index: no stale ../docs links", "../docs" not in index)

# --- legal pages ---
for page, other in [("privacy.html", "terms.html"), ("terms.html", "privacy.html")]:
    src = html.get(page, "")
    check(f"{page}: links back to index.html", 'href="index.html"' in src)
    check(f"{page}: cross-links to {other}", f'href="{other}"' in src)
    check(f"{page}: no draft-for-legal-review notice remains", "draft" not in src.lower())
    check(f"{page}: contact is hello@emploihq.com", "mailto:hello@emploihq.com" in src)
    check(f"{page}: has a production canonical", 'rel="canonical" href="https://emploihq.com/' in src)
check("terms.html keeps the never-pay-a-fee warning",
      "never pay a fee" in html.get("terms.html", "").lower())

# --- company identity (compliance) on every page ---
for page, src in html.items():
    check(f"{page}: names Crost Limited", "Crost Limited" in src)
    check(f"{page}: shows RC 9526947", "RC 9526947" in src)
check("index: copyright is Crost Limited", "© 2026 Crost Limited" in index)

# --- domain: emploihq.com everywhere, no stale emploi.ng ---
for page, src in html.items():
    check(f"{page}: no stale emploi.ng reference", "emploi.ng" not in src)

# --- positioning: Africa-first, global — not remote-only ---
check("index: Africa-first global positioning copy present",
      "Starting in Africa, built for the world" in index)
check("index: no remote-only positioning", "remote job seekers" not in index)

# --- product guardrails in marketing copy ---
check("index: footer keeps the honest verification disclaimer",
      "not a guarantee" in index)
check("index: trust demo keeps the never-pay warning",
      "never pay a fee" in index.lower())

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S)")
    sys.exit(1)
print("ALL TESTS PASSED ✅")
