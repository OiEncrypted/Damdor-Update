import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from bs4 import BeautifulSoup
import json
import re
import io
from datetime import datetime
import pdfplumber

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"

# ==========================================
# সম্পূর্ণ NAME_MAP (ঢাকা + অন্যান্য বিভাগের জন্য)
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
# অটো-ক্লিনিং রিপ্লেসমেন্ট (সব বিভাগের জন্য)
# ==========================================
REPLACEMENTS = {
    # একক
    "প্রনি কেনি": "", "প্রনিটি": "", "নলটোর": "লিটার", "প্রতি কেনি": "",
    "প্যাকেটিাি": "প্যাকেটজাত", "পনিপ্যোে": "প্যাকেট", "পনলপ্যোে": "প্যাকেট",
    "প্যোরেটিোি": "প্যাকেটজাত", "প্রতি লিটার": "লিটার",
    
    # মাংস
    "মোাংস": "মাংস", "মোংস": "মাংস", "মাংস": "মাংস",
    "গরু": "গরু", "খোনসর": "খাসি", "খাসি": "খাসি",
    "ছোগরির": "ছাগলের", "ছোগল": "ছাগল", "ছাগলের": "ছাগলের",
    
    # মুরগি
    "কমোরগ": "মুরগি", "মুরনগ": "মুরগি", "মুিরগ": "মুরগি", 
    "মুিগী": "মুরগি", "মুরগি": "মুরগি", "বমািগ": "মুরগি",
    "কদশী": "দেশি", "কেশী": "দেশি", "কদিী": "দেশি", "দেশি": "দেশি",
    "কসোিোিী": "সোনালি", "কসোিোলী": "সোনালি", "বসানািী": "সোনালি",
    "বসাঃ": "সোনালি", "সোনালি": "সোনালি",
    "িয়িোর": "ব্রয়লার", "িয়লোর": "ব্রয়লার", "ব্রয়লার": "ব্রয়লার",
    "িযোন্ত": "", "িাযোন্ত": "",
    "েে/": "দেশি/", "েেণ/": "দেশি/",
    
    # ডিম
    "নডমিঃ": "ডিম", "নডমঃ": "ডিম", "রডমঃ": "ডিম", "নডম": "ডিম",
    "ফোম বসোদো": "ফার্ম", "ফোম বসোেো": "ফার্ম", "ফোমবসোেো": "ফার্ম",
    "ফোম": "ফার্ম", "বসোদো": "ডিম", "বসোেো": "ডিম",
    "েিো": "ডিম", "সোগর": "হাঁস", "চাঁপো": "চায়না", "কসো": "হাঁস",
    "৪টি": "৪ পিস", "১ পিছ": "১ পিস", "প্রনিহোনি": "",
    
    # মাছ
    "মোছ": "মাছ", "মো": "মাছ", "ইনিশ": "ইলিশ", "ইনিি": "ইলিশ",
    "চোরষর": "দেশি", "চোরের": "দেশি", "চোরির": "দেশি",
    "কিিোনপয়ো": "কাতলা", "কাতলা": "কাতলা",
    "পোাংগোস": "পাঙাশ", "পাংগাস": "পাঙাশ", "পাঙাশ": "পাঙাশ",
    "রুই": "রুই", "েোিি": "তেলাপিয়া", "তেলাপিয়া": "তেলাপিয়া",
    
    # দুধ
    "গুুঁরড়ো": "গুঁড়া", "গুকড়া": "গুঁড়া", "গুড়া": "গুঁড়া", "গুঁড়া": "গুঁড়া",
    "দুধ": "দুধ", "দুি": "দুধ", "গুুঁরড়ো": "গুঁড়া",
    
    # ফল
    "আরপি": "আপেল", "আরেল": "আপেল", "আপেল": "আপেল",
    "কপয়োরো": "পেঁয়ারা", "পেঁয়ারা": "পেঁয়ারা",
    "িাম্বুরো": "লেবু", "লেবু": "লেবু",
    
    # চাল
    "চাল": "চাল", "চোি": "চাল", "চোি-": "চাল-", "চাল-": "চাল-",
    "ি র্": "চাল", "চাল": "চাল",
    "পোিোম": "পাটনা", "পাটনা": "পাটনা",
    "মোঝোনর": "মাঝারি", "মো োনর": "মাঝারি", "মাঝারি": "মাঝারি",
    "নি ধোি": "নী ধান", "নিধোি": "নী ধান", "নি-ধোি": "নী ধান",
    "সুগন্ধী": "সুগন্ধী", "গুটি": "গুটি",
    "স্বণোব": "সয়াবিন", "স্বিোব": "সয়াবিন", "সয়াবিন": "সয়াবিন",
    "উফশী": "উফশী", "নর্আর": "ব্রি", "ব্রি": "ব্রি", "নর্ররোই": "ব্রি",
    "নিরোশোইি": "বিরশাইল", "নিরোিোইি": "বিরশাইল", "বিরশাইল": "বিরশাইল",
    "িম্পো": "শম্পা", "শম্পা": "শম্পা", "েোটোনর": "জাতের", "জাতের": "জাতের",
    "কর্োররো": "কারওয়ান", "কারওয়ান": "কারওয়ান",
    "নহরো": "নাইজার", "নাইজার": "নাইজার",
    "সরু": "সরু", "মোটা": "মোটা", "মোট": "মোটা", "কমোটো": "মোটা",
    "উন্নি": "উন্নত", "উন্নত": "উন্নত",
    "িোয়িো": "চায়না", "কেশী": "দেশি", "দেশি": "দেশি",
    
    # অন্যান্য
    "রচরন": "মরিচ", "মরিচ": "মরিচ", "ব ািা": "কাঁচা", "কাঁচা": "কাঁচা",
    "সাধাির্": "সাধারণ", "সাধারণ": "সাধারণ",
    "1 বেরি": "১ কেজি", "১ বেরি": "১ কেজি", "5 বেরি": "৫ কেজি",
    "(cid:10)": "", "(cid:XX)": "",
    "SL 4 H": "SL-4H", "SL4H": "SL-4H",
}

