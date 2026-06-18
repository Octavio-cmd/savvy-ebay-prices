import os
import requests
import json
import base64
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

app = Flask(__name__)

# Environment variables (set in Railway)
EBAY_APP_ID = os.environ.get('EBAY_APP_ID')
EBAY_DEV_ID = os.environ.get('EBAY_DEV_ID')
EBAY_CERT_ID = os.environ.get('EBAY_CERT_ID')

# eBay OAuth and Browse API endpoints
EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# Global token cache
_token_cache = {"token": None, "expires_at": 0}

def get_requests_session():
    """Configure requests session with retries and longer timeout"""
    session = requests.Session()
    retry = Retry(
        total=2,
        read=2,
        connect=2,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_oauth_token():
    """
    Get OAuth token from eBay using Client Credentials flow
    Uses App ID (Client ID) and Cert ID (Client Secret)
    """
    global _token_cache
    
    # Return cached token if still valid
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]
    
    if not all([EBAY_APP_ID, EBAY_CERT_ID]):
        app.logger.error("Missing eBay credentials for OAuth")
        return None
    
    try:
        # Encode credentials
        credentials = f"{EBAY_APP_ID}:{EBAY_CERT_ID}"
        credentials_b64 = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {credentials_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }
        
        session = get_requests_session()
        response = session.post(EBAY_OAUTH_URL, headers=headers, data=data, timeout=30)
        response.raise_for_status()
        
        token_data = response.json()
        token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)
        
        if token:
            # Cache token (expires in 1 hour, refresh at 55 minutes)
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + (expires_in - 300)
            app.logger.info("OAuth token obtained successfully")
            return token
        else:
            app.logger.error("No access_token in eBay response")
            return None
            
    except requests.exceptions.RequestException as e:
        app.logger.error(f"OAuth token request failed: {str(e)}")
        return None

def search_browse_api(keywords):
    """
    Search eBay using Browse API
    Returns filtered results with price, title, itemId
    """
    token = get_oauth_token()
    if not token:
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        params = {
            "q": keywords,
            "limit": 50,
            "sort": "price"
        }
        
        session = get_requests_session()
        response = session.get(EBAY_BROWSE_URL, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        return data
        
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Browse API request failed: {str(e)}")
        return None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/search', methods=['GET'])
def search_ebay():
    """
    GET /search?q=keyword&size=XL
    Returns: {found, query, listings, stats}
    """
    query = request.args.get('q', '')
    size = request.args.get('size', '')
    
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400
    
    search_query = f"{query} {size}".strip()
    
    try:
        data = search_browse_api(search_query)
        
        if not data:
            return jsonify({
                "found": False,
                "query": search_query,
                "listings": 0,
                "error": "eBay API returned no data"
            }), 503
        
        items = data.get('itemSummaries', [])
        
        if not items:
            return jsonify({
                "found": False,
                "query": search_query,
                "listings": 0
            }), 200
        
        # Extract and sort by price
        listings = []
        for item in items[:10]:  # Top 10
            try:
                price_obj = item.get('price', {})
                price_value = price_obj.get('value') if isinstance(price_obj, dict) else None
                
                listing = {
                    "id": item.get('itemId'),
                    "title": item.get('title', 'N/A'),
                    "price": float(price_value) if price_value else None,
                    "url": item.get('itemWebUrl', ''),
                    "image": item.get('image', {}).get('imageUrl', '')
                }
                listings.append(listing)
            except Exception as e:
                app.logger.warning(f"Error parsing item: {str(e)}")
                continue
        
        # Sort by price
        listings.sort(key=lambda x: x['price'] if x['price'] else float('inf'))
        
        if not listings:
            return jsonify({
                "found": False,
                "query": search_query,
                "listings": 0
            }), 200
        
        min_price = listings[0]['price']
        max_price = listings[-1]['price']
        avg_price = sum(l['price'] for l in listings if l['price']) / len([l for l in listings if l['price']]) if listings else 0
        
        return jsonify({
            "found": True,
            "query": search_query,
            "listings": len(listings),
            "stats": {
                "minPrice": min_price,
                "maxPrice": max_price,
                "avgPrice": round(avg_price, 2)
            },
            "items": listings
        }), 200
        
    except Exception as e:
        app.logger.error(f"Search error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/search-upc', methods=['GET'])
def search_upc():
    """
    GET /search-upc?upc=071214003222
    Returns: {found, upc, listings, stats}
    """
    upc = request.args.get('upc', '')
    
    if not upc:
        return jsonify({"error": "Missing 'upc' parameter"}), 400
    
    try:
        # Search by UPC
        data = search_browse_api(upc)
        
        if not data:
            return jsonify({
                "found": False,
                "upc": upc,
                "listings": 0,
                "error": "eBay API returned no data"
            }), 503
        
        items = data.get('itemSummaries', [])
        
        if not items:
            return jsonify({
                "found": False,
                "upc": upc,
                "listings": 0
            }), 200
        
        # Extract and sort by price
        listings = []
        for item in items[:10]:  # Top 10
            try:
                price_obj = item.get('price', {})
                price_value = price_obj.get('value') if isinstance(price_obj, dict) else None
                
                listing = {
                    "id": item.get('itemId'),
                    "title": item.get('title', 'N/A'),
                    "price": float(price_value) if price_value else None,
                    "url": item.get('itemWebUrl', ''),
                    "image": item.get('image', {}).get('imageUrl', '')
                }
                listings.append(listing)
            except Exception as e:
                app.logger.warning(f"Error parsing item: {str(e)}")
                continue
        
        # Sort by price
        listings.sort(key=lambda x: x['price'] if x['price'] else float('inf'))
        
        if not listings:
            return jsonify({
                "found": False,
                "upc": upc,
                "listings": 0
            }), 200
        
        min_price = listings[0]['price']
        max_price = listings[-1]['price']
        
        return jsonify({
            "found": True,
            "upc": upc,
            "listings": len(listings),
            "stats": {
                "minPrice": min_price,
                "maxPrice": max_price,
                "currency": "USD"
            },
            "items": listings
        }), 200
        
    except Exception as e:
        app.logger.error(f"UPC search error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/test-token', methods=['GET'])
def test_token():
    """
    Test endpoint to verify OAuth token generation
    GET /test-token
    """
    try:
        token = get_oauth_token()
        if token:
            return jsonify({
                "status": "success",
                "message": "OAuth token obtained",
                "token_length": len(token)
            }), 200
        else:
            return jsonify({
                "status": "failed",
                "message": "Could not obtain OAuth token"
            }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
