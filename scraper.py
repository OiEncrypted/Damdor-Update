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

# নামের ভেতরে থাকা অপ্রয়োজনীয় শব্দ ঠিক করার অভিধান
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
    "সয়োনর্ি (েযোি ১নলিঃ নর্নিন্ন ব্র্যোন্ড)": "সয়াবিন তেল (১ লিটার বোতল)",
    "সয়োনর্ি (েযোি 5নলিঃনর্নিন্ন ব্র্যোন্ড)": "সয়াবিন তেল (৫ লিটার বোতল)",
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
    "রুই (িোরের)": "রুই মাছ"
}

def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(PAGE_URL, headers=headers, timeout=30, verify=False)
    soup = BeautifulSoup(res.text, "html.parser")
    links = []
    for a in soup.find_all('a', href=True):
        if a['href'].endswith('.pdf'):
            links.append(a['href'])
    return list(dict.fromkeys(links))[:8]

def clean_name(name):
    # প্রথমে সম্পূর্ণ মিলে যাওয়া নাম খুঁজি
    if name in NAME_MAP:
        return NAME_MAP[name]
    
    # আংশিক মিলে যাওয়া নাম খুঁজি (শুরুর দিক মিললে)
    for key, val in NAME_MAP.items():
        if name.startswith(key):
            return val
    
    # কোনো মিল না পেলে অপ্রয়োজনীয় সংখ্যা বাদ দিই
    name = re.sub(r'\s+\d+\s*$', '', name)  # শেষের সংখ্যা
    name = re.sub(r'^\d+\s+', '', name)  # শুরুর সংখ্যা
    name = re.sub(r'[০-৯]+\s*$', '', name)  # শেষের বাংলা সংখ্যা
    
    return name.strip()

def parse_pdf(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(pdf_url, headers=headers, timeout=60, verify=False)
    
    items = []
    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        if len(pdf.pages) < 2:
            return []
        page = pdf.pages[1]
        
        words = page.extract_words()
        if not words:
            return []
        
        # লাইন গ্রুপিং
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
        
        # প্রতিটি লাইন পার্স করি
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
                
                # নাম পরিষ্কার করি
                name = clean_name(name_part)
                
                # যদি নামে কমপক্ষে ২টা অক্ষর থাকে
                if len(name) > 2 and not name.isdigit():
                    items.append({
                        "name": name,
                        "min_price": min_price,
                        "max_price": max_price
                    })
    return items

if __name__ == "__main__":
    links = get_pdf_links()
    if not links:
        print("PDF পাওয়া যায়নি")
        exit()
    
    print("PDF পার্স করা হচ্ছে...")
    items = parse_pdf(links[0])
    
    if items:
        data = {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total": len(items),
            "items": items
        }
        with open("prices.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"সফল! {len(items)} টি পণ্য পাওয়া গেছে")
    else:
        print("কোনো ডেটা পাওয়া যায়নি")
