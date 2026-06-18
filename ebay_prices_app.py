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
# CONFIGURACIÓN DE ALGOPIX
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALGOPIX_APP_ID = "2pTW5BzPQdYishB6AiRMNE"
ALGOPIX_API_KEY = "2xdVJ17VPIinxRhMpg87Mm7I8ucYh7jnp6VGVc9u"
ALGOPIX_API_URL = "https://api.algopix.ai/v3/search"

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
        "lookups_total": LOOKUP_COUNT["total"]
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


@app.route('/test-algopix', methods=['GET'])
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

def _call_algopix_search(keywords):
    """
    Llama a Algopix v3/search con SOLO el parámetro keywords
    Algopix auto-detecta si es UPC, ASIN, EAN, etc.
    """
    
    try:
        # Parámetros SIMPLIFICADOS - solo keywords
        params = {
            "keywords": keywords
        }
        
        logger.info(f"📡 GET {ALGOPIX_API_URL}")
        logger.info(f"   keywords: {keywords}")
        
        # GET request
        response = requests.get(
            ALGOPIX_API_URL,
            params=params,
            headers=ALGOPIX_HEADERS,
            timeout=10
        )
        
        logger.info(f"📬 Status: {response.status_code}")
        logger.info(f"📦 Response: {response.text[:500]}")
        
        data = response.json()
        
        if response.status_code == 200 and data.get("status") == "SUCCESS":
            result = data.get("result", {})
            
            if result:
                # Extraer precios
                offers = result.get("offers", {})
                
                ebay_price = _extract_price(offers, "EBAY_US")
                amazon_price = _extract_price(offers, "AMAZON_US")
                walmart_price = _extract_price(offers, "WALMART_US")
                
                # Demanda
                demand_level = result.get("demandLevel", {}).get("demandCode", "UNKNOWN")
                
                # Sellers
                sellers_count = result.get("sellers", {}).get("sellerCount", 0)
                
                # Margen
                suggested_price = ebay_price * 1.15 if ebay_price > 0 else 0
                margin_text = _calculate_margin(ebay_price, suggested_price)
                
                formatted_data = {
                    "upc": keywords,
                    "name": result.get("product", {}).get("name", "Unknown"),
                    "brand": result.get("product", {}).get("brand", ""),
                    
                    "ebay_price": round(ebay_price, 2),
                    "amazon_price": round(amazon_price, 2),
                    "walmart_price": round(walmart_price, 2),
                    
                    "demand_level": demand_level,
                    "competition_level": result.get("competitionLevel", {}).get("competitionCode", "UNKNOWN"),
                    "sellers_count": sellers_count,
                    
                    "suggested_price": round(suggested_price, 2),
                    "margin_suggestion": margin_text,
                    
                    "found": True,
                    "timestamp": datetime.now().isoformat()
                }
                
                logger.info(f"✅ Producto encontrado: {formatted_data['name']}")
                
                return {
                    "status": "success",
                    "data": formatted_data
                }
            else:
                logger.warning(f"⚠️ No products found for {keywords}")
                return {
                    "status": "error",
                    "message": "Producto no encontrado en Algopix",
                    "found": False
                }
        else:
            logger.error(f"❌ Algopix error: {data}")
            return {
                "status": "error",
                "message": data.get("statusMessage", "Error de Algopix"),
                "algopix_response": data
            }
    
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout")
        return {
            "status": "error",
            "message": "Timeout al conectar con Algopix"
        }
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Savvy Scanner - Algopix Backend (Versión Simplificada)")
    logger.info(f"   Endpoint: {ALGOPIX_API_URL}")
    logger.info(f"   Parámetro: keywords (auto-detecta tipo)")
    logger.info(f"   Quota: 5,000 lookups/mes")
    app.run(host='0.0.0.0', port=port, debug=False)
