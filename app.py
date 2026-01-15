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
# Allow your specific domains. 
# You can add 'http://localhost:3000' or similar for local testing if needed.
allowed_origins = [
    "https://armor.shop",
    "https://staging.armor.shop",
    "http://127.0.0.1:5500", # Example for local testing
    "http://localhost:3000"
]

CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

# Credentials
API_TOKEN = os.getenv('JUDGE_ME_API_TOKEN')
SHOP_DOMAIN = os.getenv('SHOP_DOMAIN')

# Helper: Clean shop domain
if SHOP_DOMAIN:
    SHOP_DOMAIN = SHOP_DOMAIN.replace("https://", "").replace("http://", "").strip("/")

# --- HELPER FUNCTIONS ---

def fetch_all_shop_reviews():
    """
    Fetches EVERY review from the shop to handle client-side filtering.
    Loops through all pages until no more reviews are returned.
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
                print(f"Error on Page {page}: {res.status_code} | {res.text}")
                break
            
            data = res.json()
            current_batch = data.get('reviews', [])
            
            if not current_batch:
                break 
            
            all_reviews.extend(current_batch)
            
            # Optimization: If fewer reviews than limit, we are on the last page
            if len(current_batch) < per_page:
                break
                
            page += 1
            time.sleep(0.1) # Be nice to the API
            
        except Exception as e:
            print(f"Exception fetching reviews: {e}")
            break
            
    print(f"--- Fetch Complete. Total raw reviews: {len(all_reviews)} ---")
    return all_reviews

def calculate_stats(reviews):
    """
    Calculates stats (average, count, distribution) for the filtered list.
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
    # 1. Get handle from request
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
        if r.get('published') is not True:
            continue
            
        filtered_reviews.append(r)

    # 4. Calculate Stats (on filtered data only)
    stats = calculate_stats(filtered_reviews)
    
    # 5. Format Data for Frontend
    clean_reviews = []
    for r in filtered_reviews:
        media = []
        
        # --- A. Process Images ---
        if r.get('pictures'):
            for p in r['pictures']:
                url = None
                # Check for nested 'urls' dict (standard Judge.me API)
                if isinstance(p, dict) and 'urls' in p:
                    url = p['urls'].get('original') or p['urls'].get('huge')
                # Fallback for simple structure
                elif isinstance(p, dict) and 'url' in p:
                    url = p['url']
                
                if url: 
                    media.append({"type": "image", "url": url})

        # --- B. Process Videos (NEW) ---
        # Note: Judge.me usually puts videos in a separate 'videos' array
        if r.get('videos'):
            for v in r['videos']:
                # Prefer 'url' or 'original_url'
                video_url = v.get('url') or v.get('original_url')
                if video_url:
                    media.append({"type": "video", "url": video_url})

        # --- C. Clean Author Name ---
        reviewer_data = r.get('reviewer', {})
        author_name = reviewer_data.get('name', 'Anonymous')
        
        # Logic to replace "Anonymous" with a better label if desired
        if author_name.strip().lower() == 'anonymous':
            author_name = "Verified Buyer"

        initials = author_name[0].upper() if author_name else "A"
        
        # --- D. Verification Status ---
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
            "verification_type": raw_verified
        })

    return jsonify({
        "stats": stats,
        "reviews": clean_reviews
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)