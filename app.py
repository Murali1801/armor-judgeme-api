import os
import requests
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

app = Flask(__name__)

# --- CORS CONFIGURATION ---
# Removed localhost/127.0.0.1. Only specific domains allowed.
allowed_origins = [
    "https://armor.shop",
    "https://staging.armor.shop"
]

CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

# Credentials
API_TOKEN = os.getenv('JUDGE_ME_API_TOKEN')
SHOP_DOMAIN = os.getenv('SHOP_DOMAIN')

if SHOP_DOMAIN:
    SHOP_DOMAIN = SHOP_DOMAIN.replace("https://", "").replace("http://", "").strip("/")

# --- HELPER FUNCTIONS ---

def fetch_all_shop_reviews():
    """
    Fetches ALL reviews from the shop to ensure we can filter by handle client-side
    (since the API handle filter can be inconsistent or limited).
    """
    url = "https://judge.me/api/v1/reviews"
    all_reviews = []
    page = 1
    per_page = 100 
    
    print(f"--- Starting Fetch for {SHOP_DOMAIN} ---")

    while True:
        params = {
            'api_token': API_TOKEN,
            'shop_domain': SHOP_DOMAIN,
            'per_page': per_page,
            'page': page
        }
        
        try:
            res = requests.get(url, params=params)
            
            if res.status_code != 200:
                print(f"Error on Page {page}: {res.status_code}")
                break
            
            data = res.json()
            current_batch = data.get('reviews', [])
            
            if not current_batch:
                break 
            
            all_reviews.extend(current_batch)
            
            if len(current_batch) < per_page:
                break
                
            page += 1
            time.sleep(0.1) 
            
        except Exception as e:
            print(f"Exception fetching reviews: {e}")
            break
            
    print(f"--- Fetch Complete. Total raw reviews: {len(all_reviews)} ---")
    return all_reviews

def calculate_stats(reviews):
    """
    Calculates stats (average, count, distribution) only for the filtered list.
    """
    count = len(reviews)
    if count == 0:
        return {
            "average": 0.0,
            "count": 0,
            "distribution": {5:0, 4:0, 3:0, 2:0, 1:0}
        }
    
    distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    total_sum = 0
    
    for r in reviews:
        rating = r.get('rating', 5)
        try:
            rating = int(rating)
        except:
            rating = 5
            
        if rating < 1: rating = 1
        if rating > 5: rating = 5
            
        distribution[rating] += 1
        total_sum += rating

    average = total_sum / count
    
    return {
        "average": round(average, 2),
        "count": count,
        "distribution": distribution
    }

# --- API ROUTE ---

@app.route('/api/product-reviews', methods=['GET'])
def get_reviews_route():
    # 1. Get handle
    target_handle = request.args.get('handle')
    if not target_handle:
        return jsonify({"error": "Missing 'handle' parameter"}), 400

    # 2. Fetch All Raw Data
    raw_reviews = fetch_all_shop_reviews()
    
    # 3. Filter Logic
    filtered_reviews = []
    
    for r in raw_reviews:
        # A. Filter by Product Handle
        if r.get('product_handle') != target_handle:
            continue
            
        # B. Filter by Published Status
        # Only allow if published is explictly True
        if r.get('published') is not True:
            continue
            
        filtered_reviews.append(r)

    # 4. Calculate Stats (on filtered data only)
    stats = calculate_stats(filtered_reviews)
    
    # 5. Format Data for Display
    clean_reviews = []
    for r in filtered_reviews:
        # Extract Media
        media = []
        if r.get('pictures'):
            for p in r['pictures']:
                urls = p.get('urls', {})
                img_url = urls.get('original') or urls.get('huge')
                if img_url: 
                    media.append({"type": "image", "url": img_url})

        # Extract Reviewer Name
        reviewer_data = r.get('reviewer', {})
        author_name = reviewer_data.get('name', 'Anonymous')
        initials = author_name[0].upper() if author_name else "A"
        
        # Determine Verification Status
        # Based on your JSON, verified can be 'nothing', 'email', 'confirmed-buyer' etc.
        raw_verified = r.get('verified', 'nothing')
        is_verified = raw_verified in ['buyer', 'verified_buyer', 'confirmed-buyer', 'verified-purchase', 'email']

        clean_reviews.append({
            "id": r.get('id'),
            "title": r.get('title'),
            "body": r.get('body'),
            "rating": int(r.get('rating', 5)),
            "author": author_name,
            "initials": initials,
            "is_verified": is_verified,
            "date": r.get('created_at'),
            "media": media,
            # We keep the raw string in case you need to debug or show specific badges later
            "verification_type": raw_verified
        })

    return jsonify({
        "stats": stats,
        "reviews": clean_reviews
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)