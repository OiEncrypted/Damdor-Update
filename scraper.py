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
# ১. পণ্যের নাম ঠিক করার বিশাল অভিধান
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
    "সয়োনর্ি (ক োলো)": "সয়াবিন তেল (কালো)",
    "পোম (ক োলো)": "পাম তেল (কালো)",
    "সয়োনর্ি (েযোি ১নলিঃ নর্নিন্ন ব্র্যোন্ড)": "সয়াবিন তেল (১ লিটার)",
    "সয়োনর্ি (েযোি 5নলিঃনর্নিন্ন ব্র্যোন্ড)": "সয়াবিন তেল (৫ লিটার)",
    "সনরেো (ক োলো)": "সরিষার তেল (কালো)",
    "আমেোিীকৃি (সোেো-ক োলো)": "চিনি (সাদা-কালো)",
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
    "সর্নি": "সিম",
    "শসো": "শসা",
    "িোলকুমড়ো (িোনল)": "চালকুমড়া (জালি)",
    "নসম": "নয়নতারা",
    "ফুলেনপ": "ফুলকপি",
    "র্াঁধোেনপ": "বাঁধাকপি",
    "মুলো": "মুলা",
    "উরে/েরল্লো": "উড়হি/বরবটি",
    "েচুরলনি": "চিচিঙ্গা/ঝিঙ্গা",
    "রুই (িোরের)": "রুই মাছ",
    "ডোল": "ডাল",
    "মসুর": "মসুর ডাল",
    "মুগ": "মুগ ডাল",
    "সনরেো": "সরিষা",
    "বুট": "বুট",
    "ক োলো": "কালো",
    "চিচিিংগা": "চিচিঙ্গা",
    "মসলো": "মসলা",
    "সয়োনর্ি": "সয়াবিন"
}

# ==========================================
# ২. পেজ থেকে PDF লিংক বের করা
# ==========================================
def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30, verify=False)
        soup = BeautifulSoup(res.text, "html.parser")
        links = []
        for a in soup.find_all('a', href=True):
            if a['href'].endswith('.pdf'):
                links.append(a['href'])
        # ডুপ্লিকেট বাদ দিয়ে প্রথম ৮টা লিংক নিই (৮ বিভাগ)
        unique_links = list(dict.fromkeys(links))[:8]
        return unique_links
    except Exception as e:
        print(f"লিংক খুঁজতে সমস্যা: {e}")
        return []

# ==========================================
# ৩. নাম পরিষ্কার করার স্মার্ট ফাংশন
# ==========================================
def clean_name(name):
    name = name.strip()
    
    # ১. অভিধানে হুবহু মিললে
    if name in NAME_MAP:
        return NAME_MAP[name]
    
    # ২. অভিধানে আংশিক মিললে (শুরুর দিক মিললে)
    for key, val in NAME_MAP.items():
        if name.startswith(key):
            name = val
            break
            
    # ৩. অপ্রয়োজনীয় সংখ্যা বা চিহ্ন বাদ দেওয়া
    name = re.sub(r'^\d+\s+', '', name)          # শুরুর সংখ্যা
    name = re.sub(r'\s+\d+\s*$', '', name)       # শেষের সংখ্যা
    name = re.sub(r'[০-৯]+\s*$', '', name)      # শেষের বাংলা সংখ্যা
    name = re.sub(r'[\-\_\.\,\/]+$', '', name)   # শেষের চিহ্ন
    name = re.sub(r'\s+', ' ', name)             # অতিরিক্ত স্পেস
    
    # ৪. যদি নাম খুব ছোট হয়ে যায়
    if len(name) < 3:
        return "অজানা পণ্য"
        
    return name.strip()

# ==========================================
# ৪. মূল পার্সিং ফাংশন
# ==========================================
def parse_pdf(pdf_url, division_name):
    headers = {"User-Agent": "Mozilla/5.0"}
    items = []
    
    try:
        res = requests.get(pdf_url, headers=headers, timeout=60, verify=False)
        
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            # ২ নাম্বার পেজ (মূল টেবিল)
            if len(pdf.pages) < 2:
                return []
            page = pdf.pages[1]
            
            words = page.extract_words()
            if not words:
                return []
            
            # শব্দগুলোকে লাইন অনুযায়ী গ্রুপ করা (top এর পার্থক্য ৫ পিক্সেল)
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
            
            # প্রতিটি লাইন প্রসেস করা
            for line_words in lines:
                line_words = sorted(line_words, key=lambda x: x['x0'])
                line_text = " ".join(w['text'] for w in line_words)
                
                # দামের প্যাটার্ন (যেমন 60.00 - 70.00)
                price_match = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", line_text)
                
                if price_match:
                    min_price = price_match.group(1)
                    max_price = price_match.group(2)
                    
                    # দামের আগের অংশটুকু নাম
                    name_part = line_text[:price_match.start()].strip()
                    
                    # নাম পরিষ্কার করা
                    clean = clean_name(name_part)
                    
                    # যদি নাম "অজানা পণ্য" না হয়
                    if clean != "অজানা পণ্য":
                        items.append({
                            "division": division_name,
                            "name": clean,
                            "min_price": min_price,
                            "max_price": max_price
                        })
    except Exception as e:
        print(f"PDF পার্সে সমস্যা ({division_name}): {e}")
        
    return items

# ==========================================
# ৫. মেইন এক্সিকিউশন
# ==========================================
if __name__ == "__main__":
    print("লিংক খোঁজা হচ্ছে...")
    links = get_pdf_links()
    
    if not links:
        print("কোনো PDF পাওয়া যায়নি")
        exit()
        
    divisions = ["ঢাকা", "চট্টগ্রাম", "খুলনা", "রাজশাহী", "বরিশাল", "রংপুর", "সিলেট", "ময়মনসিংহ"]
    
    all_data = []
    
    for i, link in enumerate(links):
        div_name = divisions[i] if i < len(divisions) else f"বিভাগ {i+1}"
        print(f"[{i+1}/{len(links)}] {div_name} বিভাগের PDF পার্স করা হচ্ছে...")
        
        items = parse_pdf(link, div_name)
        all_data.extend(items)
        print(f" -> {div_name}: {len(items)} টি পণ্য পাওয়া গেছে")

    # ফাইনাল JSON স্ট্রাকচার
    final_json = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(all_data),
        "data": all_data
    }
    
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
        
    print(f"\nসব শেষ! মোট {len(all_data)} টি পণ্যের ডেটা prices.json এ সেভ হয়েছে।")
