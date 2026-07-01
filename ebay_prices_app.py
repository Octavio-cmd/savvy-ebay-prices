"""
SAVVY SCANNER - Backend con ALGOPIX API (VERSIÓN SIMPLIFICADA)
Solo envía el parámetro keywords, Algopix auto-detecta el tipo

Instalación de dependencias:
pip install flask requests python-dotenv flask-cors
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
from datetime import datetime
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURACIÓN DE ALGOPIX (DESDE VARIABLES DE ENTORNO)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALGOPIX_APP_ID = os.environ.get("ALGOPIX_APP_ID", "")
ALGOPIX_API_KEY = os.environ.get("ALGOPIX_API_KEY", "")
ALGOPIX_API_URL = "https://api.algopix.ai/v3/products/matches"

# Validación de credenciales
if not ALGOPIX_APP_ID or not ALGOPIX_API_KEY:
    logger.warning("⚠️  ALGOPIX_APP_ID o ALGOPIX_API_KEY no configurados en variables de entorno")

# Headers para Algopix
ALGOPIX_HEADERS = {
    "X-API-KEY": ALGOPIX_API_KEY,
    "X-APP-ID": ALGOPIX_APP_ID,
    "Content-Type": "application/json"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CACHÉ EN MEMORIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CACHE = {}
LOOKUP_COUNT = {
    "total": 0,
    "today": 0,
    "reset_date": datetime.now().strftime("%Y-%m-%d")
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUTAS PRINCIPALES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "online",
        "service": "Savvy Scanner - Algopix Backend",
        "timestamp": datetime.now().isoformat(),
        "lookups_today": LOOKUP_COUNT["today"],
        "lookups_total": LOOKUP_COUNT["total"],
        "algopix_configured": bool(ALGOPIX_APP_ID and ALGOPIX_API_KEY)
    })


@app.route('/search-upc', methods=['GET'])
def search_upc():
    """
    Búsqueda por UPC usando Algopix API v3/search (VERSIÓN SIMPLIFICADA)
    
    Parámetros:
    - upc: Código UPC a buscar (ej: 886227362638)
    - search_term: (Opcional) Búsqueda por texto alternativa
    """
    
    upc = request.args.get('upc', '').strip()
    search_term = request.args.get('search_term', '').strip()
    
    # Validación
    if not upc and not search_term:
        return jsonify({
            "error": "Debe proporcionar UPC o search_term",
            "status": "error"
        }), 400
    
    # CACHÉ
    cache_key = f"upc_{upc}" if upc else f"search_{search_term}"
    if cache_key in CACHE:
        logger.info(f"✅ CACHE HIT: {cache_key}")
        return jsonify({
            "data": CACHE[cache_key],
            "status": "success",
            "cached": True,
            "message": "Datos obtenidos del caché"
        })
    
    logger.info(f"🔍 Buscando en Algopix: {upc or search_term}")
    
    try:
        response = _call_algopix_search(upc or search_term)
        
        if response.get("status") == "success":
            CACHE[cache_key] = response.get("data", {})
            LOOKUP_COUNT["total"] += 1
            LOOKUP_COUNT["today"] += 1
            
            logger.info(f"✅ Búsqueda exitosa. Lookups hoy: {LOOKUP_COUNT['today']}")
            
            return jsonify({
                "data": response.get("data"),
                "status": "success",
                "cached": False,
                "lookups_remaining_today": max(0, int(5000 / 30) - LOOKUP_COUNT["today"])
            })
        else:
            return jsonify(response), 400
            
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        return jsonify({
            "error": f"Error: {str(e)}",
            "status": "error"
        }), 500


@app.route('/test-apis', methods=['GET'])
def test_apis():
    """
    Test cada API individualmente para debug - RESPUESTA COMPLETA
    """
    upc = request.args.get('upc', '071249078761')
    
    results = {
        "upc": upc,
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }
    
    # TEST 1: ALGOPIX
    try:
        logger.info(f"🧪 TEST 1: Algopix")
        response = requests.get(
            "https://api.algopix.ai/v3/products/matches",
            params={"keywords": upc},
            headers={
                "X-API-KEY": ALGOPIX_API_KEY,
                "X-APP-ID": ALGOPIX_APP_ID
            },
            timeout=5
        )
        results["tests"]["algopix"] = {
            "status_code": response.status_code,
            "full_response": response.json() if response.status_code < 500 else response.text
        }
        logger.info(f"   Status: {response.status_code}")
    except Exception as e:
        results["tests"]["algopix"] = {"error": str(e)}
        logger.error(f"   Error: {str(e)}")
    
    # TEST 2: UPCitemdb
    try:
        logger.info(f"🧪 TEST 2: UPCitemdb")
        response = requests.get(
            f"https://api.upcitemdb.com/prod/trial/lookup?upc={upc}",
            timeout=5
        )
        data = response.json()
        results["tests"]["upcitemdb"] = {
            "status_code": response.status_code,
            "full_response": data,
            "has_items": bool(data.get("items"))
        }
        logger.info(f"   Status: {response.status_code} | Has items: {bool(data.get('items'))}")
    except Exception as e:
        results["tests"]["upcitemdb"] = {"error": str(e)}
        logger.error(f"   Error: {str(e)}")
    
    # TEST 3: OpenFoodFacts
    try:
        logger.info(f"🧪 TEST 3: OpenFoodFacts")
        response = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{upc}.json",
            timeout=5
        )
        data = response.json()
        results["tests"]["openfoodfacts"] = {
            "status_code": response.status_code,
            "full_response": data,
            "status": data.get("status")
        }
        logger.info(f"   Status: {response.status_code}")
    except Exception as e:
        results["tests"]["openfoodfacts"] = {"error": str(e)}
        logger.error(f"   Error: {str(e)}")
    
    return jsonify(results)
def test_algopix():
    """Test endpoint"""
    logger.info("🧪 Testing Algopix...")
    
    try:
        test_upc = "886227362638"
        response = _call_algopix_search(test_upc)
        
        return jsonify({
            "test_upc": test_upc,
            "response": response,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Test error: {str(e)}")
        return jsonify({
            "error": f"Test failed: {str(e)}",
            "status": "error"
        }), 500


@app.route('/quota', methods=['GET'])
def quota():
    """Cuota de lookups"""
    lookups_used = LOOKUP_COUNT["total"]
    lookups_remaining = 5000 - lookups_used
    percentage_used = (lookups_used / 5000) * 100
    
    return jsonify({
        "plan": "Algopix API - 5,000 lookups/mes",
        "lookups_total": 5000,
        "lookups_used": lookups_used,
        "lookups_remaining": lookups_remaining,
        "percentage_used": f"{percentage_used:.1f}%",
        "lookups_today": LOOKUP_COUNT["today"]
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNCIÓN PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _call_ebay_search_by_upc(upc):
    """
    Busca en eBay por UPC/GTIN y devuelve el precio total más barato
    (precio + envío) entre los primeros 20 resultados Buy It Now.
    Prefiere vendedores de USA sobre China si el precio es similar.
    """
    try:
        token = _get_ebay_token()
        if not token:
            logger.warning("⚠️  eBay: no se pudo obtener token")
            return None

        headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
        search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
        is_numeric_upc = upc.isdigit() and 8 <= len(upc) <= 14

        def _fetch_items(params):
            r = requests.get(search_url, headers=headers, params=params, timeout=10)
            logger.info(f"   eBay status: {r.status_code}")
            if r.status_code == 200:
                return r.json().get("itemSummaries", [])
            return []

        # Intento 1: búsqueda por GTIN (más preciso)
        items = []
        if is_numeric_upc:
            items = _fetch_items({
                "gtin": upc, "limit": "20",
                "filter": "buyingOptions:{FIXED_PRICE}",
                "sort": "price"
            })
            logger.info(f"🛒 eBay GTIN '{upc}': {len(items)} resultados")

        # Intento 2: si GTIN no dio nada, buscar por keyword
        if not items:
            items = _fetch_items({
                "q": upc, "limit": "20",
                "filter": "buyingOptions:{FIXED_PRICE}",
                "sort": "price"
            })
            logger.info(f"🛒 eBay keyword '{upc}': {len(items)} resultados")

        if not items:
            logger.info("   eBay: sin resultados")
            return None

        # Calcular precio total (precio + envío) para cada item
        def get_total(it):
            p = float((it.get("price") or {}).get("value", 0))
            ships = it.get("shippingOptions") or []
            s = 0.0
            if ships:
                sc = (ships[0].get("shippingCost") or {})
                s = float(sc.get("value", 0))
            return round(p + s, 2), round(p, 2), round(s, 2)

        # Separar items de USA vs otros (China, etc.)
        usa_items = [it for it in items if "United States" in (it.get("itemLocation") or {}).get("country", "")]
        other_items = [it for it in items if it not in usa_items]

        # Encontrar el más barato primero en USA, luego en otros
        best_item = None
        best_total = None
        best_price = None
        best_shipping = None

        for pool in [usa_items, other_items]:
            if not pool:
                continue
            for it in pool:
                total, price, shipping = get_total(it)
                if total > 0 and (best_total is None or total < best_total):
                    best_total = total
                    best_price = price
                    best_shipping = shipping
                    best_item = it
            if best_item and best_item in usa_items:
                break

        # Si no hubo nada con precio válido, tomar el primero
        if not best_item:
            best_item = items[0]
            best_total, best_price, best_shipping = get_total(best_item)
            if best_total == 0:
                best_total = best_price = 0.0
                best_shipping = 0.0

        location = (best_item.get("itemLocation") or {}).get("country", "")
        logger.info(f"✅ eBay MEJOR PRECIO: '{best_item.get('title','')[:50]}' | "
                    f"item=${best_price} + ship=${best_shipping} = total=${best_total} [{location}]")

        formatted_data = {
            "upc": upc,
            "name": best_item.get("title", "Unknown"),
            "brand": "",
            "ebay_price": best_price,
            "ebay_shipping": best_shipping,
            "ebay_total": best_total,
            "amazon_price": 0,
            "walmart_price": 0,
            "demand_level": "UNKNOWN",
            "sellers_count": len(items),
            "suggested_price": round(best_total * 0.95, 2) if best_total > 0 else 0,
            "margin_suggestion": "",
            "category": ((best_item.get("categories") or [{}])[0]).get("categoryName", ""),
            "asin": "",
            "score": 0,
            "data_source": "eBay ✅",
            "ebay_item_id": best_item.get("itemId", ""),
            "ebay_url": best_item.get("itemWebUrl", ""),
            "ebay_location": location,
            "timestamp": datetime.now().isoformat()
        }
        return formatted_data

    except Exception as e:
        logger.warning(f"⚠️  eBay search error: {str(e)}")
        return None

def _call_algopix_search(keywords):
    """
    Cascada de búsqueda: eBay primero (más confiable para tu negocio),
    luego Algopix, luego APIs gratuitas (UPCitemdb, OpenFoodFacts)
    """

    # ══════════════════════════════════════════════════════════════════════════════════
    # PASO 0: INTENTA EBAY PRIMERO
    # ══════════════════════════════════════════════════════════════════════════════════

    ebay_result = _call_ebay_search_by_upc(keywords)
    if ebay_result:
        return {"status": "success", "data": ebay_result}

    # ══════════════════════════════════════════════════════════════════════════════════
    # PASO 1: INTENTA ALGOPIX
    # ══════════════════════════════════════════════════════════════════════════════════
    
    try:
        params = {"keywords": keywords}
        logger.info(f"🔍 Intentando Algopix: {keywords}")
        
        response = requests.get(
            ALGOPIX_API_URL,
            params=params,

            headers=ALGOPIX_HEADERS,
            timeout=10
        )
        
        logger.info(f"   Status: {response.status_code}")
        data = response.json()
        
        if response.status_code == 200 and data.get("status") == "SUCCESS":
            result = data.get("result", {})
            
            if result:
                # Algopix ÉXITO
                offers = result.get("offers", {})
                ebay_price = _extract_price(offers, "EBAY_US")
                amazon_price = _extract_price(offers, "AMAZON_US")
                walmart_price = _extract_price(offers, "WALMART_US")
                
                formatted_data = {
                    "upc": keywords,
                    "name": result.get("product", {}).get("name", "Unknown"),
                    "brand": result.get("product", {}).get("brand", ""),
                    "ebay_price": round(ebay_price, 2),
                    "amazon_price": round(amazon_price, 2),
                    "walmart_price": round(walmart_price, 2),
                    "demand_level": result.get("demandLevel", {}).get("demandCode", "UNKNOWN"),
                    "sellers_count": result.get("sellers", {}).get("sellerCount", 0),
                    "suggested_price": round(ebay_price * 1.15 if ebay_price > 0 else 0, 2),
                    "margin_suggestion": _calculate_margin(ebay_price, ebay_price * 1.15 if ebay_price > 0 else 0),
                    "category": result.get("category", {}).get("name", ""),
                    "asin": result.get("asin", ""),
                    "score": result.get("score", 0),
                    "data_source": "Algopix ✅",
                    "timestamp": datetime.now().isoformat()
                }
                
                logger.info(f"✅ Algopix ÉXITO: {formatted_data['name'][:50]}")
                return {"status": "success", "data": formatted_data}
    
    except Exception as e:
        logger.warning(f"⚠️  Algopix falló: {str(e)}")
    
    # ══════════════════════════════════════════════════════════════════════════════════
    # PASO 2: FALLBACK A UPCitemdb (GRATUITO)
    # ══════════════════════════════════════════════════════════════════════════════════
    
    try:
        logger.info(f"🔍 Intentando UPCitemdb: {keywords}")
        response = requests.get(
            f"https://api.upcitemdb.com/prod/trial/lookup?upc={keywords}",
            timeout=8
        )
        data = response.json()
        
        if data.get("items") and len(data["items"]) > 0:
            item = data["items"][0]
            formatted_data = {
                "upc": keywords,
                "name": item.get("title") or item.get("description") or "Unknown",
                "brand": item.get("brand", ""),
                "ebay_price": 0,
                "amazon_price": 0,
                "walmart_price": 0,
                "demand_level": "UNKNOWN",
                "sellers_count": 0,
                "suggested_price": 0,
                "margin_suggestion": "Esperando Algopix",
                "category": item.get("category", ""),
                "asin": "",
                "score": 0,
                "data_source": "UPCitemdb ⭐ (Esperando precios de Algopix)",
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ UPCitemdb ÉXITO: {formatted_data['name'][:50]}")
            return {"status": "success", "data": formatted_data}
    
    except Exception as e:
        logger.warning(f"⚠️  UPCitemdb falló: {str(e)}")
    
    # ══════════════════════════════════════════════════════════════════════════════════
    # PASO 3: FALLBACK A OpenFoodFacts (GRATUITO, para alimentos)
    # ══════════════════════════════════════════════════════════════════════════════════
    
    try:
        logger.info(f"🔍 Intentando OpenFoodFacts: {keywords}")
        response = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{keywords}.json",
            timeout=8
        )
        data = response.json()
        
        if data.get("status") == 1 and data.get("product"):
            product = data["product"]
            formatted_data = {
                "upc": keywords,
                "name": product.get("product_name_en") or product.get("product_name") or "Unknown",
                "brand": product.get("brands", ""),
                "ebay_price": 0,
                "amazon_price": 0,
                "walmart_price": 0,
                "demand_level": "UNKNOWN",
                "sellers_count": 0,
                "suggested_price": 0,
                "margin_suggestion": "No disponible",
                "category": product.get("categories", ""),
                "asin": "",
                "score": 0,
                "data_source": "OpenFoodFacts (Free) ⭐",
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ OpenFoodFacts ÉXITO: {formatted_data['name'][:50]}")
            return {"status": "success", "data": formatted_data}
    
    except Exception as e:
        logger.warning(f"⚠️  OpenFoodFacts falló: {str(e)}")
    
    # ══════════════════════════════════════════════════════════════════════════════════
    # TODOS LOS SERVICIOS FALLARON
    # ══════════════════════════════════════════════════════════════════════════════════
    
    logger.error(f"❌ TODOS LOS SERVICIOS FALLARON para: {keywords}")
    return {
        "status": "error",
        "message": "Producto no encontrado en ningún servicio",
        "services_tried": ["Algopix", "UPCitemdb", "OpenFoodFacts"],
        "upc": keywords
    }


def _extract_price(offers, marketplace):
    """Extrae precio de un marketplace"""
    try:
        market_offers = offers.get(marketplace, {})
        if market_offers and len(market_offers) > 0:
            return float(market_offers[0].get("price", 0))
        return 0
    except:
        return 0


def _calculate_margin(ebay_price, suggested_price):
    """Calcula margen"""
    if not ebay_price or ebay_price == 0:
        return "No disponible"
    
    ebay_fees = ebay_price * 0.20
    
    if suggested_price > ebay_price:
        margin = suggested_price - ebay_price - ebay_fees
        return f"Vende a ${suggested_price:.2f} (ganancia ${margin:.2f})"
    else:
        return f"Precio eBay: ${ebay_price:.2f}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EBAY BROWSE API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EBAY_CLIENT_ID     = "StevenGa-SavvySca-PRD-81addb012-655f2649"
EBAY_CLIENT_SECRET = "PRD-1addb012c112-1d46-4c31-9731-99d5"
EBAY_TOKEN_URL     = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_URL    = "https://api.ebay.com/buy/browse/v1/item/"

_ebay_token_cache = {"token": None, "expires_at": 0}

def _get_ebay_token():
    import base64, time
    now = time.time()
    if _ebay_token_cache["token"] and now < _ebay_token_cache["expires_at"] - 60:
        return _ebay_token_cache["token"]
    credentials = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"}
    data = "grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope"
    resp = requests.post(EBAY_TOKEN_URL, headers=headers, data=data, timeout=10)
    if resp.status_code != 200:
        logger.error(f"❌ eBay token error {resp.status_code}: {resp.text}")
        return None
    token_data = resp.json()
    _ebay_token_cache["token"] = token_data.get("access_token")
    _ebay_token_cache["expires_at"] = now + token_data.get("expires_in", 7200)
    logger.info("✅ eBay token obtenido")
    return _ebay_token_cache["token"]


@app.route('/resolve-url', methods=['GET'])
def resolve_url():
    """
    Resuelve un URL corto de eBay (ebay.io/m/...) y extrae el Item ID.
    La app de eBay en iPhone siempre genera links cortos — este endpoint los resuelve.
    Parámetros:
    - url: URL corto de eBay
    """
    import re
    short_url = request.args.get('url', '').strip()
    if not short_url:
        return jsonify({"error": "Debe proporcionar url", "status": "error"}), 400

    logger.info(f"🔗 Resolviendo URL: {short_url}")

    try:
        resp = requests.get(
            short_url,
            allow_redirects=True,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"}
        )
        final_url = resp.url
        logger.info(f"✅ URL resuelto: {final_url}")

        item_id = None
        patterns = [
            r'/itm/(?:[^/?]+/)?(\d{10,13})',
            r'[?&]item=(\d{10,13})',
            r'[?&]itemId=(\d{10,13})',
            r'/(\d{12,13})(?:[/?]|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, final_url)
            if match:
                item_id = match.group(1)
                break

        if not item_id:
            return jsonify({"status": "error", "error": "No se encontró Item ID", "final_url": final_url}), 404

        return jsonify({"status": "success", "item_id": item_id, "final_url": final_url})

    except Exception as e:
        logger.error(f"❌ resolve_url error: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route('/ebay-item', methods=['GET'])
def ebay_item():
    """
    Busca un item de eBay por su Item ID (extraído del URL).
    Parámetros:
    - item_id: eBay Item ID (ej: 387234567890)
    """
    item_id = request.args.get('item_id', '').strip()
    if not item_id:
        return jsonify({"error": "Debe proporcionar item_id", "status": "error"}), 400

    item_id = ''.join(filter(str.isdigit, item_id))
    if not item_id:
        return jsonify({"error": "item_id inválido", "status": "error"}), 400

    cache_key = f"ebay_item_{item_id}"
    if cache_key in CACHE:
        return jsonify({"data": CACHE[cache_key], "cached": True, "status": "success"})

    logger.info(f"🛒 Buscando eBay item: {item_id}")

    try:
        token = _get_ebay_token()
        if not token:
            return jsonify({"error": "No se pudo obtener token de eBay", "status": "error"}), 500

        headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
        url = f"{EBAY_BROWSE_URL}v1|{item_id}|0"
        logger.info(f"📡 GET {url}")

        resp = requests.get(url, headers=headers, timeout=10)
        logger.info(f"📬 eBay status: {resp.status_code}")

        if resp.status_code != 200:
            return jsonify({"error": f"eBay error {resp.status_code}", "status": "error"}), resp.status_code

        item = resp.json()
        price = 0.0
        price_obj = item.get("price", {})
        if price_obj:
            price = float(price_obj.get("value", 0))

        image_url = item.get("image", {}).get("imageUrl", "")
        additional_images = [ai.get("imageUrl", "") for ai in item.get("additionalImages", []) if ai.get("imageUrl")]

        brand = ""
        for aspect in item.get("localizedAspects", []):
            if aspect.get("name", "").lower() == "brand":
                brand = aspect.get("value", "")
                break

        # ── Extraer costo de envío ────────────────────────────
        shipping_cost = 0.0
        shipping_type = "calculated"
        shipping_options = item.get("shippingOptions", [])
        if shipping_options:
            first = shipping_options[0]
            ship_cost_obj = first.get("shippingCost", {})
            if ship_cost_obj:
                shipping_cost = float(ship_cost_obj.get("value", 0))
                shipping_type = "paid"
            else:
                # Si no hay costo → envío gratis
                shipping_cost = 0.0
                shipping_type = "free"
        # También verificar si el item tiene "freeShipping" flag
        if item.get("shippingOptions") and any(
            float(o.get("shippingCost", {}).get("value", 1)) == 0
            for o in item.get("shippingOptions", [])
        ):
            shipping_cost = 0.0
            shipping_type = "free"

        total_price = round(price + shipping_cost, 2)

        formatted = {
            "item_id": item_id,
            "title": item.get("title", ""),
            "price": round(price, 2),
            "shipping_cost": round(shipping_cost, 2),
            "shipping_type": shipping_type,
            "total_price": total_price,
            "currency": price_obj.get("currency", "USD"),
            "condition": item.get("condition", ""),
            "seller": item.get("seller", {}).get("username", ""),
            "image_url": image_url,
            "additional_images": additional_images[:4],
            "item_url": item.get("itemWebUrl", f"https://www.ebay.com/itm/{item_id}"),
            "brand": brand,
            "found": True,
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"✅ eBay item: {formatted['title'][:50]} | item=${price} ship=${shipping_cost} total=${total_price}")
        CACHE[cache_key] = formatted
        return jsonify({"data": formatted, "status": "success", "cached": False})

    except Exception as e:
        logger.error(f"❌ ebay_item error: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Savvy Scanner - Algopix Backend (Versión Simplificada)")
    logger.info(f"   Endpoint: {ALGOPIX_API_URL}")
    logger.info(f"   Parámetro: keywords (auto-detecta tipo)")
    logger.info(f"   Quota: 5,000 lookups/mes")
    logger.info(f"   Algopix CONFIG: APP_ID={'✅' if ALGOPIX_APP_ID else '❌'} | API_KEY={'✅' if ALGOPIX_API_KEY else '❌'}")
    app.run(host='0.0.0.0', port=port, debug=False)
