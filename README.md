# Sistema de Recomendaciones para Retail

Este proyecto implementa un sistema de recomendaciones para productos de retail utilizando técnicas de recomendación basadas en contenido.

## Instalación

1. Crear un entorno virtual:
```bash
python -m venv venv
```

2. Activar el entorno virtual:
- En Windows:
```bash
.\venv\Scripts\activate
```
- En Linux/Mac:
```bash
source venv/bin/activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

## Ejecutar el proyecto

1. Asegúrate de tener el entorno virtual activado
2. Desde la raíz del proyecto, ejecuta:
```bash
python src/api/run.py
```
3. La API estará disponible en `http://localhost:8000`
4. Puedes ver la documentación de la API en `http://localhost:8000/docs`

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