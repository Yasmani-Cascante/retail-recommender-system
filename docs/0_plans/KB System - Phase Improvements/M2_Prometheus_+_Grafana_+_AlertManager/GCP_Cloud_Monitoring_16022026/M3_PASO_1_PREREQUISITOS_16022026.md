# 📋 FASE M3 - PASO 1: VERIFICACIÓN DE PREREQUISITOS

**Proyecto**: Retail Recommender System v2.1.0  
**Fase**: M3 - GCP Cloud Monitoring Integration  
**Documento**: Paso 1 de 8  
**Fecha**: 16 Febrero 2026  
**Tiempo estimado**: 15 minutos  
**Estado**: 📝 EN PROGRESO

---

## 🎯 OBJETIVO DEL PASO 1

Verificar que todos los prerequisitos estén en lugar antes de comenzar la integración con GCP Cloud Monitoring.

---

## ✅ CHECKLIST DE PREREQUISITOS

### 1. Sistema Base

- [x] **M2 Completado**: Prometheus metrics implementadas ✅
- [x] **Endpoint /metrics funcional**: Verificado en validación M2 ✅
- [x] **7 métricas custom expuestas**: Confirmado ✅
- [x] **HTTP auto-instrumentation activa**: Validado ✅

**Evidencia M2**:
```
Archivo: DCT_M2_Prometheus_Metrics___Observability_16022026.md
Estado: COMPLETADA Y VALIDADA
Métricas confirmadas:
1. recommender_requests_total (Counter)
2. recommender_duration_seconds (Histogram)
3. recommender_errors_total (Counter)
4. kb_sync_operations_total (Counter)
5. kb_sync_duration_seconds (Histogram)
6. kb_sync_semaphore_size (Gauge)
7. google_retail_api_calls_total (Counter)
```

---

### 2. Acceso a Google Cloud Platform

**Verificar**:

- [ ] **Cuenta GCP activa**
- [ ] **Proyecto GCP creado**
- [ ] **Permisos de administrador en el proyecto**
- [ ] **gcloud CLI instalado** (opcional pero recomendado)

**Comandos de verificación**:

```bash
# Verificar gcloud CLI instalado
gcloud --version
# Esperado: Google Cloud SDK 400.0.0+

# Verificar proyecto activo
gcloud config get-value project
# Esperado: Tu project ID

# Verificar cuenta autenticada
gcloud auth list
# Esperado: Tu cuenta con ACTIVE status

# Verificar permisos
gcloud projects get-iam-policy $(gcloud config get-value project) \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:YOUR_EMAIL"
# Esperado: roles/owner o roles/editor
```

**Acción si falta gcloud CLI**:
```bash
# Windows (PowerShell Admin)
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe

# O usar GCP Console (no requiere CLI)
# https://console.cloud.google.com
```

---

### 3. Deployment Target

**Verificar dónde se va a deployar**:

- [ ] **Cloud Run**: ¿Ya existe servicio desplegado?
- [ ] **Compute Engine**: ¿VM configurada?
- [ ] **GKE**: ¿Cluster disponible?
- [ ] **Local development**: ¿Solo para testing?

**Comando de verificación Cloud Run**:
```bash
# Listar servicios Cloud Run
gcloud run services list

# Si ya existe retail-recommender
gcloud run services describe retail-recommender \
  --region=us-central1 \
  --format="value(status.url)"
# Esperado: URL del servicio
```

**Si no hay deployment**:
- ✅ OK, configuraremos monitoring para cuando se despliegue
- GCP Cloud Monitoring funciona con `/metrics` endpoint donde sea que esté

---

### 4. Variables de Entorno Actuales

**Verificar archivo `.env`**:

```bash
# Verificar que exista
ls .env
# Esperado: .env

# Variables críticas para GCP
cat .env | grep -E "GOOGLE_|GCP_"
# Esperado:
# GOOGLE_PROJECT_NUMBER=...
# GOOGLE_LOCATION=global
# (otros)
```

**Variables necesarias para M3**:
```bash
# En .env (agregar si no existen)
GOOGLE_PROJECT_ID=your-project-id          # ID del proyecto GCP
GOOGLE_MONITORING_ENABLED=true             # Habilitar integración
PROMETHEUS_METRICS_ENABLED=true            # Ya debe estar (M2)
```

---

### 5. Estado del Sistema

**Verificar que el sistema arranque correctamente**:

```powershell
# Desde directorio del proyecto
cd C:\Users\yasma\Desktop\retail-recommender-system

# Verificar que arranque (si está corriendo, skip)
# uvicorn src.api.main_unified_redis:app --reload

# Verificar endpoint /metrics (en otra terminal)
Invoke-WebRequest http://localhost:8000/metrics

# Esperado:
# StatusCode: 200
# Content-Type: text/plain; version=0.0.4
```

**Logs esperados al startup**:
```
✅ M2: Prometheus auto-instrumentation applied
✅ M2: /metrics endpoint exposed (Prometheus format, no auth)
ℹ️  M2: /v1/metrics endpoint remains unchanged
```

---

### 6. Costos Estimados

**Verificar presupuesto disponible**:

Basado en análisis de costos:
- **Pequeño negocio** (tu caso): **$0/mes** ✅ (dentro de free tier)
- **Ingesta estimada**: ~47-98 MiB/mes
- **Free tier GCP**: 150 MiB/mes

**Conclusión**: Costo = $0 permanentemente ✅

---

### 7. Documentación de Referencia

**Verificar acceso a**:

