"""
Direct Market Corrections Module
===============================

Módulo que proporciona correcciones directas de mercado que se pueden 
integrar fácilmente en cualquier parte del sistema sin modificar
archivos existentes extensivamente.
"""

import logging
from typing import Dict, List, Any
from src.api.utils.market_utils import convert_price_to_market_currency, translate_basic_text

logger = logging.getLogger(__name__)

def apply_direct_market_corrections(
    recommendations: List[Dict[str, Any]], 
    market_id: str = "US",
    user_query: str = ""
) -> List[Dict[str, Any]]:
    """
    🔧 CORRECCIÓN CRÍTICA DIRECTA: Aplica correcciones de mercado de forma sencilla.
    
    Esta función puede ser llamada desde cualquier parte del sistema para:
    1. Corregir precios COP marcados incorrectamente como USD
    2. Traducir contenido en español para mercado US
    3. Validar estructura de datos
    
    Args:
        recommendations: Lista de recomendaciones
        market_id: ID del mercado (US, ES, MX, etc.)
        user_query: Query del usuario para contexto
        
    Returns:
        Lista de recomendaciones corregidas
    """
    if not recommendations:
        return []
    
    corrected_recommendations = []
    corrections_applied = 0
    
    logger.info(f"🔧 Aplicando correcciones directas para mercado {market_id} a {len(recommendations)} recomendaciones")
    
    for i, rec in enumerate(recommendations):
        try:
            corrected_rec = rec.copy()
            rec_corrections = []
            
            # CORRECCIÓN 1: Fix de precios COP marcados como USD
            if market_id == "US" and corrected_rec.get("currency") == "USD":
                price = corrected_rec.get("price", 0.0)
                
                # Si el precio es > 1000 USD, probablemente es COP
                if price > 1000:
                    conversion_result = convert_price_to_market_currency(
                        price=price,
                        from_currency="COP",
                        to_market_id="US"
                    )
                    
                    if conversion_result["conversion_applied"]:
                        corrected_rec["price"] = conversion_result["price"]
                        corrected_rec["original_price_cop"] = price
                        corrected_rec["price_corrected"] = True
                        rec_corrections.append("price_conversion")
                        logger.info(f"   ✅ Precio corregido #{i}: {price} COP -> ${conversion_result['price']} USD")
            
            # CORRECCIÓN 2: Traducción para mercado US
            if market_id == "US":
                # Traducir título si contiene palabras en español
                title = corrected_rec.get("title", "")
                if title and any(word in title.lower() for word in ["vestido", "cinturon", "cinturón", "alas", "hojas", "dorado"]):
                    translation_result = translate_basic_text(title, "US")
                    if translation_result["translation_applied"]:
                        corrected_rec["title"] = translation_result["text"]
                        corrected_rec["original_title"] = title
                        corrected_rec["title_translated"] = True
                        rec_corrections.append("title_translation")
                        logger.info(f"   ✅ Título traducido #{i}: '{title}' -> '{translation_result['text']}'")
                
                # Traducir descripción si es muy larga en español
                description = corrected_rec.get("description", "")
                if description and len(description) > 50 and any(word in description.lower() for word in ["confeccionado", "tela", "diseño", "ideal para"]):
                    translation_result = translate_basic_text(description, "US")
                    if translation_result["translation_applied"]:
                        # Truncar si es muy larga después de traducir
                        translated_desc = translation_result["text"]
                        if len(translated_desc) > 200:
                            translated_desc = translated_desc[:197] + "..."
                        
                        corrected_rec["description"] = translated_desc
                        corrected_rec["original_description"] = description
                        corrected_rec["description_translated"] = True
                        rec_corrections.append("description_translation")
                        logger.info(f"   ✅ Descripción traducida #{i}")
            
            # CORRECCIÓN 3: Mejorar razón si es genérica
            if user_query and corrected_rec.get("reason") == "Based on your preferences and market analysis":
                enhanced_reason = f"Great match for '{user_query}' with relevant features and good value"
                corrected_rec["reason"] = enhanced_reason
                rec_corrections.append("enhanced_reason")
            
            # CORRECCIÓN 4: Asegurar campos requeridos
            required_fields = {
                "id": corrected_rec.get("id", f"product_{i}"),
                "title": corrected_rec.get("title", "Product"),
                "description": corrected_rec.get("description", ""),
                "price": float(corrected_rec.get("price", 0.0)),
                "currency": corrected_rec.get("currency", "USD"),
                "score": float(corrected_rec.get("score", 0.5)),
                "market_adapted": True,
                "viability_score": float(corrected_rec.get("viability_score", 0.8)),
                "source": corrected_rec.get("source", "corrected")
            }
            
            for field, value in required_fields.items():
                if field not in corrected_rec or corrected_rec[field] is None:
                    corrected_rec[field] = value
            
            # Añadir metadata de correcciones
            if rec_corrections:
                corrected_rec["corrections_applied"] = rec_corrections
                corrected_rec["correction_timestamp"] = int(time.time()) if 'time' in globals() else 0
                corrections_applied += 1
            
            corrected_recommendations.append(corrected_rec)
            
        except Exception as e:
            logger.error(f"❌ Error corrigiendo recomendación #{i}: {e}")
            corrected_recommendations.append(rec)  # Usar original si falla
    
    logger.info(f"✅ Correcciones completadas: {corrections_applied}/{len(recommendations)} productos corregidos")
    
    return corrected_recommendations

