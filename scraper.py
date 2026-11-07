import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from bs4 import BeautifulSoup
import json
import re
import io
import os
import time
import tempfile
import traceback
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import pdfplumber

from mappings import NAME_MAP, PHRASE_MAP, WORD_MAP, KNOWN_PRODUCTS, BROKEN_MARKERS

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"
HISTORY_KEEP_DAYS = 60
SIGNIFICANT_THRESHOLD_PCT = 20.0
MIN_ACCEPTABLE_PRODUCTS = 50
LEARNED_FILE = "learned_mappings.json"
MAX_LEARNED = 1000
FUZZY_THRESHOLD = 0.85
LEARN_THRESHOLD = 0.92
BD_TZ = timezone(timedelta(hours=6))
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
# বাংলা বর্ণের range — word boundary নির্ধারণে ব্যবহার
BN_RANGE = "\u0980-\u09FF"


# ==========================================
# Utilities
# ==========================================
def bd_now():
    return datetime.now(BD_TZ)


def bd_date_str():
    return bd_now().strftime("%Y-%m-%d")


def utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_json(path, data):
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def safe_float(s):
    try:
        return float(s.translate(BN_DIGITS).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def fuzzy_match(word, candidates):
    if not word or len(word) < 3:
        return None, 0.0
    best, best_score = None, 0.0
    for c in sorted(candidates):
        score = SequenceMatcher(None, word, c).ratio()
        if score > best_score + 0.001 or (abs(score - best_score) < 0.001 and best and c < best):
            best_score, best = score, c
    return (best, best_score) if best_score >= FUZZY_THRESHOLD else (None, best_score)


# ==========================================
# Learned Mappings
# ==========================================
def load_learned():
    if not os.path.exists(LEARNED_FILE):
        return {}
    try:
        with open(LEARNED_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)}
    except Exception as e:
        print(f"⚠️ learned load: {e}")
    return {}


def save_learned(m):
    if len(m) > MAX_LEARNED:
        m = dict(list(m.items())[-MAX_LEARNED:])
    atomic_write_json(LEARNED_FILE, m)


def should_learn(raw, cleaned, fscore):
    if not raw or not cleaned or raw == cleaned:
        return False
    if fscore < LEARN_THRESHOLD:
        return False
    if cleaned not in KNOWN_PRODUCTS:
        return False
    return True


# ==========================================
# Suspicion check
# ==========================================
def is_suspicious(name):
    if not name or len(name) < 3:
        return True
    if len(name) > 60:
        return True
    if re.search(r"\(cid:\d+\)", name):
        return True
    if re.search(r"[^\u0980-\u09FFa-zA-Z0-9\s\(\)\/\-\.,%]", name):
        return True
    if len(re.findall(r"\d{2,}", name)) >= 2:
        return True
    for m in BROKEN_MARKERS:
        if m in name:
            return True
    return False


# ==========================================
# NAME CLEANING (with word boundaries)
# ==========================================
def _phrase_replace(name):
    """Phrase map — পুরো স্ট্রিং substring replace"""
    for bad, good in PHRASE_MAP.items():
        if bad and bad in name:
            name = name.replace(bad, good)
    return name


def _word_replace(name):
    """
    Word map — Bengali character boundary respected।
    অর্থাৎ punctuation/symbol থাকলেও word match হবে,
    কিন্তু অন্য Bengali word-এর ভেতরে match হবে না।
    """
    for bad, good in WORD_MAP.items():
        if not bad:
            continue
        pattern = rf"(?<![{BN_RANGE}]){re.escape(bad)}(?![{BN_RANGE}])"
        name = re.sub(pattern, good, name)
    return name


def clean_name(raw, learned):
    if not raw:
        return "", 0.0

    name = unicodedata.normalize("NFC", raw.strip())

    # 1. NAME_MAP (exact / startsWith)
    if name in NAME_MAP:
        return NAME_MAP[name], 1.0
    for k, v in NAME_MAP.items():
        if name.startswith(k):
            return v, 1.0

    # 2. Phrase map
    name = _phrase_replace(name)

    # 3. Learned (highest priority after explicit)
    if name in learned:
        return learned[name], 1.0

    # 4. Word map (with boundary)
    name = _word_replace(name)

    # 5. Cleanup — cid, numbers, symbols
    name = re.sub(r"\(cid:\d+\)", "", name)
    name = re.sub(r"(\s*[\d.]+){2,}\s*$", "", name)          # trailing number groups
    name = re.sub(r"^[\d০-৯]+\s+", "", name)                 # leading number
    name = re.sub(r"[\_\-\.\,\/\*]+", " ", name)             # symbols
    name = re.sub(r"\s+", " ", name).strip()

    # dedupe consecutive words
    parts = name.split()
    dedup = []
    for w in parts:
        if not dedup or dedup[-1] != w:
            dedup.append(w)
    name = " ".join(dedup)

    # 6. Fuzzy match (last resort)
    fscore = 0.0
    if is_suspicious(name) and len(name) > 2:
        out = []
        for w in name.split():
            if len(w) < 3:
                out.append(w)
                continue
            match, score = fuzzy_match(w, KNOWN_PRODUCTS)
            if match:
                out.append(match)
                fscore = max(fscore, score)
            else:
                out.append(w)
        name = " ".join(out)

    if len(name) < 2 or name.isdigit():
        return "", 0.0

    return name, fscore


