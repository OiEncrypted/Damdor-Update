import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from bs4 import BeautifulSoup
import json
import re
import io
import os
import time
from datetime import datetime
from difflib import SequenceMatcher
import pdfplumber

from mappings import NAME_MAP, PHRASE_MAP, WORD_MAP, KNOWN_PRODUCTS, BROKEN_MARKERS

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"
HISTORY_KEEP_DAYS = 60
SIGNIFICANT_THRESHOLD_PCT = 20.0


# ==========================================
# নাম ঠিক করার লজিক
# ==========================================
def fuzzy_match(word, candidates, threshold=0.75):
    best, best_score = None, 0
    for c in candidates:
        score = SequenceMatcher(None, word, c).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best = c
    return best, best_score


def is_suspicious(name):
    if not name or len(name) < 3:
        return True
    if len(name) > 60:
        return True
    if re.search(r"\(cid:", name):
        return True
    if re.search(r"[^\u0980-\u09FFa-zA-Z0-9\s\(\)\/\-\.,%]", name):
        return True
    digit_groups = re.findall(r"\d{2,}", name)
    if len(digit_groups) >= 2:
        return True
    for marker in BROKEN_MARKERS:
        if marker in name:
            return True
    return False


def clean_name(name):
    name = name.strip()

    for phrase, correct in PHRASE_MAP.items():
        if phrase in name:
            name = name.replace(phrase, correct)

    words = name.split()
    fixed_words = []
    for w in words:
        if w in WORD_MAP:
            rep = WORD_MAP[w]
            if rep:
                fixed_words.append(rep)
        else:
            fixed_words.append(w)
    name = " ".join(fixed_words)

    name = re.sub(r"(\s+\d+\s+\d+)+.*$", "", name)
    name = re.sub(r"\d+\s+\d+\s+\d+.*$", "", name)
    name = re.sub(r"^[\d০-৯]+\s+", "", name)
    name = re.sub(r"\s+[\d০-৯]+\s*$", "", name)
    name = re.sub(r"[\_\-\.\,\/\*]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    words = name.split()
    final_words = []
    for w in words:
        if not final_words or final_words[-1] != w:
            final_words.append(w)
    name = " ".join(final_words)

    if is_suspicious(name) and len(name) > 2:
        words = name.split()
        new_words = []
        for w in words:
            if len(w) < 3:
                new_words.append(w)
                continue
            match, _ = fuzzy_match(w, KNOWN_PRODUCTS, threshold=0.75)
            new_words.append(match if match else w)
        name = " ".join(new_words)

    if len(name) < 2 or name.isdigit():
        return ""
    return name


# ==========================================
# PDF পার্সিং
# ==========================================
def fetch_with_retry(url, headers, retries=3):
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=headers, timeout=30, verify=False)
            if res.status_code == 200:
                return res
        except Exception as e:
            print(f"  ⚠️ চেষ্টা {attempt+1} ব্যর্থ: {e}")
            time.sleep(2)
    return None


def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = fetch_with_retry(PAGE_URL, headers)
    if not res:
        return []
    soup = BeautifulSoup(res.text, "html.parser")
    links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].endswith('.pdf')]
    return list(dict.fromkeys(links))[:8]


def parse_pdf(pdf_url, division_name, suspicious_list):
    headers = {"User-Agent": "Mozilla/5.0"}
    items = []
    res = fetch_with_retry(pdf_url, headers)
    if not res:
        return items

    try:
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            if len(pdf.pages) < 2:
                return items
            page = pdf.pages[1]
            words = page.extract_words()
            if not words:
                return items

            lines, current, last_top = [], [], None
            for w in sorted(words, key=lambda x: (x['top'], x['x0'])):
                if last_top is None or abs(w['top'] - last_top) < 5:
                    current.append(w)
                else:
                    if current:
                        lines.append(current)
                    current = [w]
                last_top = w['top']
            if current:
                lines.append(current)

            for line_words in lines:
                line_words = sorted(line_words, key=lambda x: x['x0'])
                line_text = " ".join(w['text'] for w in line_words)
                pm = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", line_text)
                if not pm:
                    continue
                min_p, max_p = pm.group(1), pm.group(2)
                if float(min_p) <= 0 or float(max_p) <= 0:
                    continue
                raw = line_text[:pm.start()].strip()
                cleaned = clean_name(raw)
                if not cleaned:
                    continue
                if is_suspicious(cleaned):
                    suspicious_list.append({
                        "division": division_name,
                        "raw": raw[:150],
                        "cleaned": cleaned
                    })
                items.append({
                    "division": division_name,
                    "name": cleaned,
                    "min_price": min_p,
                    "max_price": max_p
                })
    except Exception as e:
        print(f"  ❌ PDF সমস্যা ({division_name}): {e}")
    return items


# ==========================================
# ট্র্যাকিং সিস্টেম
# ==========================================
def load_previous_prices():
    if not os.path.exists("prices.json"):
        return None
    try:
        with open("prices.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ আগের prices.json পড়া যায়নি: {e}")
        return None


