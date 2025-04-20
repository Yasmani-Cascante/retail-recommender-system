"""
Datos de eventos de usuario de muestra para pruebas del sistema de recomendaciones.

Este módulo proporciona una colección de eventos de usuario ficticios para 
simular diferentes patrones de comportamiento y probar la exclusión de productos
vistos, recomendaciones personalizadas y otras funcionalidades.
"""

from datetime import datetime, timedelta

# Fecha base para eventos (podemos usar fechas recientes para pruebas)
BASE_DATE = datetime(2025, 4, 20, 10, 0, 0)

SAMPLE_USER_EVENTS = {
    "test_user_1": [
        {
            "user_id": "test_user_1",
            "event_type": "detail-page-view",
            "product_id": "test_prod_1",
            "timestamp": (BASE_DATE + timedelta(minutes=15)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_1",
            "event_type": "add-to-cart",
            "product_id": "test_prod_1",
            "timestamp": (BASE_DATE + timedelta(minutes=16, seconds=45)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_1",
            "event_type": "purchase-complete",
            "product_id": "test_prod_1",
            "timestamp": (BASE_DATE + timedelta(minutes=20, seconds=12)).isoformat() + "Z",
            "purchase_amount": 19.99
        },
        {
            "user_id": "test_user_1",
            "event_type": "detail-page-view",
            "product_id": "test_prod_5",
            "timestamp": (BASE_DATE + timedelta(hours=1, minutes=30, seconds=5)).isoformat() + "Z"
        }
    ],
    "test_user_2": [
        {
            "user_id": "test_user_2",
            "event_type": "search",
            "query": "smartphone",
            "timestamp": (BASE_DATE - timedelta(minutes=50)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_2",
            "event_type": "detail-page-view",
            "product_id": "test_prod_3",
            "timestamp": (BASE_DATE - timedelta(minutes=47, seconds=30)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_2",
            "event_type": "category-page-view",
            "category": "Electrónica",
            "timestamp": (BASE_DATE - timedelta(minutes=44, seconds=15)).isoformat() + "Z"
        }
    ],
    "test_user_3": [
        # Usuario nuevo sin eventos para probar recomendaciones para nuevos usuarios
    ],
    "test_user_4": [
        # Usuario con múltiples interacciones en una categoría para probar preferencias
        {
            "user_id": "test_user_4",
            "event_type": "detail-page-view",
            "product_id": "test_prod_3",
            "timestamp": (BASE_DATE + timedelta(hours=4, minutes=10)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_4",
            "event_type": "detail-page-view",
            "product_id": "test_prod_8",
            "timestamp": (BASE_DATE + timedelta(hours=4, minutes=15)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_4",
            "event_type": "detail-page-view",
            "product_id": "test_prod_9",
            "timestamp": (BASE_DATE + timedelta(hours=4, minutes=20)).isoformat() + "Z"
        }
    ],
    "test_user_5": [
        # Usuario con múltiples categorías de interés
        {
            "user_id": "test_user_5",
            "event_type": "detail-page-view",
            "product_id": "test_prod_1",  # Ropa
            "timestamp": (BASE_DATE + timedelta(hours=2)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_5",
            "event_type": "detail-page-view",
            "product_id": "test_prod_5",  # Calzado
            "timestamp": (BASE_DATE + timedelta(hours=2, minutes=30)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_5",
            "event_type": "detail-page-view",
            "product_id": "test_prod_8",  # Electrónica
            "timestamp": (BASE_DATE + timedelta(hours=3)).isoformat() + "Z"
        }
    ],
    "test_user_6": [
        # Usuario con evento de compra para probar transaction
        {
            "user_id": "test_user_6",
            "event_type": "detail-page-view",
            "product_id": "test_prod_3",
            "timestamp": (BASE_DATE - timedelta(days=1, hours=2)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_6",
            "event_type": "add-to-cart",
            "product_id": "test_prod_3",
            "timestamp": (BASE_DATE - timedelta(days=1, hours=1, minutes=55)).isoformat() + "Z"
        },
        {
            "user_id": "test_user_6",
            "event_type": "purchase-complete",
            "product_id": "test_prod_3",
            "timestamp": (BASE_DATE - timedelta(days=1, hours=1, minutes=45)).isoformat() + "Z",
            "purchase_amount": 999.99
        }
    ]
}

def get_events_for_user(user_id):
    """
    Obtiene los eventos de un usuario específico.
    
    Args:
        user_id: ID del usuario
        
    Returns:
        List[Dict]: Lista de eventos del usuario, o lista vacía si no existe
    """
    return SAMPLE_USER_EVENTS.get(user_id, [])

def get_all_events():
    """
    Obtiene todos los eventos de todos los usuarios.
    
    Returns:
        List[Dict]: Lista plana de todos los eventos
    """
    all_events = []
    for user_events in SAMPLE_USER_EVENTS.values():
        all_events.extend(user_events)
    return all_events
