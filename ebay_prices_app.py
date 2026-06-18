"""
SAVVY SCANNER - Backend con ALGOPIX API (ENDPOINT CORRECTO)
Usa la API v3/search correcta de Algopix
Optimizado para 5,000 lookups/mes

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

# Headers para Algopix (CORRECTO)
ALGOPIX_HEADERS = {
    "X-API-KEY": ALGOPIX_API_KEY,
    "X-APP-ID": ALGOPIX_APP_ID,
    "Content-Type": "application/json"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CACHÉ EN MEMORIA (Optimiza lookups)
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
    Búsqueda por UPC usando Algopix API v3/search
    
    Parámetros:
    - upc: Código UPC a buscar (ej: 886227362638)
    - search_term: (Opcional) Búsqueda por texto alternativa
    
    Retorna:
    - Precio eBay actual
    - Precio Amazon actual
    - Precio Walmart actual
    - Estimación de demanda
    - Competencia
    - Margen sugerido
    """
    
    upc = request.args.get('upc', '').strip()
    search_term = request.args.get('search_term', '').strip()
    
    # Validación
    if not upc and not search_term:
        return jsonify({
            "error": "Debe proporcionar UPC o search_term",
            "status": "error"
        }), 400
    
    # ← CACHÉ: Si ya buscamos esto, devolver respuesta cached
    cache_key = f"upc_{upc}" if upc else f"search_{search_term}"
    if cache_key in CACHE:
        logger.info(f"✅ CACHE HIT: {cache_key}")
        return jsonify({
            "data": CACHE[cache_key],
            "cached": True,
            "message": "Datos obtenidos del caché (sin usar lookup)"
        })
    
    logger.info(f"🔍 Buscando en Algopix: {upc or search_term}")
    
    try:
        # Llamar a Algopix API v3/search
        response = _call_algopix_search(upc or search_term)
        
        if response.get("status") == "success":
            # Guardar en caché para futuras búsquedas
            CACHE[cache_key] = response.get("data", {})
            
            # Incrementar contador de lookups
            LOOKUP_COUNT["total"] += 1
            LOOKUP_COUNT["today"] += 1
            
            logger.info(f"✅ Algopix response exitosa. Lookups hoy: {LOOKUP_COUNT['today']}")
            
            return jsonify({
                "data": response.get("data"),
                "status": "success",
                "cached": False,
                "lookups_remaining_today": max(0, int(5000 / 30) - LOOKUP_COUNT["today"])
            })
        else:
            return jsonify(response), 400
            
    except Exception as e:
        logger.error(f"❌ Error en search-upc: {str(e)}")
        return jsonify({
            "error": f"Error al buscar en Algopix: {str(e)}",
            "status": "error"
        }), 500


