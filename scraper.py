import requests
import json
from datetime import datetime, timedelta

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://moa-services.com",
    "referer": "https://moa-services.com/market-directory/market-daily-price-report",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

BASE_URL = "https://moa-services.com/agri-service/crop-price-info/reports/price-report/market-daily-price-report"

# একটি নির্দিষ্ট বাজারের ডেটা আনা
def fetch_prices(session, date_str, division, district, market):
    payload = {
        "division": division, "district": district, "market": market,
        "price_type": "retail", "date": date_str
    }
    try:
        res = session.post(BASE_URL, json=payload, headers=HEADERS, timeout=20)
        if res.status_code == 200 and res.json().get("success"):
            return res.json().get("data", [])
    except: pass
    return []

# নাম আনার চেষ্টা (অটোমেটিক অনুমান)
def fetch_names(session):
    name_map = {}
    # এই লিংকগুলো সাধারণত সাইটে লুকানো থাকে, আমরা চেষ্টা করে দেখছি
    possible_urls = [
        "https://moa-services.com/agri-service/crop-price-info/master/commodities",
        "https://moa-services.com/agri-service/crop-price-info/master/commodity-list",
        "https://moa-services.com/agri-service/master/commodities"
    ]
    for url in possible_urls:
        try:
            res = session.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("success") and data.get("data"):
                    # যদি লিস্ট আকারে থাকে
                    if isinstance(data["data"], list):
                        for item in data["data"]:
                            if "id" in item and "name" in item:
                                name_map[str(item["id"])] = item["name"]
                    # যদি ডিকশনারিতে থাকে
                    elif isinstance(data["data"], dict):
                        for key, val in data["data"].items():
                            if isinstance(val, list):
                                for item in val:
                                    if "id" in item and "name" in item:
                                        name_map[str(item["id"])] = item["name"]
                    if name_map: return name_map
        except: pass
    return name_map

def get_all_data():
    session = requests.Session()
    today = datetime.now()
    
    print("নামের লিস্ট খোঁজা হচ্ছে...")
    names = fetch_names(session)
    if names: print(f"সফল! {len(names)} টি নাম পাওয়া গেছে।")
    else: print("নামের লিস্ট পাওয়া যায়নি, শুধু আইডি দেখানো হবে।")

    # বাজার লিস্ট (তুমি চাইলে আরও বাড়াতে পারো)
    markets = [
        {"division": "ঢাকা", "district": "ঢাকা", "market": "কাওরান বাজার"},
        {"division": "ঢাকা", "district": "ঢাকা", "market": "মিরপুর ১ নং বাজার"},
        {"division": "ঢাকা", "district": "গাজীপুর", "market": "গাজীপুর বাজার"},
        {"division": "চট্টগ্রাম", "district": "চট্টগ্রাম", "market": "চকবাজার"},
    ]
    
    final_output = []
    
    for m in markets:
        print(f"চেক করা হচ্ছে: {m['market']}")
        market_data = None
        found_date = None
        
        # ৩ দিনের লজিক (আজ, গতকাল, পরশু)
        for days in range(3):
            d_str = (today - timedelta(days=days)).strftime("%Y-%m-%d")
            items = fetch_prices(session, d_str, m["division"], m["district"], m["market"])
            if items:
                market_data = items
                found_date = d_str
                break
        
        if market_data:
            clean_items = []
            for item in market_data:
                # নাম বের করা (না পেলে আইডি)
                c_id = str(item.get("commodity_id"))
                c_name = names.get(c_id, f"পণ্য আইডি: {c_id}")
                
                # শুধু দাম থাকলে যোগ করা
                if item.get("r_lowestPrice") and item.get("r_highestPrice"):
                    clean_items.append({
                        "group_id": item.get("com_grp_id"),
                        "name": c_name,
                        "retail_min": item.get("r_lowestPrice"),
                        "retail_max": item.get("r_highestPrice"),
                        "wholesale_min": item.get("w_lowestPrice"),
                        "wholesale_max": item.get("w_highestPrice")
                    })
            
            if clean_items:
                final_output.append({
                    "location": m,
                    "date": found_date,
                    "items": clean_items
                })
                print(f" -> সফল! {len(clean_items)} টি পণ্য পাওয়া গেছে ({found_date})।")
        else:
            print(f" -> ডেটা পাওয়া যায়নি।")

    return final_output

if __name__ == "__main__":
    data = get_all_data()
    final_json = {"updated_at": datetime.utcnow().isoformat() + "Z", "data": data}
    
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    print("সব ডেটা prices.json এ সেভ হয়েছে।")
