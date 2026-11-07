import requests
import json
from datetime import datetime, timedelta

def get_prices_for_date(session, date_str, headers):
    price_url = "https://moa-services.com/agri-service/crop-price-info/reports/price-report/market-daily-price-report"
    
    payload = {
        "division": "ঢাকা",
        "district": "ঢাকা",
        "market": "কাওরান বাজার",
        "price_type": "retail",
        "date": date_str
    }
    
    try:
        response = session.post(price_url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "data" in data:
                raw_items = data["data"]
                # যদি ডেটা লিস্ট খালি না হয়, তবে ডেটা আছে
                if len(raw_items) > 0:
                    return raw_items
    except Exception as e:
        print(f"{date_str} তারিখে চেক করতে গিয়ে এরর: {e}")
    
    return None

def get_latest_available_prices():
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://moa-services.com",
        "referer": "https://moa-services.com/market-directory/market-daily-price-report",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    session = requests.Session()
    today = datetime.now()
    
    latest_items = None
    latest_date_str = None
    
    # আমরা সর্বোচ্চ ১৫ দিন পেছনে যাব। কিন্তু যেই দিনই ডেটা পাব, সেখানেই থেমে যাব।
    for days_ago in range(15):
        target_date = today - timedelta(days=days_ago)
        date_str = target_date.strftime("%Y-%m-%d")
        
        print(f"চেক করা হচ্ছে: {date_str} তারিখের ডেটা...")
        items = get_prices_for_date(session, date_str, headers)
        
        if items:
            print(f"সফল! {date_str} তারিখের ডেটা পাওয়া গেছে।")
            latest_items = items
            latest_date_str = date_str
            break # ডেটা পেয়েই লুপ থেকে বের হয়ে যাচ্ছি, কারণ এটাই সবচেয়ে নতুন ডেটা
            
    return latest_items, latest_date_str

if __name__ == "__main__":
    print("ডেটা খোঁজা শুরু হচ্ছে...")
    items, found_date = get_latest_available_prices()
    
    if items:
        final_items = []
        for item in items:
            # যদি দাম ঠিক থাকে তবে লিস্টে যোগ করি
            if item.get("r_lowestPrice") is not None and item.get("r_highestPrice") is not None:
                final_items.append({
                    "commodity_id": item.get("commodity_id"),
                    "lowest_price": item.get("r_lowestPrice"),
                    "highest_price": item.get("r_highestPrice")
                })
                
        final_data = {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "date": found_date,
            "items": final_items
        }
        with open("prices.json", "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        print(f"সফল! {len(final_items)} টি পণ্যের ডেটা সেভ করা হয়েছে ({found_date})।")
    else:
        print("দুঃখিত, শেষ ১৫ দিনের কোনো ডেটাই পাওয়া যায়নি।")
