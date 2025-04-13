"""
Generador de eventos de usuario de prueba para alimentar el sistema de recomendaciones.

Este módulo proporciona funciones para generar eventos sintéticos de usuario
que ayudan a entrenar el sistema de recomendaciones de Google Cloud Retail API
cuando hay pocos datos históricos disponibles.
"""

import logging
import asyncio
import random
import time
from typing import List, Dict, Optional
import os

logger = logging.getLogger(__name__)

class EventGenerator:
    """
    Genera eventos de usuario sintéticos para entrenar el sistema de recomendaciones.
    """
    
    def __init__(self, retail_recommender, tfidf_recommender):
        """
        Inicializa el generador de eventos.
        
        Args:
            retail_recommender: Instancia de RetailAPIRecommender
            tfidf_recommender: Instancia de TFIDFRecommender
        """
        self.retail_recommender = retail_recommender
        self.tfidf_recommender = tfidf_recommender
        self.user_ids = [f"synthetic_user_{i}" for i in range(1, 11)]  # 10 usuarios sintéticos
        
    async def generate_events(self, num_events: int = 50) -> Dict:
        """
        Genera eventos sintéticos de usuario.
        
        Args:
            num_events: Número de eventos a generar
            
        Returns:
            Dict: Resultado de la generación de eventos
        """
        if not self.tfidf_recommender.loaded or not self.tfidf_recommender.product_data:
            logger.error("El recomendador TF-IDF no está cargado o no hay productos disponibles")
            return {"status": "error", "message": "No hay productos disponibles para generar eventos"}
        
        logger.info(f"Generando {num_events} eventos sintéticos de usuario")
        
        # Obtener productos disponibles
        products = self.tfidf_recommender.product_data
        
        if not products:
            logger.error("No hay productos disponibles para generar eventos")
            return {"status": "error", "message": "No hay productos disponibles"}
        
        # Mapear productos por categoría para diversificar eventos
        products_by_category = {}
        for product in products:
            category = product.get("product_type", "General")
            if category not in products_by_category:
                products_by_category[category] = []
            products_by_category[category].append(product)
        
        # Tipos de eventos a generar
        event_types = ["detail-page-view", "add-to-cart", "purchase-complete"]
        event_weights = [0.7, 0.2, 0.1]  # Probabilidades de cada tipo (sum = 1.0)
        
        # Generar eventos
        events_generated = 0
        events_failed = 0
        
        for _ in range(num_events):
            try:
                # Seleccionar usuario aleatorio
                user_id = random.choice(self.user_ids)
                
                # Seleccionar categoría aleatoria (si hay categorías)
                if products_by_category:
                    category = random.choice(list(products_by_category.keys()))
                    category_products = products_by_category[category]
                    product = random.choice(category_products)
                else:
                    product = random.choice(products)
                
                product_id = str(product.get("id", ""))
                
                # Seleccionar tipo de evento basado en pesos
                event_type = random.choices(event_types, weights=event_weights, k=1)[0]
                
                # Registrar evento
                logger.info(f"Generando evento: user_id={user_id}, event_type={event_type}, product_id={product_id}")
                result = await self.retail_recommender.record_user_event(
                    user_id=user_id,
                    event_type=event_type,
                    product_id=product_id
                )
                
                if result.get("status") == "success":
                    events_generated += 1
                else:
                    events_failed += 1
                    logger.warning(f"Error registrando evento: {result}")
                
                # Pequeña pausa para evitar saturar la API
                await asyncio.sleep(0.2)
                
            except Exception as e:
                events_failed += 1
                logger.error(f"Error generando evento: {str(e)}")
        
        logger.info(f"Generación de eventos completada: {events_generated} exitosos, {events_failed} fallidos")
        
        return {
            "status": "success",
            "events_generated": events_generated,
            "events_failed": events_failed
        }

    async def generate_realistic_user_sessions(self, num_sessions: int = 5) -> Dict:
        """
        Genera sesiones de usuario realistas que incluyen múltiples interacciones
        con productos relacionados.
        
        Args:
            num_sessions: Número de sesiones a generar
            
        Returns:
            Dict: Resultado de la generación de sesiones
        """
        if not self.tfidf_recommender.loaded or not self.tfidf_recommender.product_data:
            logger.error("El recomendador TF-IDF no está cargado o no hay productos disponibles")
            return {"status": "error", "message": "No hay productos disponibles para generar eventos"}
        
        logger.info(f"Generando {num_sessions} sesiones realistas de usuario")
        
        # Obtener productos disponibles
        products = self.tfidf_recommender.product_data
        if not products:
            logger.error("No hay productos disponibles para generar eventos")
            return {"status": "error", "message": "No hay productos disponibles"}
        
        events_generated = 0
        events_failed = 0
        
        # Para cada sesión
        for session_num in range(num_sessions):
            try:
                # Seleccionar usuario aleatorio
                user_id = random.choice(self.user_ids)
                logger.info(f"Generando sesión {session_num+1} para usuario {user_id}")
                
                # Productos vistos en esta sesión
                viewed_products = []
                cart_products = []
                purchased_products = []
                
                # Seleccionar 1-3 categorías de interés para esta sesión
                all_categories = list(set(product.get("product_type", "General") for product in products))
                num_categories = min(random.randint(1, 3), len(all_categories))
                session_categories = random.sample(all_categories, num_categories)
                
                # Generar entre 5-15 vistas de producto
                num_views = random.randint(5, 15)
                for _ in range(num_views):
                    # Seleccionar productos principalmente de las categorías de interés
                    if random.random() < 0.8 and session_categories:  # 80% del tiempo
                        category = random.choice(session_categories)
                        category_products = [p for p in products if p.get("product_type", "General") == category]
                        if category_products:
                            product = random.choice(category_products)
                        else:
                            product = random.choice(products)
                    else:
                        product = random.choice(products)
                    
                    product_id = str(product.get("id", ""))
                    viewed_products.append(product_id)
                    
                    # Registrar evento de vista
                    result = await self.retail_recommender.record_user_event(
                        user_id=user_id,
                        event_type="detail-page-view",
                        product_id=product_id
                    )
                    
                    if result.get("status") == "success":
                        events_generated += 1
                    else:
                        events_failed += 1
                        
                    # Pequeña pausa para evitar saturar la API
                    await asyncio.sleep(0.2)
                
                # Añadir algunos productos al carrito (20-40% de los vistos)
                cart_probability = random.uniform(0.2, 0.4)
                for product_id in viewed_products:
                    if random.random() < cart_probability:
                        cart_products.append(product_id)
                        
                        # Registrar evento de añadir al carrito
                        result = await self.retail_recommender.record_user_event(
                            user_id=user_id,
                            event_type="add-to-cart",
                            product_id=product_id
                        )
                        
                        if result.get("status") == "success":
                            events_generated += 1
                        else:
                            events_failed += 1
                            
                        await asyncio.sleep(0.2)
                
                # Comprar algunos productos (50-80% de los añadidos al carrito)
                purchase_probability = random.uniform(0.5, 0.8)
                for product_id in cart_products:
                    if random.random() < purchase_probability:
                        purchased_products.append(product_id)
                        
                        # Registrar evento de compra
                        result = await self.retail_recommender.record_user_event(
                            user_id=user_id,
                            event_type="purchase-complete",
                            product_id=product_id,
                            purchase_amount=random.uniform(10.0, 200.0)  # Añadir monto de compra aleatorio
                        )
                        
                        if result.get("status") == "success":
                            events_generated += 1
                        else:
                            events_failed += 1
                            
                        await asyncio.sleep(0.2)
                
                logger.info(f"Sesión {session_num+1} completada: {len(viewed_products)} vistas, "
                           f"{len(cart_products)} productos en carrito, {len(purchased_products)} compras")
                
                # Pausa entre sesiones
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error generando sesión {session_num+1}: {str(e)}")
        
        logger.info(f"Generación de sesiones completada: {events_generated} eventos exitosos, {events_failed} fallidos")
        
        return {
            "status": "success",
            "sessions_generated": num_sessions,
            "events_generated": events_generated,
            "events_failed": events_failed
        }
    
    async def generate_personalized_events_for_user(self, user_id: str, num_events: int = 20) -> Dict:
        """
        Genera eventos personalizados para un usuario específico.
        
        Args:
            user_id: ID del usuario para el que generar eventos
            num_events: Número de eventos a generar
            
        Returns:
            Dict: Resultado de la generación de eventos
        """
        if not self.tfidf_recommender.loaded or not self.tfidf_recommender.product_data:
            logger.error("El recomendador TF-IDF no está cargado o no hay productos disponibles")
            return {"status": "error", "message": "No hay productos disponibles para generar eventos"}
        
        logger.info(f"Generando {num_events} eventos personalizados para usuario {user_id}")
        
        # Obtener productos disponibles
        products = self.tfidf_recommender.product_data
        if not products:
            logger.error("No hay productos disponibles para generar eventos")
            return {"status": "error", "message": "No hay productos disponibles"}
        
        # Seleccionar categorías de interés para este usuario (2-3 categorías)
        all_categories = list(set(product.get("product_type", "General") for product in products))
        num_categories = min(random.randint(2, 3), len(all_categories))
        user_categories = random.sample(all_categories, num_categories)
        
        logger.info(f"Categorías de interés para usuario {user_id}: {user_categories}")
        
        # Distribución de eventos por tipo
        view_events = int(num_events * 0.7)  # 70% vistas
        cart_events = int(num_events * 0.2)  # 20% añadir al carrito
        purchase_events = num_events - view_events - cart_events  # 10% compras
        
        events_generated = 0
        events_failed = 0
        
        # Generar eventos de vista
        for _ in range(view_events):
            try:
                # Seleccionar producto de categorías de interés (80% del tiempo)
                if random.random() < 0.8 and user_categories:
                    category = random.choice(user_categories)
                    category_products = [p for p in products if p.get("product_type", "General") == category]
                    if category_products:
                        product = random.choice(category_products)
                    else:
                        product = random.choice(products)
                else:
                    product = random.choice(products)
                
                product_id = str(product.get("id", ""))
                
                # Registrar evento de vista
                result = await self.retail_recommender.record_user_event(
                    user_id=user_id,
                    event_type="detail-page-view",
                    product_id=product_id
                )
                
                if result.get("status") == "success":
                    events_generated += 1
                else:
                    events_failed += 1
                    
                await asyncio.sleep(0.2)
                
            except Exception as e:
                events_failed += 1
                logger.error(f"Error generando evento de vista: {str(e)}")
        
        # Generar eventos de añadir al carrito
        viewed_products = [p.get("id") for p in products if random.random() < 0.3][:cart_events]
        for product_id in viewed_products[:cart_events]:
            try:
                # Registrar evento de añadir al carrito
                result = await self.retail_recommender.record_user_event(
                    user_id=user_id,
                    event_type="add-to-cart",
                    product_id=str(product_id)
                )
                
                if result.get("status") == "success":
                    events_generated += 1
                else:
                    events_failed += 1
                    
                await asyncio.sleep(0.2)
                
            except Exception as e:
                events_failed += 1
                logger.error(f"Error generando evento de carrito: {str(e)}")
        
        # Generar eventos de compra
        cart_products = viewed_products[:purchase_events]
        for product_id in cart_products:
            try:
                # Registrar evento de compra
                result = await self.retail_recommender.record_user_event(
                    user_id=user_id,
                    event_type="purchase-complete",
                    product_id=str(product_id),
                    purchase_amount=random.uniform(10.0, 200.0)  # Añadir monto de compra aleatorio
                )
                
                if result.get("status") == "success":
                    events_generated += 1
                else:
                    events_failed += 1
                    
                await asyncio.sleep(0.2)
                
            except Exception as e:
                events_failed += 1
                logger.error(f"Error generando evento de compra: {str(e)}")
        
        logger.info(f"Generación de eventos personalizados completada: {events_generated} exitosos, {events_failed} fallidos")
        
        return {
            "status": "success",
            "user_id": user_id,
            "events_generated": events_generated,
            "events_failed": events_failed
        }

