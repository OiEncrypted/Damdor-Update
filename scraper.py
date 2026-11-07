import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from bs4 import BeautifulSoup
import json
import re
import io
import os
from datetime import datetime
import pdfplumber

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"

# ==========================================
# NAME_MAP — সঠিক পুরো নাম
# ==========================================
NAME_MAP = {
    "আটো প্যোরেট-সোেো": "আটা (প্যাকেট)",
    "ক োলো": "ডাল (কালো)",
    "মসুর (উন্নি)": "মসুর ডাল (উন্নত)",
    "মসুর (কমোটো)": "মসুর ডাল (মোটা)",
    "মুগ (সরু- উন্নি)": "মুগ ডাল (সরু-উন্নত)",
    "মুগ -(কমোটো)": "মুগ ডাল (মোটা)",
    "ক সোরী": "কেসারি ডাল",
    "মোশ েলোই": "মাষকলাই ডাল",
    "বুট": "বুট (ছোলা)",
    "সয়োনর্ি (ক োলো)": "সয়াবিন তেল (কালো)",
    "পোম (ক োলো)": "পাম তেল (কালো)",
    "সনরেো (ক োলো)": "সরিষার তেল (কালো)",
    "আমেোিীকৃি (সোেো-ক োলো)": "চিনি (সাদা)",
    "কেঁয়োি (কেশী)": "পেঁয়াজ (দেশি)",
    "রসুি (কেশী)": "রসুন (দেশি)",
    "রসুি (িোয়িো)": "রসুন (চায়না)",
    "আেো (আমেোিীকৃি)": "আদা (আমদানীকৃত)",
    "শুেিো মনরি (কেশী)": "শুকনা মরিচ (দেশি)",
    "োঁিো মনরি": "কাঁচা মরিচ",
    "আলু (পুরোিি)": "আলু (পুরোনো)",
    "কর্গুি": "কাঁকরোল",
    "োঁিো কেঁরপ": "কাঁচা পেঁপে",
    "নমনি কুমড়ো": "মিষ্টি কুমড়া",
    "চিচিিংগা": "চিচিংগা",
    "মুখীকচু": "মুখীকচু",
    "র্রর্টি": "ঢেঁড়স",
    "লোউ": "লাউ",
    "পটল": "পটল",
    "শসো": "শসা",
    "িোলকুমড়ো (িোনল)": "চালকুমড়া (জালি)",
    "নসম": "নয়নতারা",
    "ফুলেনপ": "ফুলকপি",
    "র্াঁধোেনপ": "বাঁধাকপি",
    "মুলো": "মুলা",
    "উরে/েরল্লো": "উড়হি/বরবটি",
    "েচুরলনি": "চিচিঙ্গা/ঝিঙ্গা",
    "রুই (িোরের)": "রুই মাছ",
}

