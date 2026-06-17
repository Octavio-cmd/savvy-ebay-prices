import os
import requests
import json
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

# Environment variables (set in Railway)
EBAY_APP_ID = os.environ.get('EBAY_APP_ID')
EBAY_DEV_ID = os.environ.get('EBAY_DEV_ID')
EBAY_CERT_ID = os.environ.get('EBAY_CERT_ID')

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

# Configure requests session with retries and longer timeout
def get_requests_session():
    session = requests.Session()
    retry = Retry(
        total=1,
        read=1,
        connect=1,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/search', methods=['GET'])
def search_ebay():
    """
    GET /search?q=keyword&size=XL
    Returns: {found, query, listings, stats, suggested}
    """
    query = request.args.get('q', '')
    size = request.args.get('size', '')
    
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400
    
    # Append size to query if provided
    search_query = f"{query} {size}".strip()
    
    if not all([EBAY_APP_ID, EBAY_DEV_ID, EBAY_CERT_ID]):
        return jsonify({"error": "Missing eBay credentials in environment"}), 500
    
    try:
        # eBay Finding API request
        params = {
            'OPERATION-NAME': 'findItemsByKeywords',
            'SERVICE-VERSION': '1.0.0',
            'SECURITY-APPNAME': EBAY_APP_ID,
            'GLOBAL-ID': 'EBAY-US',
            'RESPONSE-DATA-FORMAT': 'JSON',
            'REST-PAYLOAD': 'true',
            'keywords': search_query,
            'paginationInput.entriesPerPage': '100'
        }
        
        session = get_requests_session()
        # TIMEOUT INCREASED TO 60 SECONDS
        response = session.get(EBAY_FINDING_URL, params=params, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        # VALIDATE: Check if eBay returned an error
        if 'errorMessage' in data:
            error_msg = data.get('errorMessage', [{}])[0].get('error', [{}])[0].get('message', 'Unknown eBay error')
            app.logger.error(f"eBay API error: {error_msg}")
            return jsonify({"error": f"eBay returned error: {error_msg}"}), 400
        
        # Extract findItemsByKeywordsResponse
        response_list = data.get('findItemsByKeywordsResponse', [])
        if not response_list or len(response_list) == 0:
            app.logger.error("No findItemsByKeywordsResponse in eBay data")
            return jsonify({"error": "Invalid eBay response format"}), 500
        
        results = response_list[0]
        search_result = results.get('searchResult', [])
        
        if not search_result or len(search_result) == 0:
            items = []
        else:
            items = search_result[0].get('item', [])
        
        if not items:
            return jsonify({
                "found": False,
                "query": search_query,
                "listings": 0,
                "stats": {
                    "minPrice": None,
                    "avgPrice": None,
                    "maxPrice": None,
                    "totalListings": 0
                },
                "suggested": {
                    "price": None,
                    "margin": None
                }
            }), 200
        
        # Extract prices
        prices = []
        for item in items:
            try:
                selling_status = item.get('sellingStatus', [{}])
                if selling_status and len(selling_status) > 0:
                    current_price = selling_status[0].get('convertedCurrentPrice', [{}])
                    if current_price and len(current_price) > 0:
                        price_str = current_price[0].get('__value__', '0')
                        price = float(price_str)
                        if price > 0:
                            prices.append(price)
            except (ValueError, TypeError, IndexError, KeyError):
                pass
        
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)
            
            # Suggested price = avg * 0.75 (25% margin)
            suggested_price = round(avg_price * 0.75, 2)
        else:
            min_price = avg_price = max_price = suggested_price = None
        
        return jsonify({
            "found": True,
            "query": search_query,
            "listings": len(items),
            "stats": {
                "minPrice": round(min_price, 2) if min_price else None,
                "avgPrice": round(avg_price, 2) if avg_price else None,
                "maxPrice": round(max_price, 2) if max_price else None,
                "totalListings": len(items)
            },
            "suggested": {
                "price": suggested_price,
                "margin": "25%"
            }
        }), 200
    
    except requests.exceptions.Timeout:
        app.logger.error("eBay API timeout on /search - took longer than 60 seconds")
        return jsonify({"error": "eBay API timeout - request took too long"}), 504
    except requests.exceptions.ConnectionError as e:
        app.logger.error(f"eBay connection error on /search: {str(e)}")
        return jsonify({"error": f"Cannot connect to eBay: {str(e)}"}), 503
    except requests.RequestException as e:
        app.logger.error(f"eBay request error on /search: {str(e)}")
        return jsonify({"error": f"eBay API error: {str(e)}"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in /search: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route('/search-upc', methods=['GET'])
def search_upc():
    """
    GET /search-upc?upc=071214003222
    Returns: {found, upc, product, stats, suggested}
    """
    upc = request.args.get('upc', '')
    
    if not upc:
        return jsonify({"error": "Missing 'upc' parameter"}), 400
    
    if not all([EBAY_APP_ID, EBAY_DEV_ID, EBAY_CERT_ID]):
        return jsonify({"error": "Missing eBay credentials in environment"}), 500
    
    try:
        # eBay Finding API request - search by UPC
        params = {
            'OPERATION-NAME': 'findItemsByKeywords',
            'SERVICE-VERSION': '1.0.0',
            'SECURITY-APPNAME': EBAY_APP_ID,
            'GLOBAL-ID': 'EBAY-US',
            'RESPONSE-DATA-FORMAT': 'JSON',
            'REST-PAYLOAD': 'true',
            'keywords': upc,
            'paginationInput.entriesPerPage': '20'
        }
        
        session = get_requests_session()
        # TIMEOUT INCREASED TO 60 SECONDS
        response = session.get(EBAY_FINDING_URL, params=params, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        # VALIDATE: Check if eBay returned an error
        if 'errorMessage' in data:
            error_msg = data.get('errorMessage', [{}])[0].get('error', [{}])[0].get('message', 'Unknown eBay error')
            app.logger.error(f"eBay API error on UPC search: {error_msg}")
            return jsonify({"error": f"eBay returned error: {error_msg}"}), 400
        
        # Extract items safely
        response_list = data.get('findItemsByKeywordsResponse', [])
        if not response_list or len(response_list) == 0:
            app.logger.error("No findItemsByKeywordsResponse in eBay data")
            return jsonify({"error": "Invalid eBay response format"}), 500
        
        results = response_list[0]
        search_result = results.get('searchResult', [])
        
        if not search_result or len(search_result) == 0:
            items = []
        else:
            items = search_result[0].get('item', [])
        
        if not items:
            return jsonify({
                "found": False,
                "upc": upc,
                "product": None,
                "stats": None,
                "suggested": None
            }), 200
        
        # Get first item (most relevant)
        item = items[0]
        
        # Extract product info safely
        title = item.get('title', ['Unknown'])[0] if item.get('title') else 'Unknown'
        
        selling_status = item.get('sellingStatus', [{}])
        price_str = '0'
        if selling_status and len(selling_status) > 0:
            current_price = selling_status[0].get('convertedCurrentPrice', [{}])
            if current_price and len(current_price) > 0:
                price_str = current_price[0].get('__value__', '0')
        
        seller_info = item.get('sellerInfo', [{}])
        seller = 'Unknown'
        if seller_info and len(seller_info) > 0:
            seller_name = seller_info[0].get('sellerUserName', ['Unknown'])
            seller = seller_name[0] if seller_name else 'Unknown'
        
        condition = item.get('condition', ['Unknown'])[0] if item.get('condition') else 'Unknown'
        
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            price = 0
        
        # Extract all prices for stats
        prices = []
        for i in items[:10]:  # Get top 10 items
            try:
                selling_status = i.get('sellingStatus', [{}])
                if selling_status and len(selling_status) > 0:
                    current_price = selling_status[0].get('convertedCurrentPrice', [{}])
                    if current_price and len(current_price) > 0:
                        p = float(current_price[0].get('__value__', '0'))
                        if p > 0:
                            prices.append(p)
            except (ValueError, TypeError, IndexError, KeyError):
                pass
        
        if prices:
            min_price = min(prices)
            avg_price = sum(prices) / len(prices)
            max_price = max(prices)
            suggested_price = round(avg_price * 0.75, 2)
        else:
            min_price = avg_price = max_price = suggested_price = None
        
        return jsonify({
            "found": True,
            "upc": upc,
            "product": {
                "title": title,
                "price": price,
                "seller": seller,
                "condition": condition
            },
            "stats": {
                "minPrice": round(min_price, 2) if min_price else None,
                "avgPrice": round(avg_price, 2) if avg_price else None,
                "maxPrice": round(max_price, 2) if max_price else None,
                "totalListings": len(items)
            },
            "suggested": {
                "price": suggested_price,
                "margin": "25%"
            }
        }), 200
    
    except requests.exceptions.Timeout:
        app.logger.error("eBay API timeout on /search-upc - took longer than 60 seconds")
        return jsonify({"error": "eBay API timeout - request took too long"}), 504
    except requests.exceptions.ConnectionError as e:
        app.logger.error(f"eBay connection error on /search-upc: {str(e)}")
        return jsonify({"error": f"Cannot connect to eBay: {str(e)}"}), 503
    except requests.RequestException as e:
        app.logger.error(f"eBay request error on /search-upc: {str(e)}")
        return jsonify({"error": f"eBay API error: {str(e)}"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in /search-upc: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
