import requests
import json
from datetime import datetime

def get_prices():
    url = "https://moa-services.com/agri-service/crop-price-info/reports/price-report/market-daily-price-report"
    
    # তোমার দেওয়া হেডারগুলো (যাতে সাইট বুঝতে পারে এটা সত্যিকারের ইউজার)
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://moa-services.com",
        "referer": "https://moa-services.com/market-directory/market-daily-price-report",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "accessmenuname": "https://moa-services.com/market-directory/market-daily-price-report",
        "accessuserid": "0",
        "accessusername": ""
    }

    # ফর্মের ডেটা (Payload)। 
    # যেহেতু আমরা আইডি জানি না, আমরা নাম দিয়েই পাঠাচ্ছি (যদি সাইট সাপোর্ট করে)
    # অথবা তোমার স্ক্রিনশটের উপর ভিত্তি করে ডিফল্ট ডেটা
    payload = {
        "division": "ঢাকা",       # অথবা division_id: "6aef5622fe5fe1c548e69ea5" (তোমার আগের স্ক্রিনশটে ছিল)
        "district": "ঢাকা",
        "market": "কাওরান বাজার",
        "price_type": "retail",   # খুচরা
        "date": "2026-11-07"
    }

    print("ডেটা খোঁজা হচ্ছে...")
    # এখানে POST মেথড ব্যবহার করা হচ্ছে
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    
    print("স্ট্যাটাস কোড:", response.status_code)
    
    if response.status_code == 200:
        data = response.json()
        # তোমার দেখানো ডেটা স্ট্রাকচার অনুযায়ী
        if data.get("success"):
            items = data.get("data", [])
            print(f"সফল! {len(items)} টি ডেটা পাওয়া গেছে।")
            return items
        else:
            print("API বলছে ডেটা পাওয়া যায়নি (success = false)।")
    else:
        print("রিকোয়েস্ট ফেইল করেছে।")
        print(response.text) # কী ভুল হচ্ছে দেখার জন্য
        
    return []

if __name__ == "__main__":
    items = get_prices()
    
    # ডেটা সেভ করা
    final_data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "items": items
    }
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
