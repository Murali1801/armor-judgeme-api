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
# Allows your Shopify store domains to communicate with this backend
allowed_origins = [
    "https://armor.shop",
    "https://staging.armor.shop",
    "http://127.0.0.1:5500",
    "http://localhost:3000"
]

CORS(app, resources={r"/api/*": {
    "origins": allowed_origins, 
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# Credentials and IDs from .env
API_TOKEN = os.getenv('JUDGE_ME_API_TOKEN')
SHOP_DOMAIN = os.getenv('SHOP_DOMAIN')
# This is the External ID: 9972195066142
VERSION_H1_ID = os.getenv('PRODUCT_ID_VERSION_H1')

# Helper: Clean shop domain
if SHOP_DOMAIN:
    SHOP_DOMAIN = SHOP_DOMAIN.replace("https://", "").replace("http://", "").strip("/")

# --- CONFIGURATION: PRODUCT ID MAPPING ---
PRODUCT_ID_MAP = {
    "version-h1": VERSION_H1_ID 
}

# --- HELPER FUNCTIONS ---

def fetch_all_shop_reviews():
    """Fetches raw reviews from Judge.me API [cite: 63]"""
    url = "https://judge.me/api/v1/reviews"
    all_reviews = []
    page = 1
    per_page = 100 
    
    while True:
        params = {
            'api_token': API_TOKEN,
            'shop_domain': SHOP_DOMAIN,
            'per_page': per_page,
            'page': page
        }
        try:
            res = requests.get(url, params=params)
            if res.status_code != 200: break
            data = res.json()
            current_batch = data.get('reviews', [])
            if not current_batch: break 
            all_reviews.extend(current_batch)
            if len(current_batch) < per_page: break
            page += 1
            time.sleep(0.1)
        except:
            break
    return all_reviews

def calculate_stats(reviews):
    """Calculates ratings and fixes the 4.4 vs 4.39 rounding discrepancy [cite: 69, 70]"""
    count = len(reviews)
    if count == 0:
        return {"average": 0.0, "count": 0, "distribution": {5:0, 4:0, 3:0, 2:0, 1:0}}
    
    distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    total_sum = 0
    for r in reviews:
        rating = int(r.get('rating', 5))
        if 1 <= rating <= 5:
            distribution[rating] += 1
            total_sum += rating
            
    # ROUNDING FIX: Ensures consistency for frontend display 
    return {
        "average": round(total_sum / count, 2),
        "count": count,
        "distribution": distribution
    }

# --- API ROUTES ---

@app.route('/api/submit-review', methods=['POST'])
def submit_review_route():
    """Submits a product-specific review to Judge.me"""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    handle = data.get('handle', 'version-h1')
    external_id = PRODUCT_ID_MAP.get(handle)
    
    if not external_id:
        return jsonify({"error": f"Product ID missing for handle: {handle}"}), 404

    # Build Payload according to Judge.me API Doc schema
    judgeme_payload = {
        "shop_domain": SHOP_DOMAIN,
        "platform": "shopify",
        "id": int(external_id), 
        "name": data.get("name"),
        "email": data.get("email"),
        "rating": int(data.get("rating", 5)),
        "body": data.get("body"),
        "title": data.get("title", ""), 
        "reviewer_name_format": "", # Defaults to store setting (Full Name)
        "ip_addr": data.get("ip_addr", request.remote_addr)
    }

    endpoint = "https://judge.me/api/v1/reviews"
    try:
        response = requests.post(
            f"{endpoint}?api_token={API_TOKEN}",
            json=judgeme_payload
        )

        if response.status_code in [200, 201]:
            return jsonify({"status": "success", "message": "Review linked to product"}), 200
        else:
            return jsonify({"status": "error", "message": response.text}), response.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/product-reviews', methods=['GET'])
def get_reviews_route():
    """Fetches reviews and fixes the name display issue (e.g., 'I.Y' vs Full Name)"""
    target_handle = request.args.get('handle')
    if not target_handle:
        return jsonify({"error": "Missing handle"}), 400

    raw_reviews = fetch_all_shop_reviews()
    
    # Filter reviews by product handle and published status
    filtered_reviews = [r for r in raw_reviews if r.get('product_handle') == target_handle and r.get('published') is True]
    stats = calculate_stats(filtered_reviews)
    
    clean_reviews = []
    for r in filtered_reviews:
        media = []
        # Process Images
        if r.get('pictures'):
            for p in r['pictures']:
                url = p.get('urls', {}).get('original') if isinstance(p, dict) else None
                if url: media.append({"type": "image", "url": url})
        
        # FIX: Prioritize raw 'user_name' to prevent initials (e.g. 'I.Y') from showing 
        author_name = r.get('user_name') or r.get('reviewer', {}).get('name') or 'Verified Buyer'
        if author_name.strip().lower() == 'anonymous':
            author_name = "Verified Buyer"

        clean_reviews.append({
            "id": r.get('id'),
            "body": r.get('body'),
            "rating": int(r.get('rating', 5)),
            "author": author_name,
            "is_verified": r.get('verified') in ['buyer', 'verified_buyer', 'email'],
            "media": media,
            "date": r.get('created_at')
        })

    return jsonify({
        "stats": stats,
        "reviews": clean_reviews
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)