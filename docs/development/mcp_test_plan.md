# Plan de Pruebas para Integración MCP

## Objetivo

Este plan define las pruebas necesarias para validar la correcta integración y funcionamiento del Market Context Protocol (MCP) en el sistema de recomendaciones.

## Tipos de Pruebas

### 1. Pruebas Unitarias

#### Componentes a probar:

- **ShopifyMCPClient**
  - Extracción de intenciones
  - Procesamiento de consultas
  - Gestión de errores

- **MarketContextManager**
  - Detección de mercado
  - Obtención de configuraciones
  - Adaptación de recomendaciones

- **MarketAwareProductCache**
  - Almacenamiento y recuperación con TTL
  - Invalidación selectiva
  - Pre-carga de caché

### 2. Pruebas de Integración

#### Flujos a probar:

- **Procesamiento Conversacional End-to-End**
  - Desde consulta de usuario hasta respuesta con recomendaciones
  - Verificación de adaptación por mercado
  - Persistencia de sesión conversacional

- **Caché Market-Aware**
  - Funcionamiento del caché en diferentes mercados
  - Estrategias de fallback
  - Rendimiento con diferentes patrones de acceso

- **Comunicación Python-Node.js**
  - Latencia de comunicación
  - Manejo de errores
  - Reconexión automática

### 3. Pruebas de Rendimiento

#### Métricas a evaluar:

- **Latencia**
  - Tiempo de respuesta promedio por mercado
  - Distribución de percentiles (p50, p90, p99)
  - Identificación de cuellos de botella

- **Throughput**
  - Solicitudes por segundo máximas
  - Degradación bajo carga
  - Límites de escalabilidad

- **Utilización de recursos**
  - CPU, memoria, red
  - Impacto en otros componentes
  - Eficiencia de caché

## Casos de Prueba

### Pruebas de Funcionalidad

1. **TC-MCP-F001: Conversación básica**
   - **Descripción**: Verificar procesamiento de consulta simple y respuesta
   - **Pasos**:
     1. Enviar consulta "Busco una camisa azul"
     2. Verificar respuesta conversacional
     3. Verificar recomendaciones retornadas
   - **Resultado esperado**: Respuesta coherente y recomendaciones relevantes

2. **TC-MCP-F002: Adaptación por mercado**
   - **Descripción**: Verificar adaptación de recomendaciones según mercado
   - **Pasos**:
     1. Enviar misma consulta con diferentes mercados (US, ES, MX, CL)
     2. Comparar precios, moneda y recomendaciones
   - **Resultado esperado**: Precios adaptados, moneda correcta, preferencias culturales aplicadas

3. **TC-MCP-F003: Detección de intención**
   - **Descripción**: Verificar extracción correcta de intenciones
   - **Pasos**:
     1. Enviar consultas con diferentes intenciones (búsqueda, comparación, presupuesto)
     2. Verificar intención detectada
   - **Resultado esperado**: Intención correctamente identificada con alta confianza

4. **TC-MCP-F004: Manejo de sesión**
   - **Descripción**: Verificar persistencia de contexto conversacional
   - **Pasos**:
     1. Iniciar conversación con consulta inicial
     2. Continuar con consulta de seguimiento usando mismo session_id
   - **Resultado esperado**: Contexto preservado entre mensajes

### Pruebas de Rendimiento

1. **TC-MCP-P001: Latencia bajo carga**
   - **Descripción**: Medir latencia con diferentes niveles de carga
   - **Pasos**:
     1. Enviar 1, 10, 50, 100 RPS
     2. Medir tiempos de respuesta
   - **Resultado esperado**: Latencia <500ms para p95 incluso a 50 RPS

2. **TC-MCP-P002: Efectividad de caché**
   - **Descripción**: Medir ratio de hit de caché por mercado
   - **Pasos**:
     1. Ejecutar conjunto de consultas repetidas
     2. Verificar métricas de caché
   - **Resultado esperado**: Ratio de hit >70% después de warmup

3. **TC-MCP-P003: Prueba de resistencia**
   - **Descripción**: Evaluar comportamiento bajo carga sostenida
   - **Pasos**:
     1. Mantener carga de 30 RPS durante 30 minutos
     2. Monitorear recursos y métricas
   - **Resultado esperado**: Sin degradación de performance o memory leaks

### Pruebas de Resiliencia

1. **TC-MCP-R001: Recuperación de errores de Node.js**
   - **Descripción**: Verificar recuperación ante fallos del bridge Node.js
   - **Pasos**:
     1. Forzar fallo en Node.js bridge
     2. Enviar consultas durante recuperación
   - **Resultado esperado**: Reconexión automática y mensajes de error apropiados

2. **TC-MCP-R002: Degradación controlada**
   - **Descripción**: Verificar comportamiento con componentes degradados
   - **Pasos**:
     1. Deshabilitar servicios (Redis, Node.js, etc.)
     2. Verificar respuestas del sistema
   - **Resultado esperado**: Fallbacks apropiados, mensajes de error útiles

## Herramientas de Prueba

- **Pruebas unitarias**: pytest
- **Pruebas de integración**: pytest con fixtures HTTP
- **Pruebas de rendimiento**: Locust, Grafana k6
- **Monitoreo**: Prometheus + Grafana

## Plan de Ejecución

1. **Pruebas unitarias**: Ejecución diaria, integradas en CI/CD
2. **Pruebas de integración**: Ejecución en cada PR que afecte componentes MCP
3. **Pruebas de rendimiento**: Ejecución semanal y antes de cada release

## Criterios de Aceptación

- Todas las pruebas unitarias y de integración pasan
- Tiempo de respuesta promedio <250ms para operaciones MCP
- Ratio de hit de caché >70% en operación normal
- Capacidad de manejar al menos 50 RPS sin degradación
- Detección correcta de intenciones en >85% de los casos
