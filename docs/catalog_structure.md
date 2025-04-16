# Integración con Google Cloud Retail API

## Descripción General

Este documento describe la integración del Sistema de Recomendaciones para Retail con Google Cloud Retail API, incluyendo la configuración, los flujos de datos, el procesamiento de respuestas y la solución al problema "Failed to get full branch details: $a undefined".

## Versión

**Última actualización:** 14 de abril de 2025  
**Versión de la API:** 0.5.0  
**Versión de Google Cloud Retail API:** v2

## Componentes Principales

### RetailAPIRecommender

Clase que implementa la interfaz con Google Cloud Retail API, proporcionando funcionalidades para:

- Importación de catálogos de productos
- Gestión de ramas (branches) del catálogo
- Registro de eventos de usuario
- Obtención de recomendaciones personalizadas

La clase está implementada en `src/recommenders/retail_api.py` y utiliza los clientes oficiales de Google Cloud para interactuar con los servicios.

### CatalogManager

Clase que gestiona específicamente la estructura del catálogo y sus ramas, implementada en `src/api/core/catalog_manager.py`. Proporciona funcionalidades para:

- Verificar la existencia del catálogo
- Listar ramas disponibles
- Asegurar que las ramas necesarias existen
- Obtener detalles de las ramas

## Configuración

### Variables de Entorno

```
GOOGLE_PROJECT_NUMBER=178362262166
GOOGLE_LOCATION=global
GOOGLE_CATALOG=default_catalog
GOOGLE_SERVING_CONFIG=default_recommendation_config
GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild
USE_GCS_IMPORT=true
```

### Inicialización

```python
retail_recommender = RetailAPIRecommender(
    project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
    location=os.getenv("GOOGLE_LOCATION", "global"),
    catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
    serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
)
```

## Estructura de Ramas del Catálogo

Google Cloud Retail API organiza los productos en ramas (branches) dentro de un catálogo. La estructura jerárquica es:

```
projects/{project_number}/locations/{location}/catalogs/{catalog_id}/branches/{branch_id}
```

Por defecto, el sistema utiliza tres ramas principales:

- **Branch 0**: La rama principal de producción
- **Branch 1**: Rama secundaria (puede usarse para staging)
- **Branch 2**: Rama terciaria (puede usarse para pruebas)

## Solución al Error "Failed to get full branch details: $a undefined"

### Descripción del Problema

Este error aparece en la consola de Google Cloud Retail API cuando el sistema intenta mostrar detalles de las ramas del catálogo, pero no puede recuperar la información completa debido a alguna inconsistencia en la estructura del catálogo o en las ramas.

### Causas Probables

1. **Ramas no inicializadas correctamente**: La API intenta acceder a ramas que no existen o no están completamente configuradas.
2. **Error en la interpolación de variables**: El error `$a undefined` sugiere un problema con una variable JavaScript que no fue reemplazada correctamente.
3. **Estructura inconsistente del catálogo**: La estructura real del catálogo no coincide con la estructura esperada por la interfaz.

### Solución Implementada

1. **CatalogManager**: Se ha creado una clase específica para gestionar la estructura del catálogo y sus ramas:
   - Verifica la existencia del catálogo 
   - Lista las ramas disponibles
   - Asegura que las ramas necesarias existen
   - Crea ramas faltantes mediante la inserción de productos temporales

2. **Verificación durante el Arranque**: El sistema ahora verifica y configura las ramas durante el inicio:
   ```python
   @app.on_event("startup")
   async def startup_event():
       try:
           logger.info("Verificando estructura del catálogo en Google Cloud Retail API...")
           await retail_recommender.ensure_catalog_branches()
       except Exception as e:
           logger.warning(f"Error al verificar estructura del catálogo: {str(e)}")
   ```

3. **Verificación antes de Importaciones**: Se verifica la estructura antes de cada importación:
   ```python
   async def import_catalog(self, products: List[Dict]):
       # Asegurar que las ramas del catálogo están correctamente configuradas
       if self.catalog_manager:
           await self.ensure_catalog_branches()
   ```

4. **Script de Corrección**: Se ha creado un script independiente `fix_catalog_branches.py` que puede ejecutarse manualmente para forzar la verificación y corrección de la estructura del catálogo.

### Herramientas de Diagnóstico

1. **fix_catalog_branches.py**: Script para verificar y corregir la estructura del catálogo y sus ramas.
2. **check_branch_updated.py**: Script para verificar el estado actual del catálogo y sus ramas.
3. **deploy_with_branch_fix.ps1**: Script de despliegue que incluye la corrección del problema de ramas.

## Procedimiento de Verificación y Corrección

Si se encuentra el error "Failed to get full branch details", seguir estos pasos:

1. **Ejecutar el script de corrección**:
   ```
   python fix_catalog_branches.py
   ```
   Este script verificará la estructura del catálogo, listará las ramas disponibles y creará las ramas faltantes.

2. **Verificar el estado actual**:
   ```
   python check_branch_updated.py
   ```
   Este script mostrará información detallada sobre el catálogo y sus ramas.

3. **Desplegar con la corrección**:
   ```
   .\deploy_with_branch_fix.ps1
   ```
   Este script de despliegue incluye la corrección del problema de ramas.

4. **Esperar y verificar**: Después del despliegue, esperar unos minutos y recargar la página de Google Cloud Retail API para verificar que el error ha desaparecido.

## Principales Flujos de Interacción con Retail API

### Importación de Catálogos

Para la importación de catálogos, el sistema:
1. Verifica la estructura del catálogo y sus ramas
2. Convierte los productos al formato requerido por Retail API
3. Utiliza GCS como intermediario para catálogos grandes
4. Realiza la importación mediante la API

### Registro de Eventos de Usuario

El sistema registra eventos de usuario (vistas, compras, etc.) para mejorar las recomendaciones:
1. Valida y normaliza el tipo de evento
2. Construye el objeto UserEvent con la información requerida
3. Para eventos de compra, incluye la información de transacción obligatoria
4. Registra el evento mediante la API

### Obtención de Recomendaciones

Para obtener recomendaciones, el sistema:
1. Valida los parámetros de configuración
2. Construye y envía la solicitud a Retail API
3. Procesa la respuesta de manera robusta para manejar diferentes estructuras
4. Convierte los resultados al formato requerido por la aplicación

## Recomendaciones para evitar el problema en el futuro

1. **Verificar regularmente la estructura del catálogo**:
   - Ejecutar `check_branch_updated.py` periódicamente
   - Monitorear los logs en busca de errores relacionados con las ramas

2. **Mantener la estructura de ramas consistente**:
   - Usar siempre las mismas ramas (0, 1, 2) para diferentes propósitos
   - Documentar claramente la estructura y propósito de cada rama

3. **Implementar validación antes de operaciones críticas**:
   - Verificar la estructura antes de importaciones masivas
   - Validar la existencia de las ramas antes de operaciones de escritura

4. **Monitorear los cambios en la API de Google Cloud Retail**:
   - Estar atento a actualizaciones y cambios en la API
   - Adaptar el código según sea necesario

## Recursos Adicionales

- [Documentación oficial de Google Cloud Retail API](https://cloud.google.com/retail/docs)
- [Guía de Recomendaciones de Productos](https://cloud.google.com/retail/docs/recommendations-overview)
- [Guía de Eventos de Usuario](https://cloud.google.com/retail/docs/user-events)
- [Gestión de Catálogos y Ramas](https://cloud.google.com/retail/docs/catalog-overview)
