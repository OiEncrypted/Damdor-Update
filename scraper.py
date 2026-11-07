import requests
from bs4 import BeautifulSoup
import pdfplumber
import json
import re
import io
from datetime import datetime

# যে পেজে PDF-এর লিংকগুলো আছে
PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"

# বাংলা সংখ্যা থেকে ইংরেজি সংখ্যায় রূপান্তর
BN_DIGITS = "০১২৩৪৫৬৭৮৯"
EN_DIGITS = "0123456789"

def bn_to_en(text):
    return text.translate(str.maketrans(BN_DIGITS, EN_DIGITS))

def get_latest_pdf():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")
        # প্রথম PDF লিংকটাই সবচেয়ে নতুন (ঢাকা বিভাগ)
        links = soup.select("table a[href$='.pdf']")
        if links:
            return links[0]["href"]
    except Exception as e:
        print("PDF লিংক খুঁজতে সমস্যা:", e)
    return None

def clean_name(name):
    # PDF-এর এলোমেলো লেখা ঠিক করার ম্যাপিং
    replacements = {
        "প্রনি কেনি": "প্রতি কেজি",
        "প্রনিটি": "প্রতিটি",
        "নলটোর": "লিটার",
        "রসুি": "মসুর",
        "মুগ -(কমোটো)": "মুগ (মোটা)",
        "সনরেো (ক োলো)": "সরিষা (কালো)",
        "সয়োনর্ি": "সয়াবিন",
        "ক োলো": "কালো",
        "আমেোিীকৃি": "আমদানীকৃত",
        "োঁিো": "টমেটো",
        "পটল": "পটল",
        "আলু": "আলু",
        "বেগুন": "বেগুন"
    }
    for bad, good in replacements.items():
        name = name.replace(bad, good)
    return name.strip()

def parse_pdf(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(pdf_url, headers=headers, timeout=60)
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            # আমরা শুধু ২ নাম্বার পেজটা নিচ্ছি, কারণ এখানেই মূল টেবিলটা আছে
            page = pdf.pages[1] 
            text = page.extract_text()
            
        items = []
        if not text:
            return items

        lines = text.split("\n")
        for line in lines:
            # যে লাইনে দাম আছে (যেমন: ৬০.০০ - ৭০.০০) এমন লাইন খুঁজছি
            match = re.search(r"([\d০-৯\.]+)\s*-\s*([\d০-৯\.]+)", line)
            if match:
                min_val = match.group(1)
                max_val = match.group(2)
                
                # বাংলা সংখ্যাকে ইংরেজি করছি
                min_val_en = bn_to_en(min_val)
                max_val_en = bn_to_en(max_val)
                
                # পণ্যের নাম বের করার চেষ্টা (দামের আগের অংশটুকু)
                name_part = line[:match.start()].strip()
                # নাম পরিষ্কার করা
                clean = clean_name(name_part)
                
                # যদি নাম খুব ছোট হয় বা খালি থাকে, তবে বাদ দিচ্ছি
                if len(clean) > 2:
                    items.append({
                        "name": clean,
                        "lowest_price": min_val_en,
                        "highest_price": max_val_en,
                        "raw_line": line.strip()
                    })
        return items
    except Exception as e:
        print("PDF পার্স করতে সমস্যা:", e)
        return []

if __name__ == "__main__":
    print("শুরু হচ্ছে...")
    pdf_url = get_latest_pdf()
    
    if pdf_url:
        print("সর্বশেষ PDF পাওয়া গেছে:", pdf_url)
        items = parse_pdf(pdf_url)
        
        if items:
            final_data = {
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "source": pdf_url,
                "items": items
            }
            with open("prices.json", "w", encoding="utf-8") as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"সফল! {len(items)} টি পণ্যের দাম পাওয়া গেছে এবং prices.json এ সেভ হয়েছে।")
        else:
            print("PDF থেকে কোনো দাম বের করা যায়নি।")
    else:
        print("কোনো PDF লিংক পাওয়া যায়নি।")