@app.route('/test-algopix', methods=['GET'])
def test_algopix():
    """
    Test endpoint para verificar conexión con Algopix
    Usa un UPC de prueba conocido
    """
    
    logger.info("🧪 Testing Algopix connection...")
    
    try:
        # UPC de prueba (Nike shoes - product común)
        test_upc = "886227362638"
        
        response = _call_algopix_search(test_upc)
        
        return jsonify({
            "test_upc": test_upc,
            "response": response,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error en test: {str(e)}")
        return jsonify({
            "error": f"Test failed: {str(e)}",
            "status": "error"
        }), 500


@app.route('/quota', methods=['GET'])
def quota():
    """Muestra cuota de lookups usado y restante"""
    
    lookups_used = LOOKUP_COUNT["total"]
    lookups_remaining = 5000 - lookups_used
    percentage_used = (lookups_used / 5000) * 100
    
    return jsonify({
        "plan": "Algopix API - 5,000 lookups/mes",
        "lookups_total": 5000,
        "lookups_used": lookups_used,
        "lookups_remaining": lookups_remaining,
        "percentage_used": f"{percentage_used:.1f}%",
        "lookups_today": LOOKUP_COUNT["today"],
        "reset_date": LOOKUP_COUNT["reset_date"],
        "status": "active" if lookups_remaining > 0 else "exceeded"
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNCIONES AUXILIARES - ALGOPIX
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _call_algopix_search(keywords):
    """
    Llama a Algopix v3/search API
    
    Retorna:
    {
        "status": "success" | "error",
        "data": {
            "upc": "...",
            "name": "...",
            "ebay_price": 45.99,
            "amazon_price": 42.50,
            "walmart_price": 48.00,
            "demand": "HIGH" | "MEDIUM" | "LOW",
            "competition_level": "MEDIUM",
            "sellers_count": 25,
            "suggested_price": 52.00,
            "margin_suggestion": "Vende a $52 (ganancia $12)"
        }
    }
    """
    
    try:
        # Parámetros para Algopix v3/search
        params = {
            "keywords": keywords,
            "idType": "UPC",
            "markets": "AMAZON_US,EBAY_US,WALMART_US"
        }
        
        logger.info(f"📡 Llamando a Algopix v3/search")
        logger.info(f"   Keywords: {keywords}")
        logger.info(f"   Headers: X-API-KEY y X-APP-ID configurados")
        
        # Llamar a Algopix v3/search API (GET request)
        response = requests.get(
            ALGOPIX_API_URL,
            params=params,
            headers=ALGOPIX_HEADERS,
            timeout=10
        )
        
        logger.info(f"📬 Status code: {response.status_code}")
        
        # Parsear respuesta
        data = response.json()
        
        logger.info(f"📦 Respuesta: {json.dumps(data, indent=2)[:500]}...")  # Log primeros 500 chars
        
        if response.status_code == 200 and data.get("status") == "SUCCESS":
            # Extraer datos del producto del resultado
            result = data.get("result", {})
            
            if result:
                # Obtener precios de ofertas
                offers = result.get("offers", {})
                
                # Extraer precios por marketplace
                ebay_price = _extract_price(offers, "EBAY_US")
                amazon_price = _extract_price(offers, "AMAZON_US")
                walmart_price = _extract_price(offers, "WALMART_US")
                
                # Obtener demanda
                demand_level = result.get("demandLevel", {}).get("demandCode", "UNKNOWN")
                
                # Contar sellers
                sellers_count = result.get("sellers", {}).get("sellerCount", 0)
                
                # Calcular margen sugerido (usar eBay como base)
                suggested_price = ebay_price * 1.15 if ebay_price > 0 else 0  # 15% markup
                margin_text = _calculate_margin(ebay_price, suggested_price)
                
                # Formatear respuesta
                formatted_data = {
                    "upc": keywords,
                    "name": result.get("product", {}).get("name", "Unknown"),
                    "brand": result.get("product", {}).get("brand", ""),
                    "category": result.get("product", {}).get("category", ""),
                    
                    # PRECIOS (marketplace específicos)
                    "ebay_price": ebay_price,
                    "amazon_price": amazon_price,
                    "walmart_price": walmart_price,
                    
                    # DEMANDA Y COMPETENCIA
                    "demand_level": _parse_demand_level(demand_level),
                    "competition_level": result.get("competitionLevel", {}).get("competitionCode", "UNKNOWN"),
                    "sellers_count": sellers_count,
                    
                    # MARGEN SUGERIDO
                    "suggested_price": round(suggested_price, 2),
                    "margin_suggestion": margin_text,
                    "margin": margin_text,
                    
                    # INFORMACIÓN ADICIONAL
                    "found": True,
                    "timestamp": datetime.now().isoformat()
                }
                
                logger.info(f"✅ Producto encontrado: {formatted_data['name']}")
                
                return {
                    "status": "success",
                    "data": formatted_data
                }
            else:
                logger.warning(f"⚠️ Algopix: No products found for {keywords}")
                return {
                    "status": "error",
                    "message": "Producto no encontrado en Algopix",
                    "found": False
                }
        else:
            logger.error(f"❌ Algopix error: {data}")
            return {
                "status": "error",
                "message": data.get("statusMessage", "Error desconocido de Algopix"),
                "algopix_response": data
            }
    
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout en Algopix API")
        return {
            "status": "error",
            "message": "Timeout al conectar con Algopix"
        }
    
    except Exception as e:
        logger.error(f"❌ Error en _call_algopix_search: {str(e)}")
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }


def _extract_price(offers, marketplace):
    """Extrae el precio de un marketplace específico"""
    try:
        market_offers = offers.get(marketplace, {})
        if market_offers and len(market_offers) > 0:
            return float(market_offers[0].get("price", 0))
        return 0
    except:
        return 0


def _parse_demand_level(code):
    """Convierte código de demanda a texto legible"""
    demand_map = {
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW"
    }
    return demand_map.get(code, code)


def _calculate_margin(ebay_price, suggested_price):
    """Calcula el margen de ganancia sugerido"""
    
    if not ebay_price or ebay_price == 0:
        return "No disponible"
    
    # Costos típicos en eBay (~20% de fees + impuestos)
    ebay_fees = ebay_price * 0.20
    
    if suggested_price > ebay_price:
        margin = suggested_price - ebay_price - ebay_fees
        return f"Vende a ${suggested_price:.2f} (ganancia ${margin:.2f})"
    else:
        return f"Precio eBay: ${ebay_price:.2f}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EJECUCIÓN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Iniciando Savvy Scanner Backend con Algopix API v3/search")
    logger.info(f"   Port: {port}")
    logger.info(f"   Algopix App ID: {ALGOPIX_APP_ID[:10]}...")
    logger.info(f"   Endpoint: https://api.algopix.ai/v3/search")
    logger.info(f"   Quota: 5,000 lookups/mes")
    app.run(host='0.0.0.0', port=port, debug=False)
