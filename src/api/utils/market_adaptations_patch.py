"""
Critical Market Adaptations Patch for MCP Router
===============================================

Este parche integra las correcciones críticas de conversión de moneda 
y traducción básica en el router MCP existente.

CORRECCIONES APLICADAS:
1. Conversión automática de precios COP -> USD para mercado US
2. Traducción básica de términos en español -> inglés  
3. Validación de estructura de datos de recomendaciones
4. Logging mejorado para debugging

APLICAR ESTE PARCHE:
```python
from src.api.utils.market_adaptations_patch import apply_market_adaptations
# Aplicar en process_conversation antes de retornar respuesta
adapted_recommendations = apply_market_adaptations(
    recommendations=safe_recommendations,
    market_id=conversation.market_id,
    user_query=conversation.query
)
```
"""

import logging
import time
from typing import Dict, List, Any, Optional
from src.api.utils.market_processor import process_recommendations_for_market
from src.api.utils.market_utils import convert_price_to_market_currency, translate_basic_text

logger = logging.getLogger(__name__)

def apply_market_adaptations(
    recommendations: List[Dict[str, Any]],
    market_id: str,
    user_query: str = "",
    source: str = "mcp_router"
) -> List[Dict[str, Any]]:
    """
    🔧 CORRECCIÓN CRÍTICA: Aplica adaptaciones de mercado a recomendaciones.
    
    Esta función resuelve:
    - Conversión incorrecta de moneda (COP marcado como USD)
    - Contenido en español para mercado US
    - Validación de estructura de datos
    
    Args:
        recommendations: Lista de recomendaciones originales
        market_id: ID del mercado (US, ES, MX, etc.)
        user_query: Query del usuario para contexto
        source: Fuente de las recomendaciones
        
    Returns:
        Lista de recomendaciones adaptadas y corregidas
    """
    start_time = time.time()
    
    try:
        logger.info(f"🔧 Aplicando adaptaciones críticas para mercado {market_id}")
        logger.info(f"   - Recomendaciones a procesar: {len(recommendations)}")
        logger.info(f"   - Query del usuario: '{user_query}'")
        
        if not recommendations:
            logger.warning("No hay recomendaciones para procesar")
            return []
        
        # Aplicar procesamiento de mercado
        adapted_recs = process_recommendations_for_market(
            recommendations=recommendations,
            market_id=market_id,
            source=source
        )
        
        # Aplicar correcciones específicas para cada recomendación
        final_recommendations = []
        adaptations_applied = []
        
        for i, rec in enumerate(adapted_recs):
            try:
                corrected_rec = apply_critical_fixes(rec, market_id, user_query)
                final_recommendations.append(corrected_rec)
                
                # Tracking de adaptaciones aplicadas
                if corrected_rec.get("market_adapted"):
                    if corrected_rec.get("exchange_rate"):
                        adaptations_applied.append(f"price_conversion_{i}")
                    if corrected_rec.get("original_title"):
                        adaptations_applied.append(f"title_translation_{i}")
                    if corrected_rec.get("original_description"):
                        adaptations_applied.append(f"desc_translation_{i}")
                
            except Exception as e:
                logger.error(f"Error aplicando corrección a recomendación {i}: {e}")
                final_recommendations.append(rec)  # Usar original si falla
        
        processing_time = (time.time() - start_time) * 1000
        
        # Log de resultados
        logger.info(f"✅ Adaptaciones completadas en {processing_time:.2f}ms:")
        logger.info(f"   - Recomendaciones procesadas: {len(final_recommendations)}")
        logger.info(f"   - Adaptaciones aplicadas: {adaptations_applied}")
        logger.info(f"   - Mercado objetivo: {market_id}")
        
        return final_recommendations
        
    except Exception as e:
        logger.error(f"❌ Error crítico en apply_market_adaptations: {e}")
        return recommendations  # Retornar originales en caso de error fatal

