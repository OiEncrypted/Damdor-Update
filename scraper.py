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

def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(PAGE_URL, headers=headers, timeout=30, verify=False)
    soup = BeautifulSoup(res.text, "html.parser")
    links = []
    for a in soup.find_all('a', href=True):
        if a['href'].endswith('.pdf'):
            links.append(a['href'])
    return list(dict.fromkeys(links))[:8]

def parse_pdf(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(pdf_url, headers=headers, timeout=60, verify=False)
    
    items = []
    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        if len(pdf.pages) < 2:
            return []
        page = pdf.pages[1]
        
        # প্রতিটি শব্দের অবস্থান সহ বের করি
        words = page.extract_words()
        if not words:
            return []
        
        # শব্দগুলোকে লাইন অনুযায়ী গ্রুপ করি (top এর পার্থক্য ৫ পিক্সেলের কম)
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
        
        # প্রতিটি লাইনের শব্দগুলোকে x-অক্ষ অনুযায়ী সাজাই
        for line_words in lines:
            line_words = sorted(line_words, key=lambda x: x['x0'])
            
            # লাইনের টেক্সট
            line_text = " ".join(w['text'] for w in line_words)
            
            # এই লাইনে দামের প্যাটার্ন আছে কিনা (যেমন 60.00 - 70.00)
            # আমরা চেক করি লাইনে কমপক্ষে ২টা সংখ্যা আছে কিনা, আর মাঝে ড্যাশ
            price_match = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", line_text)
            
            if price_match:
                min_price = price_match.group(1)
                max_price = price_match.group(2)
                
                # দামের আগের অংশটুকু নাম হিসেবে নিই
                name_part = line_text[:price_match.start()].strip()
                
                # নাম থেকে অপ্রয়োজনীয় শব্দ বাদ দিই
                name = re.sub(r'প্রতি\s*কেজি|প্রনিটি|প্রনি\s*কেনি|নলটোর|প্রতি\s*লিটার', '', name_part, flags=re.IGNORECASE).strip()
                
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
