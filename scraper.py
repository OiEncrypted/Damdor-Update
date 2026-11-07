import requests
from bs4 import BeautifulSoup
import pdfplumber
import json
import re
import io
from datetime import datetime

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"

def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")
        
        pdf_links = []
        # পেজের সব <a> ট্যাগ খুঁজছি যাদের href-এ .pdf আছে
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.endswith('.pdf'):
                pdf_links.append(href)
                
        # আমরা শুধু প্রথম ৮টা লিংক নিব (৮ বিভাগের জন্য)
        # কারণ এর পরে পুরোনো তারিখের লিংক থাকতে পারে
        return list(dict.fromkeys(pdf_links))[:8] 
    except Exception as e:
        print("লিংক খুঁজতে সমস্যা:", e)
        return []

def parse_pdf(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        print(f"PDF ডাউনলোড হচ্ছে: {pdf_url[:80]}...")
        res = requests.get(pdf_url, headers=headers, timeout=60)
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            # ২ নাম্বার পেজে মূল টেবিল থাকে
            if len(pdf.pages) < 2: return []
            text = pdf.pages[1].extract_text()
            
        if not text: return []

        items = []
        lines = text.split("\n")
        for line in lines:
            # টেবিলের লাইন খোঁজা (যেখানে কমপক্ষে ২টা সংখ্যা আছে)
            match = re.search(r"([\d.]+)\s*-\s*([\d.]+)", line)
            if match:
                min_price = match.group(1)
                max_price = match.group(2)
                
                # দামের আগের অংশটুকু নাম হিসেবে নিচ্ছি
                name = line[:match.start()].strip()
                
                # নাম থেকে অপ্রয়োজনীয় অক্ষর বাদ দেওয়া (যেমন 'প্রতি কেজি', 'প্রনিটি')
                name = re.sub(r'প্রতি\s*কেজি|প্রনিটি|প্রনি\s*কেনি|নলটোর', '', name).strip()
                
                if len(name) > 2: # নাম খুব ছোট হলে বাদ
                    items.append({
                        "name": name,
                        "min_price": min_price,
                        "max_price": max_price
                    })
        return items
    except Exception as e:
        print(f"PDF পার্স করতে সমস্যা: {e}")
        return []

if __name__ == "__main__":
    print("লিংক খোঁজা হচ্ছে...")
    links = get_pdf_links()
    
    if not links:
        print("কোনো PDF লিংক পাওয়া যায়নি।")
        exit()

    print(f"{len(links)} টি লিংক পাওয়া গেছে। প্রথম লিংক থেকে ডেটা পার্স করা হচ্ছে...")
    
    # আপাতত আমরা শুধু প্রথম লিংক (ঢাকা) পার্স করছি
    items = parse_pdf(links[0])
    
    if items:
        final_data = {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_items": len(items),
            "items": items
        }
        with open("prices.json", "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        print(f"সফল! {len(items)} টি পণ্যের ডেটা prices.json এ সেভ হয়েছে।")
    else:
        print("PDF থেকে কোনো ডেটা বের করা যায়নি।")