def apply_critical_fixes(
    recommendation: Dict[str, Any],
    market_id: str,
    user_query: str = ""
) -> Dict[str, Any]:
    """
    Aplica correcciones críticas específicas a una recomendación individual.
    
    Args:
        recommendation: Recomendación individual
        market_id: ID del mercado
        user_query: Query del usuario
        
    Returns:
        Recomendación corregida
    """
    try:
        fixed_rec = recommendation.copy()
        fixes_applied = []
        
        # 🔧 CORRECCIÓN 1: Fix de conversión de moneda incorrecta
        if market_id == "US" and fixed_rec.get("currency") == "USD":
            original_price = fixed_rec.get("price", 0.0)
            
            # Detectar si el precio está realmente en COP (precios muy altos = COP)
            if original_price > 1000:  # Asumimos que precios >1000 USD son realmente COP
                logger.info(f"🔧 Corrigiendo precio COP marcado como USD: {original_price}")
                
                price_conversion = convert_price_to_market_currency(
                    price=original_price,
                    from_currency="COP",
                    to_market_id="US"
                )
                
                if price_conversion["conversion_applied"]:
                    fixed_rec.update({
                        "price": price_conversion["price"],
                        "currency": price_conversion["currency"],
                        "original_price_cop": original_price,
                        "exchange_rate": price_conversion.get("exchange_rate"),
                        "price_conversion_applied": True
                    })
                    fixes_applied.append("price_conversion")
                    logger.info(f"   ✅ Precio corregido: {original_price} COP -> {price_conversion['price']} USD")
        
        # 🔧 CORRECCIÓN 2: Traducción para mercado US
        if market_id == "US":
            # Traducir título si está en español
            title = fixed_rec.get("title", "")
            if title and detect_spanish_content(title):
                title_translation = translate_basic_text(title, "US")
                if title_translation["translation_applied"]:
                    fixed_rec.update({
                        "title": title_translation["text"],
                        "original_title": title,
                        "title_translation_applied": True
                    })
                    fixes_applied.append("title_translation")
                    logger.info(f"   ✅ Título traducido: '{title}' -> '{title_translation['text']}'")
            
            # Traducir descripción si está en español
            description = fixed_rec.get("description", "")
            if description and detect_spanish_content(description):
                desc_translation = translate_basic_text(description, "US")
                if desc_translation["translation_applied"]:
                    # Truncar descripción si es muy larga después de traducir
                    translated_desc = desc_translation["text"]
                    if len(translated_desc) > 300:
                        translated_desc = translated_desc[:297] + "..."
                    
                    fixed_rec.update({
                        "description": translated_desc,
                        "original_description": description,
                        "description_translation_applied": True
                    })
                    fixes_applied.append("description_translation")
                    logger.info(f"   ✅ Descripción traducida y limpiada")
        
        # 🔧 CORRECCIÓN 3: Mejorar razón de recomendación con contexto
        if user_query and len(user_query.strip()) > 0:
            enhanced_reason = generate_contextual_reason(fixed_rec, user_query, market_id)
            if enhanced_reason:
                fixed_rec["reason"] = enhanced_reason
                fixes_applied.append("contextual_reason")
        
        # 🔧 CORRECCIÓN 4: Validar y completar campos faltantes
        validate_and_complete_fields(fixed_rec, market_id)
        
        # Añadir metadata de correcciones
        fixed_rec.update({
            "critical_fixes_applied": fixes_applied,
            "fixes_timestamp": time.time(),
            "market_correction_version": "1.0"
        })
        
        return fixed_rec
        
    except Exception as e:
        logger.error(f"Error en apply_critical_fixes: {e}")
        return recommendation

def detect_spanish_content(text: str) -> bool:
    """
    Detecta si un texto está en español usando indicadores simples.
    
    Args:
        text: Texto a analizar
        
    Returns:
        True si detecta contenido en español
    """
    if not text:
        return False
    
    # Indicadores de español
    spanish_indicators = [
        "ñ", "Ñ",  # Eñe
        " de ", " del ", " la ", " el ", " los ", " las ",  # Artículos
        " para ", " con ", " sin ", " por ",  # Preposiciones
        " años ", " año ", " días ", " día ",  # Tiempo
        "ción", "sión",  # Terminaciones
        "Vestido", "Cinturon", "Cinturón", "Alas", "Hojas", "Dorado"  # Palabras específicas
    ]
    
    text_lower = text.lower()
    spanish_count = sum(1 for indicator in spanish_indicators if indicator.lower() in text_lower)
    
    return spanish_count >= 2  # Al menos 2 indicadores

