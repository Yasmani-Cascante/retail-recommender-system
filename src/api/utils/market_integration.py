"""
Market Corrections Integration
=============================

Integración simple de correcciones de mercado que se puede usar 
en cualquier parte del sistema sin modificaciones complejas.

USAGE EN ROUTER MCP:
```python
from src.api.utils.market_integration import integrate_market_corrections

# En la función process_conversation, después de obtener recomendaciones:
corrected_recommendations = integrate_market_corrections(
    recommendations=safe_recommendations,
    market_id=conversation.market_id,
    user_query=conversation.query
)
```
"""

import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

def integrate_market_corrections(
    recommendations: List[Dict[str, Any]],
    market_id: str = "US", 
    user_query: str = "",
    enable_logging: bool = True
) -> List[Dict[str, Any]]:
    """
    🔧 INTEGRACIÓN PRINCIPAL: Aplica todas las correcciones críticas de mercado.
    
    Esta función es la que debe llamarse desde el router MCP para aplicar
    todas las correcciones identificadas en el análisis.
    
    Args:
        recommendations: Lista de recomendaciones del sistema
        market_id: ID del mercado (US, ES, MX, etc.)
        user_query: Query del usuario para contexto
        enable_logging: Si habilitar logging detallado
        
    Returns:
        Lista de recomendaciones corregidas
    """
    start_time = time.time()
    
    try:
        if not recommendations:
            if enable_logging:
                logger.info("🔧 No hay recomendaciones para corregir")
            return []
        
        if enable_logging:
            logger.info(f"🔧 INICIANDO CORRECCIONES CRÍTICAS")
            logger.info(f"   📊 Recomendaciones: {len(recommendations)}")
            logger.info(f"   🌍 Mercado: {market_id}")
            logger.info(f"   🔍 Query: '{user_query}'")
        
        # Importar funciones de corrección
        from src.api.utils.direct_corrections import apply_critical_fixes_simple
        
        # Aplicar correcciones críticas
        corrected_recommendations = apply_critical_fixes_simple(
            recommendations=recommendations,
            market_id=market_id
        )
        
        # Aplicar mejoras contextuales si hay query del usuario
        if user_query:
            corrected_recommendations = enhance_with_user_context(
                recommendations=corrected_recommendations,
                user_query=user_query,
                market_id=market_id
            )
        
        # Validar resultados
        validated_recommendations = validate_final_recommendations(
            recommendations=corrected_recommendations,
            market_id=market_id
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        if enable_logging:
            corrections_count = count_corrections_applied(validated_recommendations)
            logger.info(f"✅ CORRECCIONES COMPLETADAS en {processing_time:.2f}ms")
            logger.info(f"   📈 Productos procesados: {len(validated_recommendations)}")
            logger.info(f"   🔧 Correcciones aplicadas: {corrections_count}")
        
        return validated_recommendations
        
    except Exception as e:
        logger.error(f"❌ Error en integrate_market_corrections: {e}")
        return recommendations  # Retornar originales si falla todo

def enhance_with_user_context(
    recommendations: List[Dict[str, Any]],
    user_query: str,
    market_id: str
) -> List[Dict[str, Any]]:
    """
    Mejora las recomendaciones con contexto del usuario.
    
    Args:
        recommendations: Recomendaciones a mejorar
        user_query: Query del usuario
        market_id: ID del mercado
        
    Returns:
        Recomendaciones mejoradas
    """
    enhanced_recommendations = []
    
    for rec in recommendations:
        enhanced_rec = rec.copy()
        
        # Mejorar razón de recomendación con contexto
        current_reason = enhanced_rec.get("reason", "")
        if not current_reason or current_reason == "Based on your preferences and market analysis":
            enhanced_reason = generate_contextual_reason(enhanced_rec, user_query, market_id)
            if enhanced_reason:
                enhanced_rec["reason"] = enhanced_reason
                enhanced_rec["reason_enhanced"] = True
        
        # Añadir score de relevancia basado en query
        relevance_score = calculate_query_relevance(enhanced_rec, user_query)
        enhanced_rec["query_relevance_score"] = relevance_score
        
        enhanced_recommendations.append(enhanced_rec)
    
    return enhanced_recommendations

def generate_contextual_reason(rec: Dict[str, Any], user_query: str, market_id: str) -> str:
    """
    Genera una razón contextual para la recomendación.
    
    Args:
        rec: Recomendación individual
        user_query: Query del usuario
        market_id: ID del mercado
        
    Returns:
        Razón contextual mejorada
    """
    try:
        query_lower = user_query.lower()
        title_lower = rec.get("title", "").lower()
        price = rec.get("price", 0.0)
        
        # Detectar tipo de query y generar razón apropiada
        if any(word in query_lower for word in ["under", "$", "budget", "cheap", "affordable"]):
            if price > 0:
                currency_symbol = "$" if market_id == "US" else "$"
                return f"Great value option at {currency_symbol}{price:.2f} that fits your budget"
        
        elif any(word in query_lower for word in ["best", "top", "recommend", "good", "quality"]):
            return f"Highly recommended {rec.get('category', 'product')} based on your preferences"
        
        elif any(word in query_lower for word in ["similar", "like", "same", "comparable"]):
            return f"Similar style and features to what you're looking for"
        
        elif any(word in query_lower for word in ["wedding", "bride", "bridal"]):
            return f"Perfect for your special day with elegant design"
        
        elif any(word in query_lower for word in ["party", "celebration", "event"]):
            return f"Ideal for special occasions and celebrations"
        
        # Query específica - buscar coincidencias
        query_words = set(query_lower.split())
        title_words = set(title_lower.split())
        common_words = query_words.intersection(title_words)
        
        if common_words:
            return f"Matches your search with relevant features for '{user_query}'"
        
        # Razón por defecto mejorada
        return f"Recommended based on your search for '{user_query}'"
        
    except Exception as e:
        logger.error(f"Error generando razón contextual: {e}")
        return "Based on your preferences and market analysis"

def calculate_query_relevance(rec: Dict[str, Any], user_query: str) -> float:
    """
    Calcula score de relevancia entre recomendación y query del usuario.
    
    Args:
        rec: Recomendación individual
        user_query: Query del usuario
        
    Returns:
        Score de relevancia (0.0 - 1.0)
    """
    try:
        if not user_query:
            return 0.5
        
        query_words = set(user_query.lower().split())
        title_words = set(rec.get("title", "").lower().split())
        desc_words = set(rec.get("description", "").lower().split())
        
        # Calcular intersecciones
        title_matches = len(query_words.intersection(title_words))
        desc_matches = len(query_words.intersection(desc_words))
        
        # Score ponderado
        title_score = title_matches / len(query_words) if query_words else 0
        desc_score = desc_matches / len(query_words) if query_words else 0
        
        # Peso mayor al título que a la descripción
        final_score = (title_score * 0.7) + (desc_score * 0.3)
        
        return min(1.0, final_score)
        
    except Exception as e:
        logger.error(f"Error calculando relevancia: {e}")
        return 0.5

def validate_final_recommendations(
    recommendations: List[Dict[str, Any]],
    market_id: str
) -> List[Dict[str, Any]]:
    """
    Valida y asegura que las recomendaciones finales tengan estructura correcta.
    
    Args:
        recommendations: Recomendaciones a validar
        market_id: ID del mercado
        
    Returns:
        Recomendaciones validadas
    """
    validated_recommendations = []
    
    for i, rec in enumerate(recommendations):
        try:
            validated_rec = rec.copy()
            
            # Campos obligatorios con valores por defecto
            required_fields = {
                "id": str(validated_rec.get("id", f"product_{i}")),
                "title": str(validated_rec.get("title", "Product")),
                "description": str(validated_rec.get("description", "")),
                "price": float(validated_rec.get("price", 0.0)),
                "currency": "USD" if market_id == "US" else validated_rec.get("currency", "USD"),
                "score": float(validated_rec.get("score", 0.5)),
                "reason": str(validated_rec.get("reason", "Based on your preferences")),
                "images": list(validated_rec.get("images", [])),
                "market_adapted": True,
                "viability_score": float(validated_rec.get("viability_score", 0.8)),
                "source": str(validated_rec.get("source", "validated"))
            }
            
            # Aplicar campos requeridos
            for field, default_value in required_fields.items():
                if field not in validated_rec or validated_rec[field] is None:
                    validated_rec[field] = default_value
            
            # Validaciones específicas
            if validated_rec["price"] < 0:
                validated_rec["price"] = 0.0
            
            if not isinstance(validated_rec["score"], (int, float)) or validated_rec["score"] < 0:
                validated_rec["score"] = 0.5
            
            if validated_rec["score"] > 1.0:
                validated_rec["score"] = 1.0
            
            validated_recommendations.append(validated_rec)
            
        except Exception as e:
            logger.error(f"Error validando recomendación {i}: {e}")
            # Crear recomendación de emergencia
            emergency_rec = {
                "id": f"emergency_{i}",
                "title": "Product",
                "description": "Product information unavailable",
                "price": 0.0,
                "currency": "USD",
                "score": 0.1,
                "reason": "Error in processing",
                "images": [],
                "market_adapted": False,
                "viability_score": 0.1,
                "source": "emergency_fallback"
            }
            validated_recommendations.append(emergency_rec)
    
    return validated_recommendations

def count_corrections_applied(recommendations: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Cuenta las correcciones aplicadas en las recomendaciones.
    
    Args:
        recommendations: Recomendaciones procesadas
        
    Returns:
        Diccionario con conteos de correcciones
    """
    counts = {
        "price_corrections": 0,
        "title_translations": 0,
        "description_translations": 0,
        "reason_enhancements": 0,
        "validations": 0
    }
    
    try:
        for rec in recommendations:
            if rec.get("price_fixed") or rec.get("price_corrected"):
                counts["price_corrections"] += 1
            
            if rec.get("quick_translated") or rec.get("title_translated"):
                counts["title_translations"] += 1
            
            if rec.get("description_translated"):
                counts["description_translations"] += 1
            
            if rec.get("reason_enhanced"):
                counts["reason_enhancements"] += 1
            
            if rec.get("market_adapted"):
                counts["validations"] += 1
        
    except Exception as e:
        logger.error(f"Error contando correcciones: {e}")
    
    return counts

# Función de conveniencia para usar en una sola línea
def fix_recommendations(recommendations: List[Dict], market_id: str = "US", query: str = "") -> List[Dict]:
    """
    Función de conveniencia para aplicar todas las correcciones en una línea.
    
    Usage:
    ```python
    fixed_recs = fix_recommendations(recommendations, "US", user_query)
    ```
    """
    return integrate_market_corrections(recommendations, market_id, query, enable_logging=False)
