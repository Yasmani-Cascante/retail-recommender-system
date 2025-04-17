"""
Validador de productos para Google Cloud Retail API.

Este módulo proporciona funciones para validar y procesar productos
antes de su importación a Google Cloud Retail API, asegurando que cumplan 
con todas las restricciones y limitaciones del servicio.
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Configuración de logging
logger = logging.getLogger(__name__)

class ProductValidator:
    """
    Validador de productos para Google Cloud Retail API.
    
    Verifica que los productos cumplan con los requisitos de Google Cloud Retail API
    y aplica transformaciones necesarias para garantizar la compatibilidad.
    """
    
    def __init__(self, log_dir: str = "logs/product_validation"):
        """
        Inicializa el validador de productos.
        
        Args:
            log_dir: Directorio donde se guardarán los registros de validación.
        """
        self.log_dir = log_dir
        
        # Crear directorio de logs si no existe
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # Archivo de registro para productos modificados
        self.modified_products_log = os.path.join(
            log_dir, 
            f"modified_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        )
        
        # Estadísticas de validación
        self.stats = {
            "total_products": 0,
            "valid_products": 0,
            "modified_products": 0,
            "invalid_products": 0,
            "description_too_long": 0,
            "missing_required_fields": 0,
            "modification_types": {}
        }
    
    def validate_products(self, products: List[Dict]) -> Tuple[List[Dict], Dict]:
        """
        Valida una lista de productos y aplica correcciones cuando es posible.
        
        Args:
            products: Lista de productos a validar.
            
        Returns:
            Tuple con la lista de productos válidos y un diccionario con estadísticas de validación.
        """
        self.stats["total_products"] = len(products)
        valid_products = []
        
        logger.info(f"Iniciando validación de {len(products)} productos")
        
        for product in products:
            validated_product, modifications = self.validate_product(product)
            
            if validated_product:
                valid_products.append(validated_product)
                self.stats["valid_products"] += 1
                
                if modifications:
                    self.stats["modified_products"] += 1
                    
                    # Registrar producto modificado
                    self._log_modified_product(product, validated_product, modifications)
                    
                    # Actualizar estadísticas por tipo de modificación
                    for mod_type in modifications:
                        self.stats["modification_types"][mod_type] = self.stats["modification_types"].get(mod_type, 0) + 1
            else:
                self.stats["invalid_products"] += 1
        
        logger.info(f"Validación completada: {self.stats['valid_products']} productos válidos, "
                   f"{self.stats['modified_products']} modificados, "
                   f"{self.stats['invalid_products']} inválidos")
        
        return valid_products, self.stats
    
    def validate_product(self, product: Dict) -> Tuple[Optional[Dict], List[str]]:
        """
        Valida un producto individual y aplica correcciones cuando es posible.
        
        Args:
            product: Producto a validar.
            
        Returns:
            Tuple con el producto validado (o None si no es válido) y una lista de modificaciones aplicadas.
        """
        if not product:
            return None, ["empty_product"]
        
        # Crear copia para evitar modificar el original
        validated = product.copy()
        modifications = []
        
        # Validar campos obligatorios
        product_id = str(validated.get("id", ""))
        
        if not product_id:
            logger.warning("Producto sin ID, no se puede procesar")
            self.stats["missing_required_fields"] += 1
            return None, ["missing_id"]
        
        # Validar título
        title = validated.get("title", "")
        if not title:
            title = validated.get("name", "")
            
        if not title:
            # Crear título a partir del ID
            validated["title"] = f"Producto {product_id}"
            modifications.append("title_generated")
        
        # Validar descripción
        description = validated.get("body_html", "")
        if not description:
            description = validated.get("description", "")
            
        # Si la descripción es demasiado larga, resumirla inteligentemente
        if description and len(description) > 5000:
            self.stats["description_too_long"] += 1
            
            # Obtener descripción resumida
            original_length = len(description)
            summarized_description = self._summarize_description(description)
            
            # Actualizar la descripción en el producto
            if "body_html" in validated:
                validated["body_html"] = summarized_description
            if "description" in validated:
                validated["description"] = summarized_description
                
            logger.warning(f"Descripción del producto {product_id} resumida de {original_length} a {len(summarized_description)} caracteres")
            modifications.append("description_summarized")
        
        # Validar categoría
        category = validated.get("product_type", "")
        if not category:
            category = validated.get("category", "")
            
        if not category:
            validated["product_type"] = "General"
            modifications.append("category_added")
        
        # Validar disponibilidad
        availability = validated.get("availability", "")
        if not availability:
            validated["availability"] = "IN_STOCK"
            modifications.append("availability_added")
        
        return validated, modifications
    
    def _summarize_description(self, text: str, max_length: int = 4900) -> str:
        """
        Resume inteligentemente una descripción larga para mantenerla dentro del límite.
        
        Args:
            text: Texto a resumir.
            max_length: Longitud máxima permitida.
            
        Returns:
            Texto resumido.
        """
        if not text or len(text) <= max_length:
            return text
        
        try:
            # 1. Dividir en oraciones
            sentences = re.split(r'(?<=[.!?])\s+', text)
            
            # 2. Calcular la importancia de cada oración
            scored_sentences = []
            for i, sentence in enumerate(sentences):
                # Importancia basada en posición (primeras y últimas oraciones más importantes)
                position_score = 1.0
                if i < len(sentences) * 0.2:  # Primeras 20% oraciones
                    position_score = 2.0
                elif i > len(sentences) * 0.8:  # Últimas 20% oraciones
                    position_score = 0.8
                
                # Importancia basada en palabras clave
                keyword_score = 1.0
                keywords = ["características", "especificaciones", "beneficios", 
                           "ventajas", "importante", "destacado", "principal", 
                           "technical", "specifications", "features", "benefits"]
                
                for keyword in keywords:
                    if keyword.lower() in sentence.lower():
                        keyword_score = 1.5
                        break
                
                # Longitud de la oración (evitar oraciones muy cortas o muy largas)
                length_score = 1.0
                if len(sentence) < 20:
                    length_score = 0.8
                elif 20 <= len(sentence) <= 100:
                    length_score = 1.2
                
                total_score = position_score * keyword_score * length_score
                scored_sentences.append((sentence, total_score))
            
            # 3. Ordenar por importancia
            scored_sentences.sort(key=lambda x: x[1], reverse=True)
            
            # 4. Construir resumen manteniendo la primera oración siempre
            summary = sentences[0] + " "
            remaining_length = max_length - len(summary)
            
            # Añadir oraciones más importantes hasta alcanzar el límite
            for sentence, _ in scored_sentences:
                if sentence == sentences[0]:  # Evitar duplicar la primera oración
                    continue
                    
                if len(sentence) + 1 <= remaining_length:
                    summary += sentence + " "
                    remaining_length -= (len(sentence) + 1)
                else:
                    break
            
            # 5. Añadir indicación de resumen
            if len(text) > len(summary.strip()):
                summary = summary.strip() + " [...]"
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error al resumir descripción: {str(e)}")
            # Fallback a truncamiento simple si hay algún error
            return text[:4997] + "..."
    
    def _log_modified_product(self, original: Dict, modified: Dict, modifications: List[str]):
        """
        Registra un producto modificado en el archivo de log.
        
        Args:
            original: Producto original antes de las modificaciones.
            modified: Producto después de las modificaciones.
            modifications: Lista de modificaciones aplicadas.
        """
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "product_id": str(original.get("id", "")),
                "modifications": modifications,
                "original": self._extract_relevant_fields(original),
                "modified": self._extract_relevant_fields(modified)
            }
            
            with open(self.modified_products_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            logger.error(f"Error al registrar producto modificado: {str(e)}")
    
    def _extract_relevant_fields(self, product: Dict) -> Dict:
        """
        Extrae los campos relevantes de un producto para el registro.
        
        Args:
            product: Producto completo.
            
        Returns:
            Diccionario con los campos relevantes.
        """
        relevant = {}
        
        # Campos a incluir en el registro
        fields = ["id", "title", "body_html", "description", "product_type", "availability"]
        
        for field in fields:
            if field in product:
                # Para campos de texto largo, incluir solo un resumen
                if field in ["body_html", "description"] and isinstance(product[field], str) and len(product[field]) > 100:
                    relevant[field] = product[field][:100] + "..."
                else:
                    relevant[field] = product[field]
        
        return relevant
    
    def get_validation_report(self) -> Dict:
        """
        Genera un informe completo de la validación.
        
        Returns:
            Diccionario con estadísticas y resumen de la validación.
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "log_file": self.modified_products_log,
            "summary": {
                "success_rate": round((self.stats["valid_products"] / self.stats["total_products"]) * 100, 2) if self.stats["total_products"] > 0 else 0,
                "modification_rate": round((self.stats["modified_products"] / self.stats["total_products"]) * 100, 2) if self.stats["total_products"] > 0 else 0,
                "top_modifications": sorted(self.stats["modification_types"].items(), key=lambda x: x[1], reverse=True)[:5]
            }
        }
        
        return report