def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30, verify=False)
        soup = BeautifulSoup(res.text, "html.parser")
        links = []
        for a in soup.find_all('a', href=True):
            if a['href'].endswith('.pdf'):
                links.append(a['href'])
        return list(dict.fromkeys(links))[:8]
    except Exception as e:
        print(f"লিংক সমস্যা: {e}")
        return []

def clean_name(name):
    name = name.strip()
    
    # ১. পুরো নাম NAME_MAP এ আছে কিনা
    if name in NAME_MAP:
        return NAME_MAP[name]
    
    # ২. আংশিক মিললে
    for key, val in NAME_MAP.items():
        if name.startswith(key):
            return val
    
    # ৩. REPLACEMENTS দিয়ে রিপ্লেস
    for bad, good in REPLACEMENTS.items():
        name = name.replace(bad, good)
    
    # ৪. শুরুর সংখ্যা/বাংলা সংখ্যা বাদ
    name = re.sub(r'^[\d০-৯]+\s+', '', name)
    
    # ৫. শেষের সংখ্যা/বাংলা সংখ্যা বাদ
    name = re.sub(r'\s+[\d০-৯]+\s*$', '', name)
    
    # ৬. মাঝের অপ্রয়োজনীয় চিহ্ন বাদ
    name = re.sub(r'[\_\-\.\,\/]+', ' ', name)
    
    # ৭. একাধিক স্পেস এক করা
    name = re.sub(r'\s+', ' ', name).strip()
    
    # ৮. ডুপ্লিকেট শব্দ বাদ (যেমন "মুরগি মুরগি")
    words = name.split()
    final_words = []
    for w in words:
        if not final_words or final_words[-1] != w:
            final_words.append(w)
    name = " ".join(final_words)
    
    # ৯. খুব ছোট হলে
    if len(name) < 2 or name.isdigit() or name == "অজানা":
        return "অন্যান্য পণ্য"
    
    return name

def parse_pdf(pdf_url, division_name):
    headers = {"User-Agent": "Mozilla/5.0"}
    items = []
    
    try:
        res = requests.get(pdf_url, headers=headers, timeout=60, verify=False)
        
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            if len(pdf.pages) < 2:
                return []
            
            # ২ নাম্বার পেজ (মূল টেবিল)
            page = pdf.pages[1]
            words = page.extract_words()
            if not words:
                return []
            
            # লাইন গ্রুপিং (top এর পার্থক্য ৫ পিক্সেল)
            lines = []
            current_line = []
            last_top = None
            
            for w in sorted(words, key=lambda x: (x['top'], x['x0'])):
                if last_top is None or abs(w['top'] - last_top) < 5:
                    current_line.append(w)
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = [w]
                last_top = w['top']
            if current_line:
                lines.append(current_line)
            
            # প্রতিটি লাইন প্রসেস
            for line_words in lines:
                line_words = sorted(line_words, key=lambda x: x['x0'])
                line_text = " ".join(w['text'] for w in line_words)
                
                # দামের প্যাটার্ন (60.00 - 70.00)
                price_match = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", line_text)
                
                if price_match:
                    min_price = price_match.group(1)
                    max_price = price_match.group(2)
                    
                    # দাম ০ না হলে
                    if float(min_price) > 0 and float(max_price) > 0:
                        name_part = line_text[:price_match.start()].strip()
                        clean = clean_name(name_part)
                        
                        if clean != "অন্যান্য পণ্য" and len(clean) > 2:
                            items.append({
                                "division": division_name,
                                "name": clean,
                                "min_price": min_price,
                                "max_price": max_price
                            })
    except Exception as e:
        print(f"PDF সমস্যা ({division_name}): {e}")
    
    return items

if __name__ == "__main__":
    print("=" * 60)
    print("বাজারদর স্ক্র্যাপার শুরু হচ্ছে...")
    print("=" * 60)
    
    links = get_pdf_links()
    if not links:
        print("❌ কোনো PDF পাওয়া যায়নি")
        exit()
    
    divisions = ["ঢাকা", "চট্টগ্রাম", "খুলনা", "রাজশাহী", "বরিশাল", "রংপুর", "সিলেট", "ময়মনসিংহ"]
    all_data = []
    
    for i, link in enumerate(links):
        div_name = divisions[i] if i < len(divisions) else f"বিভাগ-{i+1}"
        print(f"\n[{i+1}/8] {div_name} বিভাগ প্রসেস হচ্ছে...")
        
        items = parse_pdf(link, div_name)
        all_data.extend(items)
        print(f"  ✅ {div_name}: {len(items)} টি পণ্য পাওয়া গেছে")
    
    # ডুপ্লিকেট বাদ (একই বিভাগে একই নাম+দাম থাকলে)
    seen = set()
    unique_data = []
    for item in all_data:
        key = (item["division"], item["name"], item["min_price"], item["max_price"])
        if key not in seen:
            seen.add(key)
            unique_data.append(item)
    
    # ফাইনাল JSON
    final_json = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(unique_data),
        "divisions": list(set(d["division"] for d in unique_data)),
        "data": unique_data
    }
    
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print(f"🎉 সফল! মোট {len(unique_data)} টি ডেটা সেভ হয়েছে")
    print(f"📊 বিভাগ সংখ্যা: {len(final_json['divisions'])}")
    print("=" * 60)
