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
        # শুধু ২ নাম্বার পেজ (মূল টেবিল)
        if len(pdf.pages) < 2:
            return []
        page = pdf.pages[1]
        
        # টেক্সট এক্সট্রাক্ট করি
        text = page.extract_text()
        if not text:
            return []
        
        # প্রতিটি লাইন আলাদা করি
        lines = text.split("\n")
        for line in lines:
            # লাইনে দামের প্যাটার্ন (যেমন 60.00 - 70.00) আছে কিনা
            # এখানে আমরা সংখ্যা এবং ড্যাশ খুঁজছি
            match = re.search(r"([\d.]+)\s*-\s*([\d.]+)", line)
            if match:
                min_price = match.group(1)
                max_price = match.group(2)
                
                # দামের আগের অংশটুকু নাম হিসেবে নিচ্ছি
                name_part = line[:match.start()].strip()
                
                # নাম থেকে অপ্রয়োজনীয় শব্দ বাদ দিচ্ছি
                name = re.sub(r'প্রতি\s*কেজি|প্রনিটি|প্রনি\s*কেনি|নলটোর', '', name_part).strip()
                
                # যদি নাম খুব ছোট না হয়
                if len(name) > 2:
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
