import os
import requests
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

app = Flask(__name__)
# Enable CORS to allow your frontend to communicate with this backend
CORS(app)

# Credentials from .env file
API_TOKEN = os.getenv('JUDGE_ME_API_TOKEN')
SHOP_DOMAIN = os.getenv('SHOP_DOMAIN')

# Helper: Clean shop domain string
if SHOP_DOMAIN:
    SHOP_DOMAIN = SHOP_DOMAIN.replace("https://", "").replace("http://", "").strip("/")

# --- HELPER FUNCTIONS ---

def fetch_all_shop_reviews():
    """
    Fetches EVERY review from the shop by looping through pages.
    We fetch everything first because the API's handle filtering can be inconsistent.
    """
    url = "https://judge.me/api/v1/reviews"
    all_reviews = []
    page = 1
    per_page = 100 # Maximum allowed per page
    
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
            
            # Check for API errors
            if res.status_code != 200:
                print(f"Error on Page {page}: Status {res.status_code} | {res.text}")
                break
            
            data = res.json()
            current_batch = data.get('reviews', [])
            
            if not current_batch:
                break # No more reviews
            
            all_reviews.extend(current_batch)
            
            # Optimization: If we received fewer reviews than requested, it's the last page
            if len(current_batch) < per_page:
                break
                
            page += 1
            # Slight delay to respect API rate limits
            time.sleep(0.1) 
            
        except Exception as e:
            print(f"Exception fetching reviews: {e}")
            break
            
    print(f"--- Fetch Complete. Total raw reviews: {len(all_reviews)} ---")
    return all_reviews

def calculate_stats(reviews):
    """
    Calculates average rating and star distribution for the filtered list.
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
        # Safely get rating
        rating = r.get('rating', 5)
        try:
            rating = int(rating)
        except:
            rating = 5
            
        # Ensure rating is within bounds 1-5
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
    # 1. Get the handle from the frontend request (e.g., ?handle=version-h1)
    target_handle = request.args.get('handle')
    
    if not target_handle:
        return jsonify({"error": "Missing 'handle' parameter"}), 400

    # 2. Fetch ALL raw reviews from Judge.me
    raw_reviews = fetch_all_shop_reviews()
    
    # 3. Filter reviews based on Logic
    #    - Must match product_handle
    #    - Must be published (published == true)
    filtered_reviews = []
    
    print(f"Filtering for handle: '{target_handle}'...")
    
    for r in raw_reviews:
        # Check Handle
        r_handle = r.get('product_handle')
        if r_handle != target_handle:
            continue
            
        # Check Published Status
        is_published = r.get('published')
        if is_published is not True:
            continue
            
        # If passed, add to list
        filtered_reviews.append(r)

    print(f"Matches found: {len(filtered_reviews)}")

    # 4. Calculate Stats on the Cleaned List
    stats = calculate_stats(filtered_reviews)
    
    # 5. Format the Response (Map fields from your JSON)
    clean_reviews = []
    for r in filtered_reviews:
        
        # A. Extract Media (Images/Videos)
        # Based on your JSON, pictures is an array of objects with 'urls'
        media = []
        if r.get('pictures'):
            for p in r['pictures']:
                # Safely access nested dictionary keys
                urls = p.get('urls', {})
                # Use 'original' size, fallback to 'huge'
                img_url = urls.get('original') or urls.get('huge')
                
                if img_url: 
                    media.append({
                        "type": "image", 
                        "url": img_url
                    })

        # B. Handle Reviewer Name
        reviewer_data = r.get('reviewer', {})
        author_name = reviewer_data.get('name', 'Anonymous')
        # Create initials (e.g. "John Doe" -> "J")
        initials = author_name[0].upper() if author_name else "A"

        # C. Handle Verification Status
        # Map specific API strings to a simple boolean
        raw_verified = r.get('verified', 'nothing')
        is_verified = raw_verified in ['buyer', 'verified_buyer', 'confirmed-buyer', 'email', 'verified-purchase']

        # D. Build the clean object
        clean_reviews.append({
            "id": r.get('id'),
            "title": r.get('title'), # Might be null
            "body": r.get('body'),
            "rating": int(r.get('rating', 5)),
            "author": author_name,
            "initials": initials,
            "is_verified": is_verified,
            "date": r.get('created_at'),
            "media": media,
            # Pass original verification string just in case frontend needs it
            "verification_type": raw_verified 
        })

    # 6. Return the final JSON structure
    return jsonify({
        "stats": stats,
        "reviews": clean_reviews
    })

if __name__ == '__main__':
    # Run on port 5000
    app.run(debug=True, port=5000)