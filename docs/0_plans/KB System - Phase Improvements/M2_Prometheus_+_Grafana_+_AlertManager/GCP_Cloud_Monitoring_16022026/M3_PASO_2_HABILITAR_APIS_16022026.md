# 📋 FASE M3 - PASO 2: HABILITACIÓN DE APIS DE GCP

**Proyecto**: Retail Recommender System v2.1.0  
**Fase**: M3 - GCP Cloud Monitoring Integration  
**Documento**: Paso 2 de 8  
**Fecha**: 16 Febrero 2026  
**Tiempo estimado**: 10 minutos  
**Estado**: 📝 EN PROGRESO

---

## 🎯 OBJETIVO DEL PASO 2

Habilitar las APIs necesarias de Google Cloud para que Cloud Monitoring pueda:
1. Recopilar métricas del endpoint `/metrics`
2. Crear dashboards
3. Configurar alertas
4. Almacenar datos históricos

---

## ✅ INFORMACIÓN DEL PROYECTO

```yaml
Project ID: retail-recommendations-449216
Account: yasmani.cascante@gmail.com (ACTIVE)
Region sugerida: us-central1 (Iowa - más cercana, bajo costo)
```

---

## 📋 APIS A HABILITAR

### APIs Necesarias para M3

| API | Propósito | Costo |
|-----|-----------|-------|
| **Cloud Monitoring API** | Recopilar y visualizar métricas | GRATIS (free tier) |
| **Cloud Logging API** | Logs del sistema | GRATIS (50 GiB/mes) |
| **Cloud Trace API** | Tracing distribuido (opcional) | GRATIS (5M spans/mes) |
| **Service Management API** | Gestión de servicios | GRATIS |

**Costo total**: **$0/mes** ✅ (dentro de free tier permanentemente)

---

## 🔧 MÉTODO 1: USANDO GCLOUD CLI (RECOMENDADO)

### Paso 2.1: Verificar proyecto activo

```bash
# Verificar proyecto actual
gcloud config get-value project
# Esperado: retail-recommendations-449216

# Si no es el correcto, cambiarlo
gcloud config set project retail-recommendations-449216
```

### Paso 2.2: Verificar APIs actualmente habilitadas

```bash
# Ver APIs habilitadas
gcloud services list --enabled

# Buscar específicamente monitoring
gcloud services list --enabled | grep -E "monitoring|logging"

# Si no aparecen, continuamos con habilitación
```

### Paso 2.3: Habilitar APIs necesarias

```bash
# Habilitar Cloud Monitoring API
gcloud services enable monitoring.googleapis.com

# Habilitar Cloud Logging API
gcloud services enable logging.googleapis.com

# Habilitar Cloud Trace API (opcional, recomendado)
gcloud services enable cloudtrace.googleapis.com

# Habilitar Service Management API
gcloud services enable servicemanagement.googleapis.com

# Habilitar Service Control API (requerida por Service Management)
gcloud services enable servicecontrol.googleapis.com
```

**Tiempo de habilitación**: ~2-3 minutos

### Paso 2.4: Verificar habilitación exitosa

```bash
# Verificar que todas estén habilitadas
gcloud services list --enabled | grep -E "monitoring|logging|trace|servicemanagement"

# Debe mostrar:
# monitoring.googleapis.com           Cloud Monitoring API
# logging.googleapis.com              Cloud Logging API
# cloudtrace.googleapis.com           Cloud Trace API
# servicemanagement.googleapis.com    Service Management API
# servicecontrol.googleapis.com       Service Control API
```

---

## 🔧 MÉTODO 2: USANDO GCP CONSOLE (ALTERNATIVO)

Si prefieres usar la interfaz web:

### Paso 2.1: Acceder a APIs & Services

1. Abrir: https://console.cloud.google.com/apis/dashboard?project=retail-recommendations-449216
2. Click en **"+ ENABLE APIS AND SERVICES"** (arriba)