def get_date_from_updated_at(updated_at_str):
    try:
        dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def save_to_history(previous_data):
    """আগের prices.json-কে history/old_date.json হিসেবে সেভ করে"""
    if not previous_data:
        return
    date_str = get_date_from_updated_at(previous_data.get("updated_at", ""))
    os.makedirs("history", exist_ok=True)
    path = f"history/{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(previous_data, f, ensure_ascii=False)
    print(f"  📁 History সংরক্ষিত: {path}")

    # পুরোনো ফাইল পরিষ্কার
    files = sorted([f for f in os.listdir("history") if f.endswith(".json")])
    for old in files[:-HISTORY_KEEP_DAYS]:
        try:
            os.remove(f"history/{old}")
            print(f"  🗑️  পুরোনো history মুছে ফেলা হয়েছে: {old}")
        except Exception:
            pass


def build_tracking(current_data, previous_data):
    """আজকের ডেটাকে গতকালের সাথে তুলনা করে tracking stats বানায়"""
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    prev_date = None
    if previous_data:
        prev_date = get_date_from_updated_at(previous_data.get("updated_at", ""))

    prev_map = {}
    if previous_data:
        for item in previous_data.get("data", []):
            prev_map[(item["division"], item["name"])] = item

    curr_map = {}
    for item in current_data.get("data", []):
        curr_map[(item["division"], item["name"])] = item

    changes = []
    new_products = []
    significant = []

    for key, curr in curr_map.items():
        div, name = key
        c_min = float(curr["min_price"])
        c_max = float(curr["max_price"])

        if key in prev_map:
            prev = prev_map[key]
            p_min = float(prev["min_price"])
            p_max = float(prev["max_price"])

            avg_curr = (c_min + c_max) / 2
            avg_prev = (p_min + p_max) / 2
            change_pct = ((avg_curr - avg_prev) / avg_prev * 100) if avg_prev > 0 else 0

            if change_pct > 2:
                trend = "up"
            elif change_pct < -2:
                trend = "down"
            else:
                trend = "stable"

            change_item = {
                "division": div,
                "name": name,
                "current_min": c_min,
                "current_max": c_max,
                "previous_min": p_min,
                "previous_max": p_max,
                "change_pct": round(change_pct, 2),
                "trend": trend,
                "significant": abs(change_pct) >= SIGNIFICANT_THRESHOLD_PCT
            }
            changes.append(change_item)
            if change_item["significant"]:
                significant.append(change_item)
        else:
            new_products.append({"division": div, "name": name})
            changes.append({
                "division": div,
                "name": name,
                "current_min": c_min,
                "current_max": c_max,
                "previous_min": None,
                "previous_max": None,
                "change_pct": None,
                "trend": "new",
                "significant": False
            })

    removed = [
        {"division": k[0], "name": k[1]}
        for k in prev_map if k not in curr_map
    ]

    increased = sum(1 for c in changes if c["trend"] == "up")
    decreased = sum(1 for c in changes if c["trend"] == "down")
    stable = sum(1 for c in changes if c["trend"] == "stable")

    top_inc = sorted(
        [c for c in changes if c["trend"] == "up"],
        key=lambda x: x["change_pct"], reverse=True
    )[:5]
    top_dec = sorted(
        [c for c in changes if c["trend"] == "down"],
        key=lambda x: x["change_pct"]
    )[:5]

    return {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "current_date": today_str,
        "previous_date": prev_date,
        "summary": {
            "total_products": len(curr_map),
            "increased": increased,
            "decreased": decreased,
            "stable": stable,
            "new_products": len(new_products),
            "removed_products": len(removed),
            "significant_changes": len(significant)
        },
        "top_increases": top_inc,
        "top_decreases": top_dec,
        "significant_changes": significant,
        "new_products": new_products,
        "removed_products": removed,
        "all_changes": changes
    }


