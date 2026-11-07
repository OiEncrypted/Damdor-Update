import requests
import json
from datetime import datetime, timedelta

# বেস হেডার
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://moa-services.com",
    "referer": "https://moa-services.com/market-directory/market-daily-price-report",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

BASE_URL = "https://moa-services.com/agri-service/crop-price-info/reports/price-report/market-daily-price-report"

def fetch_prices_for_market(session, date_str, division, district, market):
    """একটি নির্দিষ্ট বাজারের জন্য ডেটা আনে"""
    payload = {
        "division": division,
        "district": district,
        "market": market,
        "price_type": "retail", # আমরা রিটেইল বা খুচরা দর নিচ্ছি
        "date": date_str
    }
    
    try:
        response = session.post(BASE_URL, json=payload, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data"):
                return data["data"]
    except Exception:
        pass
    return None

def get_all_data():
    session = requests.Session()
    today = datetime.now()
    final_dataset = []
    
    # তোমার স্ক্রিনশট থেকে পাওয়া কিছু কমন বাজার (তুমি চাইলে আরও বাড়াতে পারো)
    # বাস্তবে সব বাজার অটোমেটিক পাওয়ার জন্য আমাদের আরেকটা API লাগবে, 
    # কিন্তু আপাতত এই লিস্ট দিয়েই কাজ চালানো যাবে।
    markets_to_check = [
        {"division": "ঢাকা", "district": "ঢাকা", "market": "কাওরান বাজার"},
        {"division": "ঢাকা", "district": "ঢাকা", "market": "মিরপুর ১ নং বাজার"},
        {"division": "ঢাকা", "district": "গাজীপুর", "market": "গাজীপুর বাজার"},
        {"division": "চট্টগ্রাম", "district": "চট্টগ্রাম", "market": "চকবাজার"},
        {"division": "খুলনা", "district": "খুলনা", "market": "খুলনা বাজার"}
        # এখানে আরও বাজার যোগ করা যাবে
    ]
    
    print("সব বাজারের ডেটা খোঁজা শুরু হচ্ছে...")
    
    # প্রতিটি বাজারের জন্য ৩ দিন পেছনে চেক করবে
    for m in markets_to_check:
        print(f"চেক করা হচ্ছে: {m['district']} - {m['market']}")
        
        market_data_found = None
        found_date = None
        
        # ৩ দিনের লুপ (আজ, গতকাল, পরশু)
        for days_ago in range(3):
            target_date = today - timedelta(days=days_ago)
            date_str = target_date.strftime("%Y-%m-%d")
            
            items = fetch_prices_for_market(session, date_str, m["division"], m["district"], m["market"])
            
            if items:
                market_data_found = items
                found_date = date_str
                break # ডেটা পেয়েই থেমে যাবে
                
        if market_data_found:
            # ডেটা ফরম্যাট করা (শুধু দরকারি জিনিসগুলো রাখা)
            formatted_items = []
            for item in market_data_found:
                # যদি খুচরা দর থাকে তবেই নিবে
                if item.get("r_lowestPrice") and item.get("r_highestPrice"):
                    formatted_items.append({
                        "commodity_id": item.get("commodity_id"),
                        "group_id": item.get("com_grp_id"),
                        "unit": item.get("unit_retail"),
                        "retail_min": item.get("r_lowestPrice"),
                        "retail_max": item.get("r_highestPrice"),
                        "wholesale_min": item.get("w_lowestPrice"),
                        "wholesale_max": item.get("w_highestPrice")
                    })
            
            if formatted_items:
                final_dataset.append({
                    "location": {
                        "division": m["division"],
                        "district": m["district"],
                        "market": m["market"]
                    },
                    "date": found_date,
                    "items": formatted_items
                })
                print(f"-> সফল! {len(formatted_items)} টি পণ্যের ডেটা পাওয়া গেছে ({found_date})")
        else:
            print(f"-> ডেটা পাওয়া যায়নি শেষ ৩ দিনেও।")

    return final_dataset

if __name__ == "__main__":
    all_data = get_all_data()
    
    final_json = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "data": all_data
    }
    
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
        
    print("সব ডেটা prices.json ফাইলে সেভ করা হয়েছে!")
