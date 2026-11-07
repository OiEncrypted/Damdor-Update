import requests
import json
from datetime import datetime

# পণ্যের নাম ঠিক করার জন্য অভিধান (তোমার PDF থেকে নেওয়া)
# এখানে শুধু কিছু উদাহরণ দিলাম, তুমি চাইলে আরও বাড়াতে পারো
NAME_MAP = {
    585: "আটা (প্যাকেট)",
    586: "আটা (খোলা)",
    587: "আটার ময়দা",
    588: "চিনি",
    589: "চিনি (লাল)",
    590: "মসুর ডাল",
    591: "মসুর ডাল (মোটা)",
    592: "মুগ ডাল",
    593: "মুগ ডাল (ফাটা)",
    594: "ছোলা",
    595: "ছোলা (খোলা)",
    596: "কেসার ডাল",
    597: "সয়াবিন তেল",
    598: "পাম তেল",
    599: "সরিষার তেল",
    601: "পেঁয়াজ",
    602: "রসুন",
    603: "আদা",
    604: "শুকনা মরিচ",
    605: "হলুদ",
    606: "ধনিয়া",
    607: "জিরা",
    608: "আলু",
    609: "বেগুন",
    610: "টমেটো",
    611: "পটল",
    612: "ঢেঁড়স",
    613: "কুমড়া",
    614: "চালকুমড়া",
    615: "মুলা",
    616: "গাজর",
    617: "শসা",
    618: "বাঁধাকপি",
    619: "ফুলকপি",
    620: "লাউ",
    621: "কচু",
    622: "পুঁইশাক",
    623: "লালশাক",
    624: "পালংশাক",
    625: "মাছ (রুই)",
    626: "মাছ (কাতলা)",
    627: "মাছ (ইলিশ)",
    628: "মাছ (পাঙাশ)",
    629: "মাছ (তেলাপিয়া)",
    630: "মুরগি (ব্রয়লার)",
    631: "মুরগি (দেশি)",
    632: "ডিম (মুরগি)",
    633: "ডিম (হাঁস)",
    634: "গরুর মাংস",
    635: "খাসির মাংস",
    636: "দুধ (গুড়া)",
    637: "দুধ (তরল)"
}

# বেস হেডার
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://moa-services.com",
    "referer": "https://moa-services.com/market-directory/market-daily-price-report",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

BASE_URL = "https://moa-services.com/agri-service/crop-price-info/reports/price-report/market-daily-price-report"

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

def get_all_data():
    session = requests.Session()
    today = datetime.now()
    
    # বাজার লিস্ট (তুমি চাইলে আরও বাড়াতে পারো)
    markets = [
        {"division": "ঢাকা", "district": "ঢাকা", "market": "কাওরান বাজার"},
        {"division": "ঢাকা", "district": "ঢাকা", "market": "মিরপুর ১ নং বাজার"},
        {"division": "চট্টগ্রাম", "district": "চট্টগ্রাম", "market": "চকবাজার"},
    ]
    
    final_output = []
    
    for m in markets:
        print(f"চেক করা হচ্ছে: {m['market']}")
        market_data = None
        found_date = None
        
        # ৩ দিনের লজিক
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
                c_id = int(item.get("commodity_id", 0))
                
                # অভিধান থেকে নাম খোঁজা, না পেলে আইডি দেখানো
                c_name = NAME_MAP.get(c_id, f"অন্যান্য পণ্য ({c_id})")
                
                # শুধু দাম থাকলে যোগ করা
                if item.get("r_lowestPrice") and item.get("r_highestPrice"):
                    clean_items.append({
                        "id": c_id,
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