### Paso 2.2: Habilitar Cloud Monitoring API

1. Buscar: `Cloud Monitoring API`
2. Click en el resultado
3. Click **"ENABLE"**
4. Esperar ~30 segundos

### Paso 2.3: Habilitar Cloud Logging API

1. Volver a **"+ ENABLE APIS AND SERVICES"**
2. Buscar: `Cloud Logging API`
3. Click **"ENABLE"**

### Paso 2.4: Habilitar Cloud Trace API

1. Volver a **"+ ENABLE APIS AND SERVICES"**
2. Buscar: `Cloud Trace API`
3. Click **"ENABLE"**

### Paso 2.5: Habilitar Service Management API

1. Volver a **"+ ENABLE APIS AND SERVICES"**
2. Buscar: `Service Management API`
3. Click **"ENABLE"**

### Paso 2.6: Verificar en Dashboard

1. Ir a: https://console.cloud.google.com/apis/dashboard?project=retail-recommendations-449216
2. Verificar que aparezcan:
   - Cloud Monitoring API ✅
   - Cloud Logging API ✅
   - Cloud Trace API ✅
   - Service Management API ✅

---

## 🔍 VERIFICACIÓN POST-HABILITACIÓN

### Test 1: Verificar APIs vía gcloud

```bash
# Comando único que verifica todas
gcloud services list --enabled \
  --filter="name:(monitoring.googleapis.com OR logging.googleapis.com OR cloudtrace.googleapis.com OR servicemanagement.googleapis.com)" \
  --format="table(name, title)"

# Salida esperada:
# NAME                              TITLE
# monitoring.googleapis.com         Cloud Monitoring API
# logging.googleapis.com            Cloud Logging API
# cloudtrace.googleapis.com         Cloud Trace API
# servicemanagement.googleapis.com  Service Management API
```

### Test 2: Verificar acceso a Monitoring

```bash
# Intentar listar métricas (debe funcionar ahora)
gcloud monitoring metrics-descriptors list \
  --filter="metric.type:custom.googleapis.com OR metric.type:prometheus.googleapis.com" \
  --limit=5

# Si funciona, las APIs están correctamente habilitadas ✅
# Si falla, revisar permisos en Paso 3
```

### Test 3: Test desde PowerShell (opcional)

```powershell
# Verificar que gcloud reconoce las APIs
gcloud services list --enabled | Select-String "monitoring"

# Debe mostrar:
# monitoring.googleapis.com
```

---

## 📊 COSTOS ESPERADOS

### Free Tier Permanente

```yaml
Cloud Monitoring:
  Ingesta métricas: 150 MiB/mes GRATIS
  Tu ingesta: ~47-98 MiB/mes
  Costo: $0.00 ✅

Cloud Logging:
  Primeros 50 GiB: GRATIS
  Tu estimado: ~5-10 GiB/mes
  Costo: $0.00 ✅

Cloud Trace:
  Primeros 5M spans: GRATIS
  Tu estimado: ~100K spans/mes
  Costo: $0.00 ✅

TOTAL MENSUAL: $0.00 ✅
```

**Garantía**: Permanecerás en free tier indefinidamente con tu tráfico actual.

---

## ⚠️ TROUBLESHOOTING

### Error: "Permission denied"

```bash
# Verificar permisos de tu cuenta
gcloud projects get-iam-policy retail-recommendations-449216 \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:yasmani.cascante@gmail.com"

# Debe mostrar al menos uno de:
# - roles/owner
# - roles/editor
```

**Solución**: Si no tienes permisos, solicita a un admin del proyecto.

### Error: "Quota exceeded"

```bash
# Verificar cuotas del proyecto
gcloud compute project-info describe --project=retail-recommendations-449216

# Si hay límites, contactar soporte GCP (poco probable en free tier)
```

### Error: "API not found"

