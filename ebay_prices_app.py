import os
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Environment variables (set in Railway)
EBAY_APP_ID = os.environ.get('EBAY_APP_ID')
EBAY_DEV_ID = os.environ.get('EBAY_DEV_ID')
EBAY_CERT_ID = os.environ.get('EBAY_CERT_ID')

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

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
        return jsonify({"error": "Missing eBay credentials"}), 500
    
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
        
        response = requests.get(EBAY_FINDING_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract findItemsByKeywordsResponse
        results = data.get('findItemsByKeywordsResponse', [{}])[0]
        items = results.get('searchResult', [{}])[0].get('item', [])
        
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
            price_str = item.get('sellingStatus', [{}])[0].get('convertedCurrentPrice', [{}])[0].get('__value__', '0')
            try:
                price = float(price_str)
                prices.append(price)
            except ValueError:
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
    
    except requests.RequestException as e:
        return jsonify({"error": f"eBay API error: {str(e)}"}), 500
    except Exception as e:
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
        return jsonify({"error": "Missing eBay credentials"}), 500
    
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
        
        response = requests.get(EBAY_FINDING_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract items
        results = data.get('findItemsByKeywordsResponse', [{}])[0]
        items = results.get('searchResult', [{}])[0].get('item', [])
        
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
        title = item.get('title', ['Unknown'])[0]
        price_str = item.get('sellingStatus', [{}])[0].get('convertedCurrentPrice', [{}])[0].get('__value__', '0')
        seller = item.get('sellerInfo', [{}])[0].get('sellerUserName', ['Unknown'])[0]
        condition = item.get('condition', ['Unknown'])[0]
        
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            price = 0
        
        # Extract all prices for stats
        prices = []
        for i in items[:10]:  # Get top 10 items
            try:
                p = float(i.get('sellingStatus', [{}])[0].get('convertedCurrentPrice', [{}])[0].get('__value__', '0'))
                if p > 0:
                    prices.append(p)
            except (ValueError, TypeError):
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
    
    except requests.RequestException as e:
        return jsonify({"error": f"eBay API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
