import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from bs4 import BeautifulSoup
import json
import re
import io
import os
from datetime import datetime
from sohojpath import BanglaPdfParser, ParserConfig

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
    
    # PDF ফাইলটা ডিস্কে সেভ করি (sohojpath ফাইলের পাথ চায়)
    with open("temp.pdf", "wb") as f:
        f.write(res.content)
    
    parser = BanglaPdfParser(ParserConfig(language="ben", dpi=300))
    pages = list(parser.parse("temp.pdf", pages=[2]))
    if not pages:
        return []
    
    page = pages[0]
    words = page.words
    if not words:
        return []
    
    lines = []
    current_line = []
    last_top = None
    for w in sorted(words, key=lambda x: (x.top, x.left)):
        if last_top is None or abs(w.top - last_top) < 10:
            current_line.append(w)
        else:
            if current_line:
                lines.append(current_line)
            current_line = [w]
        last_top = w.top
    if current_line:
        lines.append(current_line)
    
    items = []
    for line_words in lines:
        line_text = " ".join(w.text for w in line_words)
        match = re.search(r"([\d.]+)\s*-\s*([\d.]+)", line_text)
        if match:
            min_p = match.group(1)
            max_p = match.group(2)
            
            name_words = []
            for w in line_words:
                if re.search(r"[\d.]+\s*-\s*[\d.]+", w.text):
                    break
                if re.search(r"[a-zA-Z\u0980-\u09FF]", w.text):
                    name_words.append(w.text)
            
            name = " ".join(name_words).strip()
            name = re.sub(r"প্রতি\s*কেজি|প্রনিটি|প্রনি\s*কেনি|নলটোর", "", name).strip()
            
            if len(name) > 2 and not name.isdigit():
                items.append({
                    "name": name,
                    "min_price": min_p,
                    "max_price": max_p
                })
    
    return items

if __name__ == "__main__":
    links = get_pdf_links()
    if not links:
        print("কোনো PDF পাওয়া যায়নি")
        exit()
    
    print("OCR চলছে, একটু অপেক্ষা করুন...")
    items = parse_pdf(links[0])
    
    # temp ফাইলটা মুছে ফেলি
    if os.path.exists("temp.pdf"):
        os.remove("temp.pdf")
    
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
        print("OCR থেকে ডেটা বের করা যায়নি")