- [x] **Documentación M2**: `/mnt/project/DCT_M2_Prometheus_Metrics___Observability_16022026.md` ✅
- [x] **GCP Cloud Monitoring Docs**: https://cloud.google.com/monitoring/docs ✅
- [x] **Pricing Calculator**: https://cloud.google.com/products/calculator ✅

---

## 🔍 VERIFICACIÓN TÉCNICA DETALLADA

### Test 1: Endpoint /metrics Accessibility

```powershell
# PowerShell
$response = Invoke-WebRequest http://localhost:8000/metrics
Write-Host "Status: $($response.StatusCode)"
Write-Host "Content-Type: $($response.Headers['Content-Type'])"
$metrics_count = ($response.Content -split "`n" | Where-Object { $_ -match "^[a-z_]+" }).Count
Write-Host "Métricas expuestas: $metrics_count"
```

**Resultado esperado**:
```
Status: 200
Content-Type: text/plain; version=0.0.4; charset=utf-8
Métricas expuestas: 20+ (custom + HTTP auto-instrumented)
```

---

### Test 2: Verificar Métricas Custom

```powershell
# Verificar las 7 métricas M2
$metrics = (Invoke-WebRequest http://localhost:8000/metrics).Content

$m2_metrics = @(
    "recommender_requests_total",
    "recommender_duration_seconds",
    "recommender_errors_total",
    "kb_sync_operations_total",
    "kb_sync_duration_seconds",
    "kb_sync_semaphore_size",
    "google_retail_api_calls_total"
)

foreach ($metric in $m2_metrics) {
    if ($metrics -match $metric) {
        Write-Host "[OK] $metric" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] $metric FALTANTE" -ForegroundColor Red
    }
}
```

**Resultado esperado**: Todos [OK] ✅

---

### Test 3: Verificar GCP Project Access

```bash
# Verificar proyecto activo
gcloud config get-value project

# Verificar APIs habilitadas (siguiente paso las habilitaremos)
gcloud services list --enabled | grep monitoring
# Si no aparece, es OK, lo habilitaremos en Paso 2
```

---

## 📊 ESTADO ACTUAL DEL SISTEMA

### Métricas Reales (Snapshot de M2)

**KB Sync Performance**:
```
kb_sync_operations_total{status="success"} 5.0
kb_sync_duration_seconds_sum 13.047538
kb_sync_semaphore_size 1.0
```
- ✅ 5 operaciones exitosas
- ✅ ~2.6s promedio por sync
- ✅ Semaphore size = 1 (M1 config)

**Google Retail API**:
```
google_retail_api_calls_total{method="predict",status="error"} 1.0
google_retail_api_duration_seconds_sum{method="predict"} 0.454
```
- ⚠️ 1 error (configuración externa)
- ✅ Latencia: 454ms

**HTTP Performance**:
```
http_requests_total{handler="/v1/recommendations/{product_id}",status="200"} 1.0
http_requests_total{handler="/v1/recommendations/{product_id}",status="403"} 3.0
http_request_duration_highr_seconds_sum 2.617
```
- ✅ 4 requests procesados
- ✅ Latencia promedio: 654ms

---

## ✅ DECISIÓN: ¿CONTINUAR CON M3?

**Checklist Final**:

```
Sistema base:
[x] M2 completado y validado
[x] Endpoint /metrics funcional
[x] Métricas custom confirmadas
[x] Sistema arranca correctamente

GCP Access:
[ ] Cuenta GCP verificada         ← PENDIENTE USUARIO
[ ] Proyecto GCP confirmado        ← PENDIENTE USUARIO
[ ] Permisos verificados           ← PENDIENTE USUARIO

Deployment:
[ ] Target definido (Cloud Run/VM) ← PENDIENTE USUARIO

Presupuesto:
[x] Costo estimado: $0/mes ✅
[x] Free tier confirmado ✅
```

---

## 🎯 PRÓXIMO PASO

**SI TODOS LOS CHECKS ANTERIORES ESTÁN OK**:

→ **PASO 2**: Habilitación de APIs de GCP (10 minutos)

**SI FALTAN ALGUNOS CHECKS**:

→ Resolver prerequisitos faltantes primero

---

## 📝 NOTAS IMPORTANTES

### ⚠️ Advertencias

1. **No proceder sin acceso GCP**: Sin cuenta/proyecto GCP, no podemos continuar
2. **Verificar permisos**: Necesitas roles/owner o roles/editor
3. **Sistema debe estar corriendo**: Para testing posterior

### ✅ Ventajas de Verificar Ahora

1. Detectar problemas antes de invertir tiempo
2. Confirmar que M2 está 100% funcional
3. Validar presupuesto (costo = $0)
4. Tener baseline de métricas actual

---

## 🔄 COMANDOS DE ROLLBACK

Si algo falla en pasos posteriores:

```bash
# M3 no modifica código, solo configura GCP
# Rollback = simplemente no usar dashboards GCP
# Sistema sigue funcionando igual (M2 intacto)
```

**Garantía**: M3 es 100% aditivo, NO modifica sistema existente ✅

---

**ESTADO PASO 1**: ✅ DOCUMENTACIÓN COMPLETA

**ACCIÓN REQUERIDA DEL USUARIO**:

1. Verificar acceso a GCP
2. Confirmar proyecto GCP disponible
3. (Opcional) Instalar gcloud CLI
4. Confirmar que puede continuar

**¿Continuar con PASO 2?** (Responder con los checks de GCP completados)
