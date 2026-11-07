import requests
from bs4 import BeautifulSoup
import pdfplumber
import json
import re
import io
from datetime import datetime

PAGE_URL = "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21"
BN = "০১২৩৪৫৬৭৮৯"
EN = "0123456789"

def bn_to_en(text):
    return text.translate(str.maketrans(BN, EN))

def get_latest_pdf():
    r = requests.get(PAGE_URL, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    # সব PDF লিংক খুঁজি
    links = soup.select("table a[href$='.pdf']")
    if not links:
        raise Exception("কোনো PDF লিংক পাওয়া যায়নি")
    # প্রথম লিংকটাই সবচেয়ে নতুন (ঢাকা)
    return links[0]["href"]

def parse_pdf(url):
    r = requests.get(url, timeout=60)
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    items = []
    for line in text.split("\n"):
        m = re.search(r"([\d.]+)\s*-\s*([\d.]+)", line)
        if m and len(line) > 10:
            items.append({
                "raw": line.strip(),
                "min": float(m.group(1)),
                "max": float(m.group(2))
            })
    return items

if __name__ == "__main__":
    pdf_url = get_latest_pdf()
    print("PDF:", pdf_url)
    items = parse_pdf(pdf_url)
    data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "source": pdf_url,
        "items": items
    }
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"পাওয়া গেছে {len(items)} টি পণ্য")
