"""
SAVVY SCANNER - Backend con ALGOPIX API
Reemplaza la búsqueda de eBay Catalog API con Algopix Product Analysis API
Optimizado para 5,000 lookups/mes

Instalación de dependencias:
pip install flask requests python-dotenv
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
ALGOPIX_API_URL = "https://api.algopix.com/v1"

# Headers para Algopix
ALGOPIX_HEADERS = {
    "app-id": ALGOPIX_APP_ID,
    "app-key": ALGOPIX_API_KEY,
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
    Búsqueda por UPC usando Algopix API
    
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
        # Llamar a Algopix Product Analysis API
        response = _call_algopix_product_analysis(upc, search_term)
        
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
        
        response = _call_algopix_product_analysis(test_upc, None)
        
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

def _call_algopix_product_analysis(upc, search_term):
    """
    Llama a Algopix Product Analysis API
    
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
        # Construir parámetros para Algopix
        payload = {
            "marketplaces": ["amazon_us", "ebay_us", "walmart_us"],
            "country_id": "US",
            "currency": "USD"
        }
        
        # Usar UPC o search_term
        if upc:
            payload["gtin"] = upc
        else:
            payload["search_term"] = search_term
        
        # Llamar a Algopix Product Analysis API
        url = f"{ALGOPIX_API_URL}/products/search"
        
        logger.info(f"📡 Llamando a Algopix: {url}")
        logger.info(f"   Payload: {payload}")
        
        response = requests.post(
            url,
            json=payload,
            headers=ALGOPIX_HEADERS,
            timeout=10
        )
        
        logger.info(f"📬 Status code: {response.status_code}")
        
        # Parsear respuesta
        data = response.json()
        
        if response.status_code == 200 and data.get("status") == "success":
            # Extraer datos del producto
            products = data.get("data", [])
            
            if products:
                product = products[0]  # Primer resultado
                
                # Formatear respuesta
                formatted_data = {
                    "upc": upc or search_term,
                    "name": product.get("product_name", "Unknown"),
                    "brand": product.get("brand", ""),
                    "category": product.get("category", ""),
                    "image_url": product.get("image_url", ""),
                    
                    # PRECIOS (marketplace específicos)
                    "ebay_price": product.get("ebay_price", 0),
                    "amazon_price": product.get("amazon_price", 0),
                    "walmart_price": product.get("walmart_price", 0),
                    
                    # DEMANDA Y COMPETENCIA
                    "demand_level": product.get("demand_level", "UNKNOWN"),
                    "competition_level": product.get("competition_level", "UNKNOWN"),
                    "sellers_count": product.get("sellers_count", 0),
                    "sales_rank": product.get("sales_rank", ""),
                    
                    # MARGEN SUGERIDO
                    "suggested_price": product.get("suggested_price", 0),
                    "margin": _calculate_margin(
                        product.get("ebay_price", 0),
                        product.get("suggested_price", 0)
                    ),
                    
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
                logger.warning(f"⚠️ Algopix: No products found for {upc or search_term}")
                return {
                    "status": "error",
                    "message": "Producto no encontrado en Algopix",
                    "found": False
                }
        else:
            logger.error(f"❌ Algopix error: {data}")
            return {
                "status": "error",
                "message": data.get("message", "Error desconocido de Algopix"),
                "algopix_response": data
            }
    
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout en Algopix API")
        return {
            "status": "error",
            "message": "Timeout al conectar con Algopix"
        }
    
    except Exception as e:
        logger.error(f"❌ Error en _call_algopix: {str(e)}")
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }


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
    logger.info(f"🚀 Iniciando Savvy Scanner Backend con Algopix API")
    logger.info(f"   Port: {port}")
    logger.info(f"   Algopix App ID: {ALGOPIX_APP_ID[:10]}...")
    logger.info(f"   Quota: 5,000 lookups/mes")
    app.run(host='0.0.0.0', port=port, debug=False)
