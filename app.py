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
# Updated to explicitly allow POST methods for the new review submission
allowed_origins = [
    "https://armor.shop",
    "https://staging.armor.shop",
    "http://127.0.0.1:5500",
    "http://localhost:3000"
]

CORS(app, resources={r"/api/*": {"origins": allowed_origins, "methods": ["GET", "POST", "OPTIONS"]}})

# Credentials
API_TOKEN = os.getenv('JUDGE_ME_API_TOKEN') # Use your Private API Token here
SHOP_DOMAIN = os.getenv('SHOP_DOMAIN')

# Helper: Clean shop domain
if SHOP_DOMAIN:
    SHOP_DOMAIN = SHOP_DOMAIN.replace("https://", "").replace("http://", "").strip("/")

# --- MAPPING HANDLE TO PRODUCT ID ---
# Judge.me requires the Shopify Product ID (numerical) to post a review.
# You can update this dictionary as you add more products.
PRODUCT_ID_MAP = {
    "version-h1": "1234567890" # REPLACE with your actual Shopify Product ID
}

# --- EXISTING HELPER FUNCTIONS ---

def fetch_all_shop_reviews():
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
    count = len(reviews)
    if count == 0:
        return {"average": 0.0, "count": 0, "distribution": {5:0, 4:0, 3:0, 2:0, 1:0}}
    distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    total_sum = 0
    for r in reviews:
        rating = int(r.get('rating', 5))
        if rating < 1: rating = 1
        if rating > 5: rating = 5
        distribution[rating] += 1
        total_sum += rating
    return {"average": round(total_sum / count, 2), "count": count, "distribution": distribution}

# --- API ROUTES ---

# 1. NEW: Submit Review Route (POST)
@app.route('/api/submit-review', methods=['POST'])
def submit_review_route():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Extract info from frontend
    handle = data.get('handle', 'version-h1')
    reviewer_name = data.get('name')
    reviewer_email = data.get('email')
    rating = data.get('rating')
    body = data.get('body')

    # Get the numerical Product ID
    product_id = PRODUCT_ID_MAP.get(handle)
    if not product_id:
        return jsonify({"error": f"Product ID not found for handle: {handle}"}), 404

    # Judge.me Reviewer API Payload
    # Note: We use the Private API Token for authentication
    judgeme_payload = {
        "shop_domain": SHOP_DOMAIN,
        "platform": "shopify",
        "id": product_id,
        "email": reviewer_email,
        "name": reviewer_name,
        "rating": rating,
        "body": body
    }

    try:
        response = requests.post(
            f"https://judge.me/api/v1/reviews?api_token={API_TOKEN}",
            json=judgeme_payload
        )

        if response.status_code in [200, 201]:
            return jsonify({"status": "success", "message": "Review submitted successfully"}), 200
        else:
            return jsonify({"status": "error", "message": response.text}), response.status_code

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 2. EXISTING: Get Reviews Route (GET)
@app.route('/api/product-reviews', methods=['GET'])
def get_reviews_route():
    target_handle = request.args.get('handle')
    if not target_handle:
        return jsonify({"error": "Missing 'handle' parameter"}), 400

    raw_reviews = fetch_all_shop_reviews()
    filtered_reviews = [r for r in raw_reviews if r.get('product_handle') == target_handle and r.get('published') is True]
    stats = calculate_stats(filtered_reviews)
    
    clean_reviews = []
    for r in filtered_reviews:
        media = []
        if r.get('pictures'):
            for p in r['pictures']:
                url = p.get('urls', {}).get('original') if isinstance(p, dict) else None
                if url: media.append({"type": "image", "url": url})
        
        if r.get('videos'):
            for v in r['videos']:
                v_url = v.get('url') or v.get('original_url')
                if v_url: media.append({"type": "video", "url": v_url})

        author_name = r.get('reviewer', {}).get('name', 'Verified Buyer')
        clean_reviews.append({
            "id": r.get('id'),
            "body": r.get('body'),
            "rating": int(r.get('rating', 5)),
            "author": author_name,
            "is_verified": r.get('verified') in ['buyer', 'verified_buyer', 'email'],
            "media": media
        })

    return jsonify({"stats": stats, "reviews": clean_reviews})

if __name__ == '__main__':
    app.run(debug=True, port=5000)