def generate_contextual_reason(
    recommendation: Dict[str, Any],
    user_query: str,
    market_id: str
) -> Optional[str]:
    """
    Genera una razón contextual para la recomendación basada en la query del usuario.
    
    Args:
        recommendation: Recomendación
        user_query: Query del usuario
        market_id: ID del mercado
        
    Returns:
        Razón contextual o None
    """
    try:
        title = recommendation.get("title", "").lower()
        query_lower = user_query.lower()
        price = recommendation.get("price", 0.0)
        
        # Generar razón basada en el contexto
        if "under" in query_lower and any(word in query_lower for word in ["$", "dollar", "budget", "price"]):
            # Query sobre presupuesto
            if price > 0:
                return f"Great value option at ${price:.2f} that fits your budget requirements"
        
        elif any(word in query_lower for word in ["best", "top", "recommend", "good"]):
            # Query sobre calidad
            return f"Highly recommended {recommendation.get('category', 'product')} based on your preferences"
        
        elif any(word in query_lower for word in ["similar", "like", "same"]):
            # Query sobre similitud
            return f"Similar style and features to what you're looking for"
        
        elif len(query_lower) > 10:  # Query específica
            # Encontrar palabras en común entre query y título
            query_words = set(query_lower.split())
            title_words = set(title.split())
            common_words = query_words.intersection(title_words)
            
            if common_words:
                return f"Matches your search for '{user_query}' with relevant features"
        
        # Razón por defecto mejorada
        return f"Based on your preferences and market analysis"
        
    except Exception as e:
        logger.error(f"Error generando razón contextual: {e}")
        return None

def validate_and_complete_fields(recommendation: Dict[str, Any], market_id: str) -> None:
    """
    Valida y completa campos faltantes en una recomendación.
    
    Args:
        recommendation: Recomendación a validar
        market_id: ID del mercado
    """
    try:
        # Campos requeridos con valores por defecto
        defaults = {
            "id": "unknown",
            "title": "Product",
            "description": "",
            "price": 0.0,
            "currency": "USD" if market_id == "US" else "USD",
            "score": 0.5,
            "reason": "Based on your preferences",
            "images": [],
            "market_adapted": True,
            "viability_score": 0.8,
            "source": "validated"
        }
        
        for field, default_value in defaults.items():
            if field not in recommendation or recommendation[field] is None:
                recommendation[field] = default_value
        
        # Validaciones específicas
        if not isinstance(recommendation["price"], (int, float)):
            recommendation["price"] = 0.0
        
        if not isinstance(recommendation["images"], list):
            recommendation["images"] = []
        
        if not isinstance(recommendation["score"], (int, float)):
            recommendation["score"] = 0.5
        
    except Exception as e:
        logger.error(f"Error validando campos: {e}")

def get_adaptation_summary(recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Genera un resumen de las adaptaciones aplicadas.
    
    Args:
        recommendations: Lista de recomendaciones procesadas
        
    Returns:
        Resumen de adaptaciones
    """
    try:
        summary = {
            "total_recommendations": len(recommendations),
            "price_conversions": 0,
            "title_translations": 0,
            "description_translations": 0,
            "contextual_reasons": 0,
            "market_adapted": 0
        }
        
        for rec in recommendations:
            if rec.get("price_conversion_applied"):
                summary["price_conversions"] += 1
            if rec.get("title_translation_applied"):
                summary["title_translations"] += 1
            if rec.get("description_translation_applied"):
                summary["description_translations"] += 1
            if rec.get("market_adapted"):
                summary["market_adapted"] += 1
            if "contextual_reason" in rec.get("critical_fixes_applied", []):
                summary["contextual_reasons"] += 1
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generando resumen: {e}")
        return {"error": str(e)}
