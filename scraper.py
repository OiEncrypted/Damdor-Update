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

# ম্যাপিং ফাইল থেকে সব ডেটা ইমপোর্ট
from mappings import NAME_MAP, PHRASE_MAP, WORD_MAP, KNOWN_PRODUCTS, BROKEN_MARKERS

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"


def fuzzy_match(word, candidates, threshold=0.75):
    """কাছাকাছি নাম থাকলে সেটা ফেরত দেয়"""
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


def clean_name(name):
    """তিন স্তরে নাম ঠিক করে"""
    name = name.strip()

    # Level 1: ফ্রেজ-লেভেল
    for phrase, correct in PHRASE_MAP.items():
        if phrase in name:
            name = name.replace(phrase, correct)

    # Level 2: ওয়ার্ড-লেভেল
    words = name.split()
    fixed_words = []
    for w in words:
        if w in WORD_MAP:
            replacement = WORD_MAP[w]
            if replacement:
                fixed_words.append(replacement)
        else:
            fixed_words.append(w)
    name = " ".join(fixed_words)

    # সংখ্যা/চিহ্ন পরিষ্কার
    name = re.sub(r"(\s+\d+\s+\d+)+.*$", "", name)
    name = re.sub(r"\d+\s+\d+\s+\d+.*$", "", name)
    name = re.sub(r"^[\d০-৯]+\s+", "", name)
    name = re.sub(r"\s+[\d০-৯]+\s*$", "", name)
    name = re.sub(r"[\_\-\.\,\/\*]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    # ডুপ্লিকেট শব্দ বাদ
    words = name.split()
    final_words = []
    for w in words:
        if not final_words or final_words[-1] != w:
            final_words.append(w)
    name = " ".join(final_words)

    # Level 3: ফাজি ম্যাচিং
    if is_suspicious(name) and len(name) > 2:
        words = name.split()
        new_words = []
        for w in words:
            if len(w) < 3:
                new_words.append(w)
                continue
            match, score = fuzzy_match(w, KNOWN_PRODUCTS, threshold=0.75)
            new_words.append(match if match else w)
        name = " ".join(new_words)

    if len(name) < 2 or name.isdigit():
        return ""

    return name


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

                price_match = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", line_text)
                if not price_match:
                    continue

                min_p, max_p = price_match.group(1), price_match.group(2)
                if float(min_p) <= 0 or float(max_p) <= 0:
                    continue

                raw_name = line_text[:price_match.start()].strip()
                cleaned = clean_name(raw_name)

                if not cleaned:
                    continue

                if is_suspicious(cleaned):
                    suspicious_list.append({
                        "division": division_name,
                        "raw": raw_name[:150],
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


def create_github_issue(suspicious_items, total_count):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not token or not repo:
        print("⚠️ GITHUB_TOKEN বা GITHUB_REPOSITORY নেই")
        return
    if not suspicious_items:
        print("✅ সন্দেহজনক নাম নেই — ইস্যু তৈরি হচ্ছে না")
        return

    today = datetime.utcnow().strftime("%Y-%m-%d")
    title = f"⚠️ {len(suspicious_items)} টি সন্দেহজনক পণ্যের নাম ({today})"

    body_lines = [
        f"আজকের স্ক্র্যাপে **মোট {total_count}** টি পণ্য পাওয়া গেছে।",
        f"এর মধ্যে **{len(suspicious_items)}** টি নাম সন্দেহজনক।",
        "",
        "### বিস্তারিত",
        "",
        "| বিভাগ | Raw Text | Cleaned |",
        "|-------|----------|---------|",
    ]
    for s in suspicious_items[:200]:
        raw = s['raw'].replace('|', '\\|')[:100]
        cleaned = s['cleaned'].replace('|', '\\|')[:80]
        body_lines.append(f"| {s['division']} | `{raw}` | {cleaned} |")

    if len(suspicious_items) > 200:
        body_lines.append(f"\n_... এবং আরও {len(suspicious_items) - 200} টি_")

    body = "\n".join(body_lines)
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {"title": title, "body": body, "labels": ["suspicious-names"]}

    try:
        res = requests.post(url, json=data, headers=headers, timeout=30)
        if res.status_code == 201:
            print(f"✅ Issue: {res.json()['html_url']}")
    except Exception as e:
        print(f"❌ Issue exception: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 বাজারদর স্ক্র্যাপার শুরু...")
    print("=" * 60)

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

    seen, unique = set(), []
    for item in all_data:
        key = (item["division"], item["name"], item["min_price"], item["max_price"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique.sort(key=lambda x: (x["division"], x["name"]))

    final = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(unique),
        "suspicious_count": len(suspicious),
        "divisions": sorted(set(d["division"] for d in unique)),
        "data": unique
    }

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"🎉 সফল! মোট {len(unique)} টি পণ্য")
    print(f"⚠️  সন্দেহজনক: {len(suspicious)} টি")
    print("=" * 60)

    create_github_issue(suspicious, len(unique))
