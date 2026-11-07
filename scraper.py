import requests
from bs4 import BeautifulSoup
import pdfplumber
import json
import re
import io
from datetime import datetime

# পেজের লিংক
PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"

# বাংলা সংখ্যা
BN_DIGITS = "০১২৩৪৫৬৭৮৯"
EN_DIGITS = "0123456789"

def bn_to_en(text):
    return text.translate(str.maketrans(BN_DIGITS, EN_DIGITS))

def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")
        # পেজের সব PDF লিংক খোঁজা (প্রথম ৮টা লিংক নিব, কারণ ৮টা বিভাগ)
        links = soup.select("table a[href$='.pdf']")
        # শুধু প্রথম ৮টা লিংক (কারণ বাকিগুলো পুরোনো তারিখের)
        return [link["href"] for link in links[:8]]
    except Exception as e:
        print("লিংক খুঁজতে সমস্যা:", e)
        return []

def clean_name(name):
    # PDF-এর এলোমেলো লেখা ঠিক করার অভিধান
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
        "বেগুন": "বেগুন",
        "কুিড়": "কুমড়া",
        "মরিচ": "মরিচ",
        "পেঁয়াজ": "পেঁয়াজ",
        "রসুন": "রসুন",
        "আদা": "আদা"
    }
    for bad, good in replacements.items():
        name = name.replace(bad, good)
    return name.strip()

def parse_pdf(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(pdf_url, headers=headers, timeout=60)
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            # আমরা ২ নাম্বার পেজটা নিচ্ছি (যেখানে মূল টেবিল)
            if len(pdf.pages) < 2:
                return []
            page = pdf.pages[1]
            text = page.extract_text()
            
        if not text:
            return []

        items = []
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
                        "highest_price": max_val_en
                    })
        return items
    except Exception as e:
        print(f"PDF পার্সে সমস্যা ({pdf_url}):", e)
        return []

if __name__ == "__main__":
    print("লিংক খোঁজা হচ্ছে...")
    pdf_links = get_pdf_links()
    
    if not pdf_links:
        print("কোনো PDF লিংক পাওয়া যায়নি।")
        exit()

    print(f"{len(pdf_links)} টি PDF লিংক পাওয়া গেছে। প্রথমটা পার্স করা হচ্ছে...")
    
    # আপাতত আমরা শুধু প্রথম PDF (ঢাকা) পার্স করছি, যাতে কোড ঠিকমতো কাজ করে কিনা দেখা যায়
    # তুমি চাইলে লুপ চালিয়ে সবগুলোর ডেটা নিতে পারো
    first_pdf_url = pdf_links[0]
    print("ডাউনলোড হচ্ছে:", first_pdf_url)
    
    items = parse_pdf(first_pdf_url)
    
    if items:
        final_data = {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "source": first_pdf_url,
            "items": items
        }
        with open("prices.json", "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        print(f"সফল! {len(items)} টি পণ্যের দাম পাওয়া গেছে এবং prices.json এ সেভ হয়েছে।")
    else:
        print("PDF থেকে কোনো ডেটা বের করা যায়নি।")