def quick_price_fix(recommendations: List[Dict[str, Any]], market_id: str = "US") -> List[Dict[str, Any]]:
    """
    Corrección rápida solo de precios para integración inmediata.
    
    Args:
        recommendations: Lista de recomendaciones
        market_id: ID del mercado
        
    Returns:
        Lista con precios corregidos
    """
    if market_id != "US":
        return recommendations
    
    fixed_recommendations = []
    
    for rec in recommendations:
        fixed_rec = rec.copy()
        price = fixed_rec.get("price", 0.0)
        
        # Fix crítico: convertir precios COP a USD
        if price > 1000 and fixed_rec.get("currency") == "USD":
            # Conversión simple: dividir por 4000 (tasa aproximada COP->USD)
            fixed_price = round(price / 4000, 2)
            fixed_rec["price"] = fixed_price
            fixed_rec["original_price_cop"] = price
            fixed_rec["price_fixed"] = True
            logger.info(f"Quick price fix: {price} -> ${fixed_price}")
        
        fixed_recommendations.append(fixed_rec)
    
    return fixed_recommendations

def quick_translation_fix(recommendations: List[Dict[str, Any]], market_id: str = "US") -> List[Dict[str, Any]]:
    """
    Corrección rápida solo de traducción para integración inmediata.
    
    Args:
        recommendations: Lista de recomendaciones
        market_id: ID del mercado
        
    Returns:
        Lista con títulos traducidos
    """
    if market_id != "US":
        return recommendations
    
    # Traducciones básicas más comunes
    quick_translations = {
        "Vestido de Novia": "Wedding Dress",
        "Alas de Novia": "Bridal Wings", 
        "Cinturon": "Belt",
        "Cinturón": "Belt",
        "Hojas Dorado": "Golden Leaves",
        "Azul Oscuro": "Dark Blue",
        "Un Hombro": "One Shoulder",
        "Largo": "Long",
        "Box": "Box",
        "Indispensables": "Essentials"
    }
    
    fixed_recommendations = []
    
    for rec in recommendations:
        fixed_rec = rec.copy()
        title = fixed_rec.get("title", "")
        
        # Aplicar traducciones básicas
        for spanish, english in quick_translations.items():
            if spanish in title:
                title = title.replace(spanish, english)
                fixed_rec["title"] = title
                fixed_rec["quick_translated"] = True
        
        fixed_recommendations.append(fixed_rec)
    
    return fixed_recommendations

# Función combinada para máxima simplicidad
def apply_critical_fixes_simple(recommendations: List[Dict[str, Any]], market_id: str = "US") -> List[Dict[str, Any]]:
    """
    Aplica las correcciones más críticas de manera simple y rápida.
    
    Args:
        recommendations: Lista de recomendaciones
        market_id: ID del mercado
        
    Returns:
        Lista corregida
    """
    if not recommendations:
        return []
    
    # Aplicar correcciones en secuencia
    fixed_recs = quick_price_fix(recommendations, market_id)
    fixed_recs = quick_translation_fix(fixed_recs, market_id)
    
    return fixed_recs
