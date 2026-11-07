import requests
from bs4 import BeautifulSoup
import pdfplumber
import json
import re
import io
from datetime import datetime

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"

# ভাঙা বাংলা লেখা ঠিক করার অভিধান
NAME_MAP = {
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
    "আদা": "আদা",
    "আটো": "আটা",
    "মসুর (কমোটো)": "মসুর (মোটা)",
    "মুগ (সরু- উন্নি)": "মুগ (সরু-উন্নত)",
    "মসুর (উন্নি)": "মসুর (উন্নত)",
    "ক সোরী": "কেসারি",
    "বুট": "বুট",
    "মোশ েলোই": "মাষকলাই",
    "রসুি (িোয়িো)": "মসুর (দেশি)",
    "পোম (ক োলো)": "পাম (কালো)",
    "চিচিিংগা": "চিচিঙ্গা",
    "মসলো": "মসলা",
    "কেঁয়োি (কেশী)": "পেঁয়াজ (দেশি)",
    "শুেিো মনরি (কেশী)": "শুকনা মরিচ (দেশি)",
    "রসুি (কেশী)": "রসুন (দেশি)",
    "আমেোিীকৃি (সোেো-ক োলো)": "আমদানীকৃত (সাদা-কালো)",
    "মুরনগ (কসোিোলী)": "মুরগি (সোনালি)",
    "ফোমবসোেো/লোল": "ফার্মের ডিম/লাল",
    "দুধ গুুঁরড়ো (পনলপ্যোে)": "দুধ গুঁড়া (পলিপ্যাক)",
    "েলো (সোগর)": "ডিম (হাঁস)",
    "গুটি স্বিোব(কমোটো)": "গুটি সয়াবিন (মোটা)",
    "পোিোম, নি ধোি ২৮, নি ধোি-২৯(মোঝোনর)": "পাটনা, নী ধান ২৮, নী ধান-২৯ (মাঝারি)",
    "নিরোশোইল-শম্পো েোটোনর(সরু)": "বিরশাইল-শম্পা জাতের (সরু)",
    "নর্ররোই (সরু)": "ব্রি-ধান (সরু)",
    "নি ধোি-৩৪ (সুগন্ধী)": "নী ধান-৩৪ (সুগন্ধী)",
    "গরু": "গরু",
    " োগল": "ছাগল",
    "িোল": "মাছ",
    "কমোরগ/মুরনগ": "মুরগি",
    "িয়লোর": "ব্রয়লার",
    "কসোিোলী (েোলোরর্োড/বহোইনিড)": "সোনালি (কালারবার্ড/হাইলাইন)"
}

def get_pdf_links():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(PAGE_URL, headers=headers, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")
        
        pdf_links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.endswith('.pdf'):
                pdf_links.append(href)
                
        return list(dict.fromkeys(pdf_links))[:8] 
    except Exception as e:
        print("লিংক খুঁজতে সমস্যা:", e)
        return []

def clean_name(name):
    for bad, good in NAME_MAP.items():
        name = name.replace(bad, good)
    # নামের শেষে থাকা অপ্রয়োজনীয় স্পেস বা চিহ্ন বাদ দেওয়া
    name = re.sub(r'^[\s\-–]+|[\s\-–]+$', '', name)
    return name.strip()

def parse_pdf(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(pdf_url, headers=headers, timeout=60)
        with pdfplumber.open(io.BytesIO(res.content)) as pdf:
            # মূল টেবিল সাধারণত ২ নাম্বার পেজে থাকে
            if len(pdf.pages) < 2: return []
            text = pdf.pages[1].extract_text()
            
        if not text: return []

        items = []
        lines = text.split("\n")
        for line in lines:
            # দাম খোঁজা (যেমন: 60.00 - 70.00)
            match = re.search(r"([\d.]+)\s*-\s*([\d.]+)", line)
            if match:
                min_price = match.group(1)
                max_price = match.group(2)
                
                # দামের আগের অংশটুকু নাম হিসেবে নেওয়া
                name_part = line[:match.start()].strip()
                clean = clean_name(name_part)
                
                # নাম খুব ছোট হলে (যেমন শুধু "৩" বা "-") বাদ দেয়া
                if len(clean) > 2 and not clean.isdigit():
                    items.append({
                        "name": clean,
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

    print(f"{len(links)} টি লিংক পাওয়া গেছে। প্রথম লিংক (ঢাকা) পার্স করা হচ্ছে...")
    
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
