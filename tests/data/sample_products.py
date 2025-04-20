"""
Datos de productos de muestra para pruebas del sistema de recomendaciones.

Este módulo proporciona una colección de productos ficticios con diferentes
características para probar diversos escenarios del sistema.
"""

SAMPLE_PRODUCTS = [
    {
        "id": "test_prod_1",
        "title": "Camiseta básica de algodón",
        "body_html": "Camiseta 100% algodón de alta calidad. Disponible en varios colores. Perfecta para el uso diario.",
        "product_type": "Ropa",
        "variants": [{"price": "19.99"}],
        "images": [{"src": "https://example.com/image1.jpg"}],
        "tags": "algodón, camiseta, básico"
    },
    {
        "id": "test_prod_2",
        "title": "Pantalón vaquero",
        "body_html": "Pantalón vaquero clásico de corte recto. Fabricado con materiales sostenibles.",
        "product_type": "Ropa",
        "variants": [{"price": "59.99"}],
        "images": [{"src": "https://example.com/image2.jpg"}],
        "tags": "vaquero, pantalón, sostenible"
    },
    # Producto con descripción larga para probar resumen inteligente
    {
        "id": "test_prod_3",
        "title": "Smartphone última generación",
        "body_html": "Este smartphone de última generación cuenta con una pantalla AMOLED de 6.5 pulgadas, procesador octa-core de 2.8GHz, 8GB de RAM y 256GB de almacenamiento. La cámara principal es de 108MP con estabilización óptica, mientras que la frontal es de 32MP perfecta para selfies. Incluye batería de 5000mAh con carga rápida de 65W que permite cargar el dispositivo al 100% en solo 30 minutos. Resistente al agua y polvo con certificación IP68. Sistema operativo Android 12 con 3 años garantizados de actualizaciones. Disponible en colores negro, plata y azul. Incluye cargador rápido, cable USB-C, auriculares y funda protectora. Garantía de 2 años contra defectos de fabricación.",
        "product_type": "Electrónica",
        "variants": [{"price": "999.99"}],
        "images": [{"src": "https://example.com/image3.jpg"}],
        "tags": "smartphone, electrónica, android"
    },
    # Producto sin imágenes
    {
        "id": "test_prod_4",
        "title": "Libro: Guía de Desarrollo con Python",
        "body_html": "Guía completa para aprender desarrollo con Python desde cero.",
        "product_type": "Libros",
        "variants": [{"price": "29.99"}],
        "images": [],
        "tags": "libros, python, programación"
    },
    # Productos de la misma categoría para validar exclusión
    {
        "id": "test_prod_5",
        "title": "Zapatillas deportivas",
        "body_html": "Zapatillas para running con amortiguación especial.",
        "product_type": "Calzado",
        "variants": [{"price": "89.99"}],
        "images": [{"src": "https://example.com/image5.jpg"}],
        "tags": "zapatillas, deporte, running"
    },
    {
        "id": "test_prod_6",
        "title": "Zapatillas casuales",
        "body_html": "Zapatillas casuales para el día a día con diseño moderno.",
        "product_type": "Calzado",
        "variants": [{"price": "69.99"}],
        "images": [{"src": "https://example.com/image6.jpg"}],
        "tags": "zapatillas, casual, moda"
    },
    # Producto sin precio ni variantes para probar robustez
    {
        "id": "test_prod_7",
        "title": "Producto de prueba sin precio",
        "body_html": "Este es un producto de prueba sin precio ni variantes.",
        "product_type": "Varios",
        "variants": [],
        "images": [{"src": "https://example.com/image7.jpg"}],
        "tags": "prueba, sin precio"
    },
    # Productos para pruebas de fallback por categoría
    {
        "id": "test_prod_8",
        "title": "Televisor LED 55 pulgadas",
        "body_html": "Televisor LED de 55 pulgadas con resolución 4K y HDR.",
        "product_type": "Electrónica",
        "variants": [{"price": "699.99"}],
        "images": [{"src": "https://example.com/image8.jpg"}],
        "tags": "tv, electrónica, 4k"
    },
    {
        "id": "test_prod_9",
        "title": "Tableta digital",
        "body_html": "Tableta digital con pantalla de 10 pulgadas y procesador de alta velocidad.",
        "product_type": "Electrónica",
        "variants": [{"price": "349.99"}],
        "images": [{"src": "https://example.com/image9.jpg"}],
        "tags": "tableta, electrónica, android"
    },
    # Producto con ID numérico para probar compatibilidad
    {
        "id": 10,
        "title": "Producto con ID numérico",
        "body_html": "Este producto tiene un ID numérico para probar la compatibilidad.",
        "product_type": "Varios",
        "variants": [{"price": "19.99"}],
        "images": [{"src": "https://example.com/image10.jpg"}],
        "tags": "prueba, id numérico"
    }
]
