import requests
import json
from datetime import datetime

def get_prices():
    # দামের API (যেটা তুমি খুঁজে পেয়েছিলে)
    price_url = "https://moa-services.com/agri-service/crop-price-info/reports/price-report/market-daily-price-report"
    
    # পণ্যের নামের API (আমাদের অনুমান - সাধারণত এই ধরনের সাইটে এভাবেই থাকে)
    # যদি নাম না আসে, আমরা সাময়িকভাবে ID দেখাব
    commodity_url = "https://moa-services.com/agri-service/crop-price-info/master/commodities"
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://moa-services.com",
        "referer": "https://moa-services.com/market-directory/market-daily-price-report",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    session = requests.Session()
    
    # ১. পণ্যের নামের লিস্ট আনা (যদি পাওয়া যায়)
    commodity_map = {}
    try:
        res_names = session.get(commodity_url, headers=headers, timeout=10)
        if res_names.status_code == 200:
            names_data = res_names.json()
            if names_data.get("success") and "data" in names_data:
                # ডেটা লিস্ট আকারে থাকলে সেটাকে ম্যাপ করি
                if isinstance(names_data["data"], list):
                    for item in names_data["data"]:
                        commodity_map[item.get("id")] = item.get("name")
                elif isinstance(names_data["data"], dict) and "commodities" in names_data["data"]:
                    for item in names_data["data"]["commodities"]:
                        commodity_map[item.get("id")] = item.get("name")
    except Exception as e:
        print("নামের লিস্ট আনতে সমস্যা হয়েছে, শুধু আইডি দেখানো হবে:", e)

    # ২. দামের ডেটা আনা
    payload = {
        "division": "ঢাকা",
        "district": "ঢাকা",
        "market": "কাওরান বাজার",
        "price_type": "retail",
        "date": "2026-11-07" # এখানে আজকের তারিখ দিতে হবে
    }

    response = session.post(price_url, json=payload, headers=headers, timeout=30)
    
    final_items = []
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success") and "data" in data:
            raw_items = data["data"]
            for item in raw_items:
                # যদি দাম না থাকে, স্কিপ করি
                if item.get("r_lowestPrice") is None or item.get("r_highestPrice") is None:
                    continue
                    
                com_id = item.get("commodity_id")
                # নাম বের করা, না পেলে "পণ্য (ID: xxx)" দেখানো
                com_name = commodity_map.get(com_id, f"পণ্য (ID: {com_id})")
                
                final_items.append({
                    "name": com_name,
                    "lowest_price": item.get("r_lowestPrice"),
                    "highest_price": item.get("r_highestPrice")
                })
    
    return final_items

if __name__ == "__main__":
    print("ডেটা সংগ্রহ করা হচ্ছে...")
    items = get_prices()
    
    # ডেটা সেভ করা
    final_data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "items": items
    }
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
        
    print(f"সফল! {len(items)} টি পণ্যের দাম পাওয়া গেছে।")