# ==========================================
# Fetch + Parse
# ==========================================
def fetch_with_retry(url, headers, retries=3, backoff=2):
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=30, verify=False)
            if r.status_code == 200:
                return r
            print(f"  ⚠️ HTTP {r.status_code}")
        except Exception as e:
            print(f"  ⚠️ retry {i+1}: {type(e).__name__}")
        time.sleep(backoff ** i)
    return None


def get_pdf_links(errors):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = fetch_with_retry(PAGE_URL, headers)
        if not r:
            errors.append("মূল পেজ ফেইল")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = [a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf")]
        unique = list(dict.fromkeys(links))[:8]
        if len(unique) < 8:
            errors.append(f"শুধু {len(unique)}টি PDF লিংক (৮ প্রত্যাশিত)")
        return unique
    except Exception as e:
        errors.append(f"লিংক exception: {e}")
        return []


def parse_pdf(url, division, suspicious, learned, to_learn, errors):
    headers = {"User-Agent": "Mozilla/5.0"}
    items = []
    r = fetch_with_retry(url, headers)
    if not r:
        errors.append(f"{division}: ডাউনলোড ফেইল")
        return items

    try:
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            if len(pdf.pages) < 2:
                errors.append(f"{division}: ২ পেজ নেই")
                return items
            page = pdf.pages[1]
            words = page.extract_words()
            if not words:
                errors.append(f"{division}: টেক্সট নেই")
                return items

            lines, cur, last = [], [], None
            for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
                if last is None or abs(w["top"] - last) < 5:
                    cur.append(w)
                else:
                    if cur:
                        lines.append(cur)
                    cur = [w]
                last = w["top"]
            if cur:
                lines.append(cur)

            for lw in lines:
                lw = sorted(lw, key=lambda x: x["x0"])
                text = " ".join(w["text"] for w in lw)
                pm = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", text)
                if not pm:
                    continue
                mn, mx = safe_float(pm.group(1)), safe_float(pm.group(2))
                if not mn or not mx or mn <= 0 or mx <= 0 or mn > mx:
                    continue
                raw = text[:pm.start()].strip()
                cleaned, fscore = clean_name(raw, learned)
                if not cleaned:
                    continue

                if is_suspicious(cleaned):
                    suspicious.append({"division": division, "raw": raw[:150], "cleaned": cleaned})

                if should_learn(raw, cleaned, fscore):
                    to_learn[raw] = cleaned

                items.append({
                    "division": division,
                    "name": cleaned,
                    "min_price": f"{mn:.2f}",
                    "max_price": f"{mx:.2f}",
                })
    except Exception as e:
        errors.append(f"{division}: পার্স exception — {e}")
    return items


# ==========================================
# Deterministic dedup
# ==========================================
def dedup(items):
    groups = defaultdict(list)
    for it in items:
        groups[(it["division"], it["name"])].append(it)
    out = []
    for (div, name), g in groups.items():
        mins = [float(x["min_price"]) for x in g]
        maxs = [float(x["max_price"]) for x in g]
        out.append({
            "division": div, "name": name,
            "min_price": f"{min(mins):.2f}",
            "max_price": f"{max(maxs):.2f}",
        })
    return sorted(out, key=lambda x: (x["division"], x["name"]))


# ==========================================
# History + Tracking
# ==========================================
def load_previous():
    if not os.path.exists("prices.json"):
        return None
    try:
        with open("prices.json", "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict) and "data" in d:
                return d
    except Exception as e:
        print(f"⚠️ prices load: {e}")
    return None


def date_of(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


def save_history(prev):
    if not prev:
        return
    d = date_of(prev.get("updated_at", ""))
    if d == "unknown":
        return
    os.makedirs("history", exist_ok=True)
    path = f"history/{d}.json"
    if not os.path.exists(path):
        atomic_write_json(path, prev)
    files = sorted(f for f in os.listdir("history") if f.endswith(".json"))
    for old in files[:-HISTORY_KEEP_DAYS]:
        try:
            os.remove(f"history/{old}")
        except Exception:
            pass


def build_tracking(curr, prev):
    cdate = date_of(curr["updated_at"])
    pdate = date_of(prev["updated_at"]) if prev else None

    prev_map = {(x["division"], x["name"]): x for x in prev.get("data", [])} if prev else {}
    curr_map = {(x["division"], x["name"]): x for x in curr["data"]}

    changes, new_items, sig = [], [], []
    for key, c in curr_map.items():
        div, name = key
        c_min, c_max = float(c["min_price"]), float(c["max_price"])
        c_avg = (c_min + c_max) / 2

        if key in prev_map:
            p = prev_map[key]
            p_min, p_max = float(p["min_price"]), float(p["max_price"])
            p_avg = (p_min + p_max) / 2
            pct = ((c_avg - p_avg) / p_avg * 100) if p_avg > 0 else 0.0
            trend = "up" if pct > 2 else "down" if pct < -2 else "stable"
            entry = {
                "division": div, "name": name,
                "current_min": c_min, "current_max": c_max,
                "previous_min": p_min, "previous_max": p_max,
                "change_pct": round(pct, 2), "trend": trend,
                "significant": abs(pct) >= SIGNIFICANT_THRESHOLD_PCT,
            }
            changes.append(entry)
            if entry["significant"]:
                sig.append(entry)
        else:
            new_items.append({"division": div, "name": name})
            changes.append({
                "division": div, "name": name,
                "current_min": c_min, "current_max": c_max,
                "previous_min": None, "previous_max": None,
                "change_pct": None, "trend": "new", "significant": False,
            })

    removed = [{"division": k[0], "name": k[1]} for k in prev_map if k not in curr_map]

    ups = sorted([c for c in changes if c["trend"] == "up"], key=lambda x: -x["change_pct"])[:5]
    downs = sorted([c for c in changes if c["trend"] == "down"], key=lambda x: x["change_pct"])[:5]

    return {
        "updated_at": utc_iso(),
        "current_date": cdate, "previous_date": pdate,
        "same_day_rerun": cdate == pdate,
        "summary": {
            "total_products": len(curr_map),
            "increased": sum(1 for c in changes if c["trend"] == "up"),
            "decreased": sum(1 for c in changes if c["trend"] == "down"),
            "stable": sum(1 for c in changes if c["trend"] == "stable"),
            "new_products": len(new_items),
            "removed_products": len(removed),
            "significant_changes": len(sig),
        },
        "top_increases": ups, "top_decreases": downs,
        "significant_changes": sig, "new_products": new_items,
        "removed_products": removed, "all_changes": changes,
    }


# ==========================================
# GitHub Issues
# ==========================================
def post_issue(repo, token, title, body, labels):
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.post(url, json={"title": title, "body": body, "labels": labels}, headers=headers, timeout=30)
        if r.status_code == 201:
            print(f"  ✅ {r.json()['html_url']}")
        else:
            print(f"  ❌ Issue {r.status_code}")
    except Exception as e:
        print(f"  ❌ Issue exception: {e}")


def create_issues(suspicious, tracking, total, errors):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    today = bd_date_str()

    if suspicious:
        title = f"🔍 [Names] {len(suspicious)} টি সন্দেহজনক পণ্যের নাম — {today}"
        lines = [
            f"মোট **{total}** টি পণ্যের মধ্যে **{len(suspicious)}** টির নাম সন্দেহজনক।",
            "",
            "**কী করতে হবে:** `mappings.py`-এ `WORD_MAP` / `PHRASE_MAP`-এ যোগ করো।",
            "",
            "| বিভাগ | Raw Text | Cleaned |",
            "|-------|----------|---------|",
        ]
        for s in suspicious[:150]:
            raw = s["raw"].replace("|", "\\|")[:100]
            cl = s["cleaned"].replace("|", "\\|")[:80]
            lines.append(f"| {s['division']} | `{raw}` | {cl} |")
        if len(suspicious) > 150:
            lines.append(f"\n_...এবং আরও {len(suspicious) - 150} টি_")
        post_issue(repo, token, title, "\n".join(lines), ["suspicious-names"])

    sig = tracking.get("significant_changes", [])
    if sig and not tracking.get("same_day_rerun"):
        title = f"📈 [Prices] {len(sig)} টি পণ্যের দামে বড় পরিবর্তন — {today}"
        lines = [
            f"**{tracking['previous_date']}** → **{tracking['current_date']}**",
            f"{SIGNIFICANT_THRESHOLD_PCT}%+ পরিবর্তন:",
            "",
            "| বিভাগ | পণ্য | আগে | এখন | পরিবর্তন |",
            "|-------|------|-----|-----|----------|",
        ]
        for s in sig[:50]:
            arrow = "🔺" if s["change_pct"] > 0 else "🔻"
            lines.append(
                f"| {s['division']} | {s['name']} | "
                f"{s['previous_min']:.0f}-{s['previous_max']:.0f} | "
                f"{s['current_min']:.0f}-{s['current_max']:.0f} | "
                f"{arrow} {s['change_pct']:+.1f}% |"
            )
        if len(sig) > 50:
            lines.append(f"\n_...এবং আরও {len(sig) - 50} টি_")
        post_issue(repo, token, title, "\n".join(lines), ["price-changes"])

    if errors:
        title = f"🚨 [Error] স্ক্র্যাপিংয়ে সমস্যা — {today}"
        body = "\n".join([f"- {e}" for e in errors[:30]])
        post_issue(repo, token, title, body, ["scraper-error"])


# ==========================================
# Main
# ==========================================
def main():
    print("=" * 60)
    print("🚀 বাজারদর স্ক্র্যাপার v4")
    print("=" * 60)

    errors, suspicious, to_learn = [], [], {}
    learned = load_learned()
    if learned:
        print(f"📚 Learned: {len(learned)}")

    prev = load_previous()
    print(f"📖 পূর্ববর্তী: {prev['total_items'] if prev else 'নেই'}")

    links = get_pdf_links(errors)
    if not links:
        create_issues(suspicious, {"significant_changes": [], "previous_date": None, "current_date": None}, 0, errors)
        raise SystemExit("❌ PDF পাওয়া যায়নি")

    divisions = ["ঢাকা", "চট্টগ্রাম", "খুলনা", "রাজশাহী", "বরিশাল", "রংপুর", "সিলেট", "ময়মনসিংহ"]
    all_items = []

    for i, link in enumerate(links):
        div = divisions[i] if i < len(divisions) else f"বিভাগ-{i+1}"
        print(f"\n[{i+1}/{len(links)}] {div}...")
        its = parse_pdf(link, div, suspicious, learned, to_learn, errors)
        all_items.extend(its)
        print(f"  ✅ {len(its)}")

    unique = dedup(all_items)
    print(f"\n📦 Dedup পরে: {len(unique)}")

    if len(unique) < MIN_ACCEPTABLE_PRODUCTS:
        errors.append(f"পণ্য কমে গেছে: {len(unique)} < {MIN_ACCEPTABLE_PRODUCTS}")
        print("🚨 Validation fail — পুরোনো prices.json রাখা হচ্ছে")

    if to_learn:
        save_learned({**learned, **to_learn})
        print(f"📚 {len(to_learn)} নতুন learned")

    current = {
        "updated_at": utc_iso(),
        "total_items": len(unique),
        "suspicious_count": len(suspicious),
        "divisions": sorted(set(x["division"] for x in unique)),
        "data": unique,
    }

    save_history(prev)
    atomic_write_json("prices.json", current)
    tracking = build_tracking(current, prev)
    atomic_write_json("tracking.json", tracking)

    print("\n" + "=" * 60)
    s = tracking["summary"]
    print(f"🎉 পণ্য: {len(unique)} | সন্দেহ: {len(suspicious)}")
    if tracking["previous_date"]:
        print(f"📅 {tracking['previous_date']} → {tracking['current_date']}" + (" (same-day)" if tracking["same_day_rerun"] else ""))
        print(f"🔺{s['increased']}  🔻{s['decreased']}  ➡️{s['stable']}  🆕{s['new_products']}  🚨{s['significant_changes']}")
    if errors:
        print(f"⚠️ {len(errors)} error")
    print("=" * 60)

    create_issues(suspicious, tracking, len(unique), errors)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        print(err)
        t = os.environ.get("GITHUB_TOKEN")
        r = os.environ.get("GITHUB_REPOSITORY")
        if t and r:
            post_issue(r, t, f"🚨 [Fatal] {bd_date_str()}", f"```\n{err[-3000:]}\n```", ["scraper-error", "fatal"])
        raise
