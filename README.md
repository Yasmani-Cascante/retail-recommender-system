# Sistema de Recomendaciones para Retail

Este proyecto implementa un sistema de recomendaciones para productos de retail utilizando técnicas de recomendación basadas en contenido.

## Instalación

1. Clonar el repositorio:
```bash
git clone https://github.com/Yasmani-Cascante/retail-recommender-system.git
cd retail-recommender-system
```

2. Crear un entorno virtual:
```bash
python -m venv venv
```

3. Activar el entorno virtual:
- En Windows:
```bash
.\venv\Scripts\activate
```
- En Linux/Mac:
```bash
source venv/bin/activate
```

4. Instalar el proyecto en modo desarrollo:
```bash
pip install -e .
```

## Ejecutar el proyecto

Hay varias formas de ejecutar el proyecto:

1. Usando el archivo run.py en la raíz (recomendado):
```bash
python run.py
```

2. O directamente usando el módulo src:
```bash
python src/api/run.py
```

El servidor estará disponible en:
- API: http://localhost:8000
- Documentación: http://localhost:8000/docs

## Endpoints disponibles

- `GET /`: Mensaje de bienvenida
- `GET /products/`: Lista todos los productos
- `GET /recommendations/{product_id}`: Obtiene recomendaciones para un producto específico
- `GET /products/category/{category}`: Obtiene productos por categoría
- `GET /products/search/?q={query}`: Busca productos por nombre o descripción

## Ejemplo de uso

1. Ver todos los productos:
```
http://localhost:8000/products/
```

2. Obtener recomendaciones para el Jeans Slim Fit (ID: 1):
```
http://localhost:8000/recommendations/1
```

3. Buscar productos de la categoría "Vestidos":
```
http://localhost:8000/products/category/Vestidos
```

4. Buscar productos que contengan "algodón":
```
http://localhost:8000/products/search/?q=algodón
```

## Estructura del proyecto

```
retail-recommender-system/
├── setup.py               # Configuración del paquete
├── requirements.txt       # Dependencias del proyecto
├── run.py                # Script principal para ejecutar el proyecto
└── src/                  # Código fuente
    ├── api/              # API REST con FastAPI
    │   ├── main.py      # Definición de endpoints
    │   └── run.py       # Script de ejecución alternativo
    └── recommenders/     # Módulos de recomendación
        └── content_based.py  # Recomendador basado en contenido
```