# ==========================================
# REPLACEMENTS — ভাঙা শব্দ ফিক্সিং
# ==========================================
REPLACEMENTS = {
    # ========== একক ==========
    "প্রনি কেনি": "", "প্রনিটি": "", "প্রতি কেনি": "",
    "প্রলি কেলি": "প্রতি কেজি", "প্রলি": "প্রতি", "কেলি": "কেজি",
    "নলটোর": "লিটার", "প্রতি লিটার": "লিটার", "১ নলটোর": "১ লিটার",
    "৫ নলটোর": "৫ লিটার",
    "প্যাকেটিাি": "প্যাকেটজাত", "পনিপ্যোে": "প্যাকেট",
    "পনলপ্যোে": "প্যাকেট", "প্যোরেটিোি": "প্যাকেটজাত",
    "প্যোে:": "প্যাকেট ", "ব্র্যোন্ড": "ব্র্যান্ড",
    "নর্নিন্ন": "বিভিন্ন", "নর্নভন্ন": "বিভিন্ন",
    "প্রনিহোনি": "৪ পিস", "প্রনি হোনি": "৪ পিস",
    "৪টি": "৪ পিস", "১ পিছ": "১ পিস",

    # ========== মাংস ==========
    "মোাংস": "মাংস", "মোংস": "মাংস",
    "খোনসর": "খাসি",
    "ছোগরির": "ছাগলের", "ছোগল": "ছাগল",
    "োগরির": "গরুর", "গরু (হোড়সহ)": "গরু (হাড়সহ)",
    "হোড়সহ": "(হাড়সহ)",

    # ========== মুরগি ==========
    "কমোরগ": "মুরগি", "মুরনগ": "মুরগি", "মুিরগ": "মুরগি",
    "মুিগী": "মুরগি", "বমািগ": "মুরগি",
    "কদশী": "দেশি", "কেশী": "দেশি", "কদিী": "দেশি", "কদনশ": "দেশি",
    "বেশী": "দেশি", "েে": "দেশি",
    "কসোিোিী": "সোনালি", "কসোিোলী": "সোনালি",
    "বসানািী": "সোনালি", "বসাঃ": "সোনালি",
    "কস/": "সোনালি", "কস": "সোনালি",
    "িয়িোর": "ব্রয়লার", "িয়লোর": "ব্রয়লার",
    "েোিোর": "ব্রয়লার", "িোিোর": "ব্রয়লার",
    "িাযোন্ত": "", "িযোন্ত": "", "িযান্ত": "", "িাযান্ত": "",
    "েোিোরর্োড": "ব্রয়লার", "র্োড": "", "বও": "",
    "মুরগি মুরগি": "মুরগি", "মুরগিমুরগি": "মুরগি",
    "মুরনগমুরনগ": "মুরগি", "মুরগিকমোরগ": "মুরগি",
    "মুরনগকমোরগ": "মুরগি",

    # ========== ডিম ==========
    "নডমিঃ": "ডিম", "নডমঃ": "ডিম", "রডমঃ": "ডিম", "নডম": "ডিম",
    "ডিমমুরগি": "ডিম",
    "ফোম বসোদো": "ফার্মের ডিম", "ফোম বসোেো": "ফার্মের ডিম",
    "ফোমবসোেো": "ফার্মের ডিম", "ফোমবসোদো": "ফার্মের ডিম",
    "ফোম": "ফার্ম", "বসোদো": "ডিম", "বসোেো": "ডিম",
    "ফার্ম িোি": "ফার্মের ডিম", "ফার্ম িো": "ফার্মের ডিম",
    "ফার্ম িোি": "ফার্মের ডিম",
    "েিো": "ডিম", "সোগর": "হাঁস", "চাঁপো": "চায়না",
    "সোগর": "হাঁস",

    # ========== মাছ ==========
    "মোছ": "মাছ", "মো": "মাছ", "মাছ োনর": "মাছ",
    "মাছঝোনর": "মাঝারি",
    "ইনিশ": "ইলিশ", "ইনিি": "ইলিশ",
    "চোরষর": "দেশি", "চোরের": "দেশি", "চোরির": "দেশি",
    "কিিোনপয়ো": "কাতলা", "কিিোনপেো": "কাতলা",
    "পোাংগোস": "পাঙাশ", "পাংগাস": "পাঙাশ",
    "েোিি": "তেলাপিয়া", "ক োট": "বড়", "ক োট": "বড়",

    # ========== দুধ ==========
    "গুুঁরড়ো": "গুঁড়া", "গুকড়া": "গুঁড়া", "গুড়া": "গুঁড়া",
    "গুুঁরড়ো": "গুঁড়া", "দুি": "দুধ",
    "গুঁড়া দুধ গুঁড়া": "গুঁড়া দুধ",
    "গুুঁরড়ো দুধ গুুঁরড়ো": "গুঁড়া দুধ",

    # ========== ফল ==========
    "আরপি": "আপেল", "আরেল": "আপেল",
    "কপয়োরো": "পেঁয়ারা",
    "িাম্বুরো": "লেবু",
    "আমকৃি": "আমদানীকৃত",
    "নিনি": "চিনি",
    "সোেো": "সাদা",

    # ========== চাল ==========
    "চোি": "চাল", "চোি-": "চাল-", "ি র্": "চাল", "ির্ণ": "চাল",
    "পোিোম": "পাটনা",
    "মোঝোনর": "মাঝারি", "মো োনর": "মাঝারি",
    "নি ধোি": "নী ধান", "নিধোি": "নী ধান", "নি-ধোি": "নী ধান",
    "নি িোি": "নী ধান",
    "স্বণোব": "সয়াবিন", "স্বিোব": "সয়াবিন",
    "নর্আর": "ব্রি", "নর্ররোই": "ব্রি",
    "রম": "ব্রি",
    "নিরোশোইি": "বিরশাইল", "নিরোিোইি": "বিরশাইল",
    "স্থোিীয়": "স্থানীয়", "েোটো": "জাতের", "েোটোর": "জাতের",
    "কর্োররো": "কারওয়ান", "কর্োর": "কারওয়ান",
    "নহরো": "নাইজার", "নচেি": "দেশি",
    "িোনিরগোল্ড": "গোল্ড", "নোনিরগোল্ড": "গোল্ড",
    "Non": "", "িপ্রিনিযো নকেে": "ইপ্রিনিয়া কেট",
    "কমোটো": "মোটা", "কমাছটো": "মোটা",
    "কমাছ োট": "মোটা",

    # ========== অন্যান্য ==========
    "রচরন": "মরিচ", "মনরি": "মরিচ",
    "ব ািা": "কাঁচা", "ক োলো": "কালো",
    "সাধাির্": "সাধারণ", "উন্নি": "উন্নত",
    "(cid:10)": "", "(cid:XX)": "", "(cid:": "", ")": "",
    "SL 4 H": "SL-4H", "SL4H": "SL-4H",
    "ফামণ": "ফার্ম",
    "গি মাছরসর": "গরম মসলা",
    "িডিমর": "ব্রয়লার",
    "িোি": "ফার্মের",
    "েোটোরর": "জাতের",
    "/ব গকস-োিমুোরিনী)গ": "",
    "র্ কম োড োর": "",
    "৪৪": "", "৪৫": "", "৪৬": "", "৪৭": "", "৪৮": "",
    "৪৯": "", "৫১": "", "৫২": "", "৫৩": "", "৫৫": "",
    "৫৬": "", "৫৭": "", "৫৮": "", "৫৯": "", "৬০": "",
    "৬১": "", "৬২": "", "৬৩": "", "১২": "", "১৫": "",
    "২": "", "৩": "", "৪": "", "৫": "", "৭": "",
}