```bash
# Verificar que el nombre de la API sea correcto
gcloud services list --available | grep monitoring

# Debe mostrar: monitoring.googleapis.com
```

---

## 🎯 PRÓXIMOS PASOS AUTOMÁTICOS

Una vez habilitadas las APIs, GCP automáticamente:

1. ✅ **Crea workspace de monitoring** para tu proyecto
2. ✅ **Configura ingesta de métricas** (listo para Prometheus)
3. ✅ **Habilita dashboards** (crearemos en Paso 4)
4. ✅ **Configura alerting** (configuraremos en Paso 5)

**No requiere acción adicional**, solo esperar ~2-3 minutos.

---

## 📝 VALIDACIÓN FINAL DEL PASO 2

### Checklist de Completación

```
[ ] Cloud Monitoring API habilitada
[ ] Cloud Logging API habilitada  
[ ] Cloud Trace API habilitada (opcional)
[ ] Service Management API habilitada
[ ] Verificación con gcloud exitosa
[ ] Sin errores de permisos
```

### Comando de Verificación Única

```bash
# Ejecutar este comando único
gcloud services list --enabled \
  --filter="name:(monitoring.googleapis.com OR logging.googleapis.com)" \
  --format="value(name)" | wc -l

# Debe mostrar: 2 o más
# Si muestra 2+ → PASO 2 COMPLETO ✅
```

---

## 🔄 ROLLBACK (SI ES NECESARIO)

Si necesitas revertir:

```bash
# Deshabilitar Cloud Monitoring API
gcloud services disable monitoring.googleapis.com

# Deshabilitar Cloud Logging API
gcloud services disable logging.googleapis.com

# NOTA: Datos históricos se preservan 30 días
```

**Recomendación**: NO hacer rollback, las APIs no tienen costo y no afectan tu sistema.

---

## 📊 INFORMACIÓN ÚTIL

### URLs Directas (para tu proyecto)

```
Monitoring Dashboard:
https://console.cloud.google.com/monitoring?project=retail-recommendations-449216

Logging Dashboard:
https://console.cloud.google.com/logs?project=retail-recommendations-449216

Metrics Explorer:
https://console.cloud.google.com/monitoring/metrics-explorer?project=retail-recommendations-449216

APIs Dashboard:
https://console.cloud.google.com/apis/dashboard?project=retail-recommendations-449216
```

### Documentación Oficial

- [Cloud Monitoring Quickstart](https://cloud.google.com/monitoring/docs/quickstart)
- [Prometheus Integration](https://cloud.google.com/stackdriver/docs/managed-prometheus)
- [Pricing Details](https://cloud.google.com/stackdriver/pricing)

---

## ✅ ESTADO DEL PASO 2

**Acciones completadas**:
- [x] Identificación de APIs necesarias
- [x] Documentación de métodos de habilitación
- [x] Comandos de verificación preparados
- [x] Troubleshooting documentado

**Acción requerida del usuario**:
```bash
# Ejecutar SOLO ESTE COMANDO para habilitar todo:
gcloud services enable monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  servicemanagement.googleapis.com \
  servicecontrol.googleapis.com

# Esperar ~2-3 minutos
# Verificar:
gcloud services list --enabled | grep -E "monitoring|logging"
```

---

## 🎯 PRÓXIMO PASO

**Cuando las APIs estén habilitadas**:

→ **PASO 3**: Configuración de IAM y Service Accounts (15 min)

**Preparación para Paso 3**:
- Verificaremos permisos necesarios
- (Opcional) Crearemos Service Account para el servicio
- Configuraremos Workload Identity si usas Cloud Run

---

**ESTADO PASO 2**: ✅ DOCUMENTACIÓN COMPLETA

**ACCIÓN INMEDIATA**: Ejecutar comando de habilitación de APIs y reportar resultado.

¿Continuar con habilitación? (Responde cuando las APIs estén habilitadas)