async def initialize_with_test_data(retail_recommender, tfidf_recommender):
    """
    Inicializa el sistema con datos de prueba si está en modo de desarrollo.
    
    Args:
        retail_recommender: Instancia de RetailAPIRecommender
        tfidf_recommender: Instancia de TFIDFRecommender
    """
    # Solo ejecutar en modo de desarrollo
    if os.getenv("DEBUG", "False").lower() == "true":
        logger.info("Modo de desarrollo detectado. Generando datos de prueba...")
        
        # Esperar a que el recomendador esté cargado
        max_retries = 10
        for i in range(max_retries):
            if tfidf_recommender.loaded:
                break
            logger.info(f"Esperando a que el recomendador TF-IDF se cargue ({i+1}/{max_retries})...")
            await asyncio.sleep(5)
        
        if not tfidf_recommender.loaded:
            logger.warning("El recomendador TF-IDF no está cargado. No se generarán datos de prueba.")
            return
        
        # Generar eventos
        generator = EventGenerator(retail_recommender, tfidf_recommender)
        
        try:
            # Generar eventos aleatorios
            logger.info("Generando eventos aleatorios...")
            result = await generator.generate_events(num_events=30)
            logger.info(f"Resultado de generación de eventos aleatorios: {result}")
            
            # Generar sesiones realistas
            logger.info("Generando sesiones realistas...")
            result = await generator.generate_realistic_user_sessions(num_sessions=5)
            logger.info(f"Resultado de generación de sesiones: {result}")
            
            # Generar eventos personalizados para un usuario específico
            specific_user = "test_user_specific"
            logger.info(f"Generando eventos personalizados para usuario {specific_user}...")
            result = await generator.generate_personalized_events_for_user(
                user_id=specific_user,
                num_events=25
            )
            logger.info(f"Resultado de generación de eventos personalizados: {result}")
            
            logger.info("Generación de datos de prueba completada.")
            
        except Exception as e:
            logger.error(f"Error generando datos de prueba: {str(e)}")
    else:
        logger.info("Modo de producción. No se generarán datos de prueba automáticamente.")