# সন্দেহজনক শব্দের মার্কার
BROKEN_MARKERS = [
    "োনর", "িোি", "েোিোর", "িোিোর", "নচেি", "কমাছটো",
    "িযান্ত", "িযোন্ত", "িাযোন্ত", "ির্ণ", "প্রলি", "কেলি",
    "মাছঝোনর", "গকস", "েোটোর", "িোনিরগোল্ড", "স্টোিীয়",
    "িপ্রিনিযো", "নকেে", "ফামণ", "মাছ োনর", "নিরোশোইি",
    "নিরোিোইি", "শুেিো", "িাযোন্ত", "বমািগ",
    "সোেো", "িাম্বুরো", "কপয়োরো", "পনিপ্যোে", "পনলপ্যোে",
    "প্রনি", "প্রনিটি", "মোছ", "মোাংস", "মোংস",
]


def is_suspicious(name):
    """নাম সন্দেহজনক কিনা চেক করে"""
    if not name or len(name) < 3:
        return True
    if len(name) > 60:
        return True
    if re.search(r"\(cid:", name):
        return True
    if re.search(r"[^\u0980-\u09FFa-zA-Z0-9\s\(\)\/\-\.,%]", name):
        return True
    digit_groups = re.findall(r"\d{2,}", name)
    if len(digit_groups) >= 3:
        return True
    for marker in BROKEN_MARKERS:
        if marker in name:
            return True
    return False


def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30, verify=False)
        soup = BeautifulSoup(res.text, "html.parser")
        links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].endswith('.pdf')]
        return list(dict.fromkeys(links))[:8]
    except Exception as e:
        print(f"লিংক সমস্যা: {e}")
        return []


def clean_name(name):
    name = name.strip()

    if name in NAME_MAP:
        return NAME_MAP[name]

    for key, val in NAME_MAP.items():
        if name.startswith(key):
            return val

    for bad, good in REPLACEMENTS.items():
        name = name.replace(bad, good)

    name = re.sub(r"^[\d০-৯]+\s+", "", name)
    name = re.sub(r"\s+[\d০-৯]+\s*$", "", name)
    name = re.sub(r"[\_\-\.\,\/]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    words = name.split()
    final_words = []
    for w in words:
        if not final_words or final_words[-1] != w:
            final_words.append(w)
    name = " ".join(final_words)

    if len(name) < 2 or name.isdigit():
        return ""

    return name


def parse_pdf(pdf_url, division_name, suspicious_list):
    headers = {"User-Agent": "Mozilla/5.0"}
    items = []
    try:
        res = requests.get(pdf_url, headers=headers, timeout=60, verify=False)
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            if len(pdf.pages) < 2:
                return []

            page = pdf.pages[1]
            words = page.extract_words()
            if not words:
                return []

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
        print(f"PDF সমস্যা ({division_name}): {e}")
    return items


def create_github_issue(suspicious_items, total_count):
    """GitHub Issues-এ ইস্যু তৈরি করে — GitHub নিজেই ইমেইলে জানাবে"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not token or not repo:
        print("⚠️ GITHUB_TOKEN বা GITHUB_REPOSITORY নেই — ইস্যু তৈরি হচ্ছে না")
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
        "### কী করতে হবে",
        "নিচের `Raw Text` দেখে সঠিক নাম ঠিক করে `scraper.py`-এর `REPLACEMENTS`-এ যোগ করো।",
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

    body_lines.append("\n---\n_এই ইস্যুটি স্বয়ংক্রিয়ভাবে তৈরি হয়েছে।_")
    body = "\n".join(body_lines)

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {
        "title": title,
        "body": body,
        "labels": ["suspicious-names", "auto-generated"]
    }

    try:
        res = requests.post(url, json=data, headers=headers, timeout=30)
        if res.status_code == 201:
            print(f"✅ Issue তৈরি হয়েছে: {res.json()['html_url']}")
        else:
            print(f"❌ Issue ব্যর্থ: {res.status_code} — {res.text}")
    except Exception as e:
        print(f"❌ Issue exception: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 বাজারদর স্ক্র্যাপার শুরু হচ্ছে...")
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

    # ডুপ্লিকেট বাদ
    seen, unique = set(), []
    for item in all_data:
        key = (item["division"], item["name"], item["min_price"], item["max_price"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

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
    print(f"⚠️  সন্দেহজনক নাম: {len(suspicious)} টি")
    print("=" * 60)

    # সন্দেহজনক নাম থাকলে GitHub Issue তৈরি করি
    create_github_issue(suspicious, len(unique))
