# src/api/core/product_data_validator.py - NUEVO ARCHIVO
"""
🔧 VALIDADOR DE DATOS DE PRODUCTOS
Utilidad para normalizar y validar datos de productos desde diferentes fuentes.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProductDataValidator:
    """
    Validador y normalizador de datos de productos para evitar errores de None/null.
    """
    
    @staticmethod
    def validate_and_normalize_product(product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida y normaliza un producto individual, convirtiendo valores None a tipos apropiados.
        
        Args:
            product: Diccionario con datos del producto
            
        Returns:
            Diccionario con producto normalizado
        """
        normalized = {}
        
        # ID (obligatorio)
        normalized["id"] = str(product.get("id", "")) or f"product_{hash(str(product))}"
        
        # Título (obligatorio)
        normalized["title"] = str(product.get("title", "") or "Producto Sin Título").strip()
        
        # Descripción (convertir None a string vacío)
        body_html = product.get("body_html")
        if body_html is None:
            normalized["body_html"] = ""
        else:
            normalized["body_html"] = str(body_html)
        
        # Descripción alternativa
        description = product.get("description")
        if description is None:
            normalized["description"] = normalized["body_html"]
        else:
            normalized["description"] = str(description)
        
        # Tipo de producto/categoría
        product_type = product.get("product_type")
        if product_type is None:
            normalized["product_type"] = "General"
        else:
            normalized["product_type"] = str(product_type)
        
        # Variantes (asegurar que sea una lista)
        variants = product.get("variants")
        if variants is None:
            normalized["variants"] = []
        elif isinstance(variants, list):
            # Normalizar cada variante
            normalized_variants = []
            for variant in variants:
                if isinstance(variant, dict):
                    normalized_variant = {
                        "id": str(variant.get("id", "")),
                        "price": ProductDataValidator._normalize_price(variant.get("price")),
                        "title": str(variant.get("title", "") or "Variante"),
                        "available": bool(variant.get("available", True))
                    }
                    normalized_variants.append(normalized_variant)
            normalized["variants"] = normalized_variants
        else:
            normalized["variants"] = []
        
        # Precio principal (extraer del primer variante o usar 0)
        if normalized["variants"]:
            normalized["price"] = normalized["variants"][0]["price"]
        else:
            normalized["price"] = ProductDataValidator._normalize_price(product.get("price"))
        
        # Imágenes (asegurar que sea una lista)
        images = product.get("images")
        if images is None:
            normalized["images"] = []
        elif isinstance(images, list):
            # Normalizar cada imagen
            normalized_images = []
            for image in images:
                if isinstance(image, dict):
                    normalized_image = {
                        "id": str(image.get("id", "")),
                        "src": str(image.get("src", "") or ""),
                        "alt": str(image.get("alt", "") or "Imagen del producto")
                    }
                    normalized_images.append(normalized_image)
                elif isinstance(image, str):
                    # Si es solo una URL string
                    normalized_images.append({
                        "id": "",
                        "src": image,
                        "alt": "Imagen del producto"
                    })
            normalized["images"] = normalized_images
        else:
            normalized["images"] = []
        
        # Tags (convertir a lista de strings)
        tags = product.get("tags")
        if tags is None:
            normalized["tags"] = []
        elif isinstance(tags, str):
            # Si es un string, dividir por comas
            normalized["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
        elif isinstance(tags, list):
            normalized["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        else:
            normalized["tags"] = []
        
        # Vendor (proveedor)
        vendor = product.get("vendor")
        normalized["vendor"] = str(vendor) if vendor is not None else "Unknown"
        
        # Handle (URL slug)
        handle = product.get("handle")
        normalized["handle"] = str(handle) if handle is not None else normalized["id"]
        
        # Estado (published, draft, etc.)
        status = product.get("status", product.get("published_status"))
        normalized["status"] = str(status) if status is not None else "active"
        
        # Fechas
        created_at = product.get("created_at")
        normalized["created_at"] = str(created_at) if created_at is not None else ""
        
        updated_at = product.get("updated_at")
        normalized["updated_at"] = str(updated_at) if updated_at is not None else ""
        
        # Metadatos adicionales (preservar campos extra)
        for key, value in product.items():
            if key not in normalized and value is not None:
                normalized[key] = value
        
        return normalized
    
    @staticmethod
    def _normalize_price(price_value: Any) -> float:
        """
        Normaliza un valor de precio a float.
        
        Args:
            price_value: Valor del precio (puede ser string, int, float, None)
            
        Returns:
            Precio como float (0.0 si no se puede convertir)
        """
        if price_value is None:
            return 0.0
        
        try:
            # Si es string, limpiar caracteres especiales
            if isinstance(price_value, str):
                # Remover símbolos de moneda y espacios
                clean_price = price_value.replace("$", "").replace(",", "").replace(" ", "").strip()
                if not clean_price:
                    return 0.0
                return float(clean_price)
            
            # Si es numérico, convertir directamente
            return float(price_value)
        
        except (ValueError, TypeError):
            logger.warning(f"No se pudo convertir precio '{price_value}' a float, usando 0.0")
            return 0.0
    
    @staticmethod
    def validate_product_catalog(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Valida y normaliza un catálogo completo de productos.
        
        Args:
            products: Lista de productos sin normalizar
            
        Returns:
            Lista de productos normalizados
        """
        if not products:
            logger.warning("Catálogo de productos está vacío")
            return []
        
        normalized_products = []
        errors_count = 0
        
        for i, product in enumerate(products):
            try:
                normalized_product = ProductDataValidator.validate_and_normalize_product(product)
                normalized_products.append(normalized_product)
            except Exception as e:
                errors_count += 1
                logger.error(f"Error normalizando producto en índice {i}: {e}")
                
                # Crear producto de emergencia
                emergency_product = {
                    "id": f"error_product_{i}",
                    "title": f"Producto Error {i}",
                    "body_html": "Error al procesar datos del producto",
                    "description": "Error al procesar datos del producto",
                    "product_type": "Error",
                    "variants": [],
                    "price": 0.0,
                    "images": [],
                    "tags": ["error"],
                    "vendor": "System",
                    "handle": f"error-product-{i}",
                    "status": "error"
                }
                normalized_products.append(emergency_product)
        
        logger.info(f"Catálogo normalizado: {len(normalized_products)} productos, {errors_count} errores corregidos")
        return normalized_products
    
    @staticmethod
    def validate_recommendation_data(recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida datos de una recomendación específica.
        
        Args:
            recommendation: Datos de recomendación
            
        Returns:
            Recomendación normalizada
        """
        normalized = {}
        
        # Campos obligatorios para recomendaciones
        normalized["id"] = str(recommendation.get("id", "unknown"))
        normalized["title"] = str(recommendation.get("title", "Producto") or "Producto")
        normalized["description"] = str(recommendation.get("description", "") or "")
        normalized["price"] = ProductDataValidator._normalize_price(recommendation.get("price"))
        normalized["score"] = float(recommendation.get("score", recommendation.get("similarity_score", 0.5)))
        normalized["category"] = str(recommendation.get("category", recommendation.get("product_type", "")) or "")
        normalized["images"] = list(recommendation.get("images", []))
        normalized["source"] = str(recommendation.get("source", "unknown"))
        
        # Campos opcionales
        if "reason" in recommendation:
            normalized["reason"] = str(recommendation["reason"])
        
        if "recommendation_type" in recommendation:
            normalized["recommendation_type"] = str(recommendation["recommendation_type"])
        
        return normalized