# ==========================================
# GitHub Issue তৈরি
# ==========================================
def create_issues(suspicious_items, tracking, total_products):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("⚠️ GITHUB_TOKEN বা GITHUB_REPOSITORY নেই")
        return

    base_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    today = datetime.utcnow().strftime("%Y-%m-%d")
    api = f"https://api.github.com/repos/{repo}/issues"

    # Issue 1: সন্দেহজনক নাম
    if suspicious_items:
        title = f"⚠️ {len(suspicious_items)} টি সন্দেহজনক পণ্যের নাম ({today})"
        lines = [
            f"আজকের স্ক্র্যাপে **মোট {total_products}** টি পণ্য পাওয়া গেছে।",
            f"এর মধ্যে **{len(suspicious_items)}** টি নাম সন্দেহজনক।",
            "",
            "### বিস্তারিত",
            "",
            "| বিভাগ | Raw Text | Cleaned |",
            "|-------|----------|---------|",
        ]
        for s in suspicious_items[:200]:
            raw = s['raw'].replace('|', '\\|')[:100]
            cl = s['cleaned'].replace('|', '\\|')[:80]
            lines.append(f"| {s['division']} | `{raw}` | {cl} |")
        if len(suspicious_items) > 200:
            lines.append(f"\n_... এবং আরও {len(suspicious_items) - 200} টি_")
        data = {
            "title": title,
            "body": "\n".join(lines),
            "labels": ["suspicious-names"]
        }
        try:
            r = requests.post(api, json=data, headers=base_headers, timeout=30)
            if r.status_code == 201:
                print(f"✅ Suspicious Issue: {r.json()['html_url']}")
        except Exception as e:
            print(f"❌ Suspicious issue exception: {e}")

    # Issue 2: বড় দাম পরিবর্তন
    sig = tracking.get("significant_changes", [])
    if len(sig) >= 1:
        title = f"📊 {len(sig)} টি পণ্যের দামে বড় পরিবর্তন ({today})"
        lines = [
            f"গতকালের ({tracking['previous_date']}) তুলনায় "
            f"**{len(sig)}** টি পণ্যের দাম **{SIGNIFICANT_THRESHOLD_PCT}%+** পরিবর্তিত হয়েছে।",
            "",
            "| বিভাগ | পণ্য | আগে | এখন | পরিবর্তন |",
            "|-------|------|-----|-----|----------|",
        ]
        for s in sig[:50]:
            sign = "🔺" if s["change_pct"] > 0 else "🔻"
            lines.append(
                f"| {s['division']} | {s['name']} | "
                f"{s['previous_min']}-{s['previous_max']} | "
                f"{s['current_min']}-{s['current_max']} | "
                f"{sign} {s['change_pct']:+.1f}% |"
            )
        if len(sig) > 50:
            lines.append(f"\n_... এবং আরও {len(sig) - 50} টি_")
        data = {
            "title": title,
            "body": "\n".join(lines),
            "labels": ["price-changes"]
        }
        try:
            r = requests.post(api, json=data, headers=base_headers, timeout=30)
            if r.status_code == 201:
                print(f"✅ Price Change Issue: {r.json()['html_url']}")
        except Exception as e:
            print(f"❌ Price change issue exception: {e}")


# ==========================================
# Main
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 বাজারদর স্ক্র্যাপার + ট্র্যাকিং শুরু...")
    print("=" * 60)

    # ১. আগের ডেটা লোড
    previous_data = load_previous_prices()
    if previous_data:
        print(f"📖 আগের ডেটা পাওয়া গেছে ({previous_data.get('total_items', 0)} পণ্য)")
    else:
        print("📖 আগের ডেটা নেই (প্রথম রান)")

    # ২. নতুন ডেটা স্ক্র্যাপ
    links = get_pdf_links()
    if not links:
        print("❌ কোনো PDF পাওয়া যায়নি")
        exit()

    divisions = ["ঢাকা", "চট্টগ্রাম", "খুলনা", "রাজশাহী", "বরিশাল", "রংপুর", "সিলেট", "ময়মনসিংহ"]
    all_data, suspicious = [], []

    for i, link in enumerate(links):
        div = divisions[i] if i < len(divisions) else f"বিভাগ-{i+1}"
        print(f"\n[{i+1}/8] {div}...")
        items = parse_pdf(link, div, suspicious)
        all_data.extend(items)
        print(f"  ✅ {div}: {len(items)} টি")

    # ৩. ডুপ্লিকেট বাদ
    seen, unique = set(), []
    for item in all_data:
        key = (item["division"], item["name"], item["min_price"], item["max_price"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda x: (x["division"], x["name"]))

    current_data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(unique),
        "suspicious_count": len(suspicious),
        "divisions": sorted(set(d["division"] for d in unique)),
        "data": unique
    }

    # ৪. আগের ডেটা history-তে সেভ
    save_to_history(previous_data)

    # ৫. নতুন prices.json
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(current_data, f, ensure_ascii=False, indent=2)

    # ৬. ট্র্যাকিং তৈরি
    print("\n📊 ট্র্যাকিং তৈরি হচ্ছে...")
    tracking = build_tracking(current_data, previous_data)

    with open("tracking.json", "w", encoding="utf-8") as f:
        json.dump(tracking, f, ensure_ascii=False, indent=2)

    # ৭. সারাংশ প্রিন্ট
    print("\n" + "=" * 60)
    print(f"🎉 মোট {len(unique)} টি পণ্য")
    print(f"⚠️  সন্দেহজনক: {len(suspicious)} টি")
    print("-" * 60)
    s = tracking["summary"]
    if tracking["previous_date"]:
        print(f"📅 তুলনা: {tracking['previous_date']} → {tracking['current_date']}")
        print(f"🔺 বেড়েছে  : {s['increased']} টি")
        print(f"🔻 কমেছে    : {s['decreased']} টি")
        print(f"➡️  স্থির    : {s['stable']} টি")
        print(f"🆕 নতুন      : {s['new_products']} টি")
        print(f"❌ বাদ পড়েছে: {s['removed_products']} টি")
        print(f"🚨 বড় পরিবর্তন: {s['significant_changes']} টি (>{SIGNIFICANT_THRESHOLD_PCT}%)")
    else:
        print("📅 প্রথম রান — তুলনা সম্ভব নয়")
    print("=" * 60)

    # ৮. Issues
    create_issues(suspicious, tracking, len(unique))
