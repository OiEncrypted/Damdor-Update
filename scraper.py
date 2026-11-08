
---

### ফাইল ২: `scraper.py`

```python
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
DIVISIONS = ["ঢাকা", "চট্টগ্রাম", "খুলনা", "রাজশাহী", "বরিশাল", "রংপুর", "সিলেট", "ময়মনসিংহ"]

HISTORY_KEEP_DAYS = 60
SIGNIFICANT_THRESHOLD_PCT = 20.0
MIN_ACCEPTABLE_PRODUCTS = 50
LEARNED_FILE = "learned_mappings.json"
MAX_LEARNED = 1000
FUZZY_THRESHOLD = 0.85
LEARN_THRESHOLD = 0.92

BD_TZ = timezone(timedelta(hours=6))
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
BN_RANGE = "\u0980-\u09FF"


# ==========================================
# Utility
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
# Font Mapping System
# ==========================================
def detect_pdf_font(pdf_path):
    """PDF-এ সবচেয়ে বেশি ব্যবহৃত ফন্টের নাম বের করে"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) < 2:
                return None
            page = pdf.pages[1]
            chars = page.chars
            if not chars:
                return None
            font_counts = {}
            for c in chars:
                fname = c.get("fontname", "")
                if not fname:
                    continue
                font_counts[fname] = font_counts.get(fname, 0) + 1
            if not font_counts:
                return None
            top_font = max(font_counts, key=font_counts.get)
            # pdfplumber fontname সাধারণত "/ABCDEF+NotoSansBengali" এরকম
            # prefix বাদ দিই
            clean = top_font.lstrip("/")
            if "+" in clean:
                clean = clean.split("+", 1)[1]
            return clean
    except Exception as e:
        print(f"  ⚠️ ফন্ট চেক exception: {e}")
        return None


def load_font_map(font_name):
    """ফন্টের নাম দিয়ে font_mappings/ folder থেকে mapping লোড করে"""
    if not font_name:
        return {}
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", font_name)
    path = f"font_mappings/{safe}.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except Exception as e:
        print(f"  ⚠️ font map load: {e}")
    return {}


def decode_with_font_map(text, font_map):
    """font map দিয়ে ভাঙা অক্ষর ঠিক করে"""
    if not font_map or not text:
        return text
    # দীর্ঘ key আগে চেক করার জন্য sort
    keys = sorted(font_map.keys(), key=len, reverse=True)
    result = []
    i = 0
    while i < len(text):
        matched = False
        for k in keys:
            if text[i:i+len(k)] == k:
                result.append(font_map[k])
                i += len(k)
                matched = True
                break
        if not matched:
            result.append(text[i])
            i += 1
    return "".join(result)


# ==========================================
# Learned mappings (ফন্টের পরেও যেটা বাকি থাকে)
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
        print(f"  ⚠️ learned load: {e}")
    return {}


def save_learned(m):
    if len(m) > MAX_LEARNED:
        m = dict(list(m.items())[-MAX_LEARNED:])
    atomic_write_json(LEARNED_FILE, m)


# ==========================================
# Suspicion
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
# NAME CLEANING (font map + explicit + fuzzy)
# ==========================================
def _phrase_replace(name):
    for bad, good in PHRASE_MAP.items():
        if bad and bad in name:
            name = name.replace(bad, good)
    return name


def _word_replace(name):
    for bad, good in WORD_MAP.items():
        if not bad:
            continue
        pattern = rf"(?<![{BN_RANGE}]){re.escape(bad)}(?![{BN_RANGE}])"
        name = re.sub(pattern, good, name)
    return name


def clean_name(raw, font_map, learned):
    if not raw:
        return "", 0.0

    # ধাপ ১: ফন্ট ম্যাপিং দিয়ে decode
    name = decode_with_font_map(raw.strip(), font_map)
    name = unicodedata.normalize("NFC", name)

    # ধাপ ২: NAME_MAP
    if name in NAME_MAP:
        return NAME_MAP[name], 1.0
    for k, v in NAME_MAP.items():
        if name.startswith(k):
            return v, 1.0

    # ধাপ ৩: PHRASE_MAP
    name = _phrase_replace(name)

    # ধাপ ৪: learned
    if name in learned:
        return learned[name], 1.0

    # ধাপ ৫: WORD_MAP
    name = _word_replace(name)

    # ধাপ ৬: পরিষ্কার
    name = re.sub(r"\(cid:\d+\)", "", name)
    name = re.sub(r"cid:\d+", "", name)
    name = re.sub(r"(\s*[\d.]+){2,}\s*$", "", name)
    name = re.sub(r"^[\d০-৯]+\s+", "", name)
    name = re.sub(r"[\_\-\.\,\/\*]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    parts = name.split()
    dedup = []
    for w in parts:
        if not dedup or dedup[-1] != w:
            dedup.append(w)
    name = " ".join(dedup)

    # ধাপ ৭: fuzzy
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


def parse_bengali_date(s):
    s = s.translate(BN_DIGITS).strip()
    try:
        return datetime.strptime(s, "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def get_dates_and_pdfs(errors):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = fetch_with_retry(PAGE_URL, headers)
        if not r:
            errors.append("মূল পেজ ফেচ ফেইল")
            return {}
        soup = BeautifulSoup(r.text, "html.parser")

        date_map = {}
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) != 9:
                    continue
                date = parse_bengali_date(cells[0].get_text(strip=True))
                if not date:
                    continue
                div_pdfs = {}
                for i, div in enumerate(DIVISIONS):
                    a = cells[i + 1].find("a", href=True)
                    if a and a["href"].endswith(".pdf"):
                        div_pdfs[div] = a["href"]
                if div_pdfs:
                    date_map[date] = div_pdfs

        if not date_map:
            errors.append("টেবিলে কোনো তারিখ/PDF পাওয়া যায়নি")
        return date_map
    except Exception as e:
        errors.append(f"পেজ parse exception: {e}")
        return {}


def parse_pdf(pdf_url, division, font_map, suspicious, learned, to_learn, errors):
    headers = {"User-Agent": "Mozilla/5.0"}
    items = []

    r = fetch_with_retry(pdf_url, headers)
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
                cleaned, fscore = clean_name(raw, font_map, learned)
                if not cleaned:
                    continue

                if is_suspicious(cleaned):
                    suspicious.append({
                        "division": division,
                        "raw": raw[:150],
                        "cleaned": cleaned
                    })

                # auto-learn: high confidence + known product
                if (cleaned in KNOWN_PRODUCTS
                        and fscore >= LEARN_THRESHOLD
                        and raw != cleaned
                        and raw not in to_learn):
                    to_learn[raw] = cleaned

                items.append({
                    "division": division,
                    "name": cleaned,
                    "min_price": f"{mn:.2f}",
                    "max_price": f"{mx:.2f}",
                })
    except Exception as e:
        errors.append(f"{division}: parse exception — {e}")
    return items


# ==========================================
# Dedup + History + Tracking
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


def load_previous():
    if not os.path.exists("prices.json"):
        return None
    try:
        with open("prices.json", "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict) and "data" in d:
                return d
    except Exception as e:
        print(f"  ⚠️ prices load: {e}")
    return None


def save_history(prev):
    if not prev:
        return
    d = prev.get("data_date", "unknown")
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
    cdate = curr["data_date"]
    pdate = prev.get("data_date") if prev else None
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
        "current_date": cdate,
        "previous_date": pdate,
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
            print(f"  ✅ Issue: {r.json()['html_url']}")
        else:
            print(f"  ❌ Issue {r.status_code}")
    except Exception as e:
        print(f"  ❌ Issue exception: {e}")


def create_issues(suspicious, tracking, total, errors, font_info):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    today = bd_date_str()

    # Issue 1: Suspicious names
    if suspicious:
        title = f"🔍 [Names] {len(suspicious)} সন্দেহজনক নাম — {today}"
        lines = [
            f"মোট **{total}** পণ্যের মধ্যে **{len(suspicious)}** সন্দেহজনক।",
            "",
            f"**ফন্ট:** `{font_info or 'unknown'}`",
            "",
            "**কী করতে হবে (প্রথমে font mapping, তারপর word map):**",
            "",
            "| বিভাগ | Raw Text | Cleaned |",
            "|-------|----------|---------|",
        ]
        for s in suspicious[:150]:
            raw = s["raw"].replace("|", "\\|")[:100]
            cl = s["cleaned"].replace("|", "\\|")[:80]
            lines.append(f"| {s['division']} | `{raw}` | {cl} |")
        if len(suspicious) > 150:
            lines.append(f"\n_...আরও {len(suspicious) - 150} টি_")
        post_issue(repo, token, title, "\n".join(lines), ["suspicious-names"])

    # Issue 2: Price changes
    sig = tracking.get("significant_changes", [])
    if sig:
        prev_date = tracking.get("previous_date") or "শুরু"
        curr_date = tracking.get("current_date") or today
        title = f"📈 [Prices] {len(sig)} পণ্যের দামে বড় পরিবর্তন — {today}"
        lines = [
            f"**{prev_date}** → **{curr_date}**",
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
        post_issue(repo, token, title, "\n".join(lines), ["price-changes"])

    # Issue 3: Errors
    if errors:
        title = f"🚨 [Error] স্ক্র্যাপিং — {today}"
        body = "\n".join([f"- {e}" for e in errors[:30]])
        post_issue(repo, token, title, body, ["scraper-error"])


# ==========================================
# Main
# ==========================================
def main():
    print("=" * 60)
    print("🚀 বাজারদর স্ক্র্যাপার v6 (Font-Aware)")
    print("=" * 60)

    errors, suspicious, to_learn = [], [], {}
    learned = load_learned()
    if learned:
        print(f"📚 Learned: {len(learned)}")

    date_map = get_dates_and_pdfs(errors)
    if not date_map:
        create_issues(suspicious, {"significant_changes": []}, 0, errors, None)
        raise SystemExit("❌ কোনো ডেটা পাওয়া যায়নি")

    print(f"📅 পেজে তারিখ: {sorted(date_map.keys(), reverse=True)[:5]}")
    newest_date = max(date_map.keys())
    division_pdfs = date_map[newest_date]
    print(f"🎯 Target: {newest_date} ({len(division_pdfs)} division)")

    prev = load_previous()
    prev_date = prev.get("data_date") if prev else None
    print(f"📖 Previous: {prev_date or 'নেই'}")

    if prev_date and newest_date <= prev_date:
        print(f"\n⏭️ নতুন ডেটা নেই। {newest_date} <= {prev_date}")
        if errors:
            create_issues(suspicious, {"significant_changes": []}, prev.get("total_items", 0), errors, None)
        return

    # ফন্ট ডিটেক্ট (প্রথম PDF থেকে)
    print("\n🔤 ফন্ট চেক করা হচ্ছে...")
    first_url = list(division_pdfs.values())[0]
    font_map = {}
    font_name = None
    try:
        r = fetch_with_retry(first_url, {"User-Agent": "Mozilla/5.0"})
        if r:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = tmp.name
            font_name = detect_pdf_font(tmp_path)
            os.remove(tmp_path)
            print(f"  ফন্ট: {font_name}")

            if font_name:
                font_map = load_font_map(font_name)
                if font_map:
                    print(f"  ✅ Font map: {len(font_map)} এন্ট্রি")
                else:
                    print(f"  ⚠️ font_mappings/{font_name}.json নেই")
                    errors.append(f"font_mappings/{font_name}.json তৈরি করা দরকার")
    except Exception as e:
        print(f"  ⚠️ ফন্ট চেক exception: {e}")

    # পার্স
    all_items = []
    for div, url in division_pdfs.items():
        print(f"\n[{div}]...")
        its = parse_pdf(url, div, font_map, suspicious, learned, to_learn, errors)
        all_items.extend(its)
        print(f"  ✅ {len(its)}")

    unique = dedup(all_items)
    print(f"\n📦 Dedup: {len(unique)}")

    if len(unique) < MIN_ACCEPTABLE_PRODUCTS:
        errors.append(f"পণ্য কমে গেছে: {len(unique)} < {MIN_ACCEPTABLE_PRODUCTS}")
        print("🚨 Validation fail")
        create_issues(suspicious, {"significant_changes": []}, prev.get("total_items", 0) if prev else 0, errors, font_name)
        return

    if to_learn:
        save_learned({**learned, **to_learn})
        print(f"📚 {len(to_learn)} নতুন learned")

    save_history(prev)

    current = {
        "updated_at": utc_iso(),
        "data_date": newest_date,
        "total_items": len(unique),
        "suspicious_count": len(suspicious),
        "font": font_name,
        "divisions": sorted(set(x["division"] for x in unique)),
        "data": unique,
    }
    atomic_write_json("prices.json", current)

    tracking = build_tracking(current, prev)
    atomic_write_json("tracking.json", tracking)

    print("\n" + "=" * 60)
    s = tracking["summary"]
    print(f"🎉 পণ্য: {len(unique)} | সন্দেহ: {len(suspicious)}")
    if prev_date:
        print(f"📅 {prev_date} → {newest_date}")
        print(f"🔺{s['increased']}  🔻{s['decreased']}  ➡️{s['stable']}  🆕{s['new_products']}  🚨{s['significant_changes']}")
    if errors:
        print(f"⚠️ {len(errors)} error")
    print("=" * 60)

    create_issues(suspicious, tracking, len(unique), errors, font_name)


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
