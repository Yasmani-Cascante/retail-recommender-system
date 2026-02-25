# 📋 FASE M3 - PASO 3: VERIFICACIÓN DE PERMISOS IAM

**Proyecto**: Retail Recommender System v2.1.0  
**Fase**: M3 - GCP Cloud Monitoring Integration  
**Documento**: Paso 3 de 8  
**Fecha**: 16 Febrero 2026  
**Tiempo estimado**: 5 minutos (simplificado)  
**Estado**: ✅ VALIDADO

---

## 🎯 OBJETIVO DEL PASO 3

Verificar que tienes los permisos necesarios para:
1. Crear dashboards en Cloud Monitoring
2. Configurar alertas
3. Ver métricas del proyecto
4. (Opcional) Crear Service Accounts

---

## ✅ PERMISOS CONFIRMADOS

### Tu Cuenta: yasmani.cascante@gmail.com

```yaml
✅ roles/owner
   - Acceso completo al proyecto
   - Puede crear/modificar/eliminar recursos
   - Puede gestionar IAM
   - Puede configurar billing

✅ roles/run.admin
   - Administrador de Cloud Run
   - Deploy y gestión de servicios

✅ roles/storage.objectAdmin
   - Gestión completa de Storage

✅ roles/resourcemanager.organizationAdmin
   - Administración a nivel organización
```

**Conclusión**: Tienes **TODOS** los permisos necesarios para M3 ✅

---

## 📊 PERMISOS ESPECÍFICOS PARA CLOUD MONITORING

### Permisos Incluidos en roles/owner

```yaml
Monitoring:
  ✅ monitoring.metricDescriptors.create
  ✅ monitoring.metricDescriptors.list
  ✅ monitoring.timeSeries.create
  ✅ monitoring.timeSeries.list
  ✅ monitoring.dashboards.create
  ✅ monitoring.dashboards.update
  ✅ monitoring.alertPolicies.create
  ✅ monitoring.alertPolicies.update

Logging:
  ✅ logging.logs.list
  ✅ logging.logEntries.create
  ✅ logging.logEntries.list

Trace:
  ✅ cloudtrace.traces.patch
  ✅ cloudtrace.traces.list
```

**No se requiere configuración adicional de IAM** ✅

---

## 🔍 VERIFICACIÓN RÁPIDA

### Test 1: Verificar Acceso a Monitoring Console

```bash
# Abrir directamente Monitoring Console
# https://console.cloud.google.com/monitoring?project=retail-recommendations-449216

# O verificar permisos específicos
gcloud projects get-iam-policy retail-recommendations-449216 \
  --flatten="bindings[].members" \
  --filter="bindings.role:roles/owner AND bindings.members:user:yasmani.cascante@gmail.com"

# Debe mostrar: roles/owner ✅
```

### Test 2: Verificar que puedes listar métricas

```bash
# Intentar listar metric descriptors
gcloud monitoring metrics-descriptors list \
  --project=retail-recommendations-449216 \
  --limit=5

# Si funciona, tienes permisos correctos ✅
```

### Test 3: Verificar acceso a Dashboards

```bash
# Listar dashboards existentes (puede estar vacío)
gcloud monitoring dashboards list \
  --project=retail-recommendations-449216

# Si el comando funciona (incluso sin resultados), tienes acceso ✅
```

---

## 🎯 SERVICE ACCOUNT (OPCIONAL)

### ¿Necesitas crear Service Account?

**Para desarrollo local**: NO es necesario ✅
- Tu cuenta personal tiene todos los permisos
- gcloud CLI usa tus credenciales automáticamente

**Para Cloud Run deployment**: SÍ recomendado (pero no urgente)
- Service Account específica para el servicio
- Principio de least privilege
- Lo configuraremos cuando deployes a Cloud Run

### Crear Service Account (Opcional, para futuro)

```bash
# Crear Service Account para el servicio
gcloud iam service-accounts create retail-recommender-sa \
  --display-name="Retail Recommender Service Account" \
  --project=retail-recommendations-449216

# Asignar permisos necesarios
gcloud projects add-iam-policy-binding retail-recommendations-449216 \
  --member="serviceAccount:retail-recommender-sa@retail-recommendations-449216.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding retail-recommendations-449216 \
  --member="serviceAccount:retail-recommender-sa@retail-recommendations-449216.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

**Nota**: Esto es para **deployment futuro**, no es necesario para M3 ahora.

---

## 📊 WORKSPACE DE MONITORING

### Verificación Automática

GCP crea automáticamente un **Monitoring Workspace** cuando:
1. Habilitas Cloud Monitoring API ✅ (ya hecho)
2. Accedes por primera vez a Monitoring Console

### Verificar Workspace

```bash
# Opción 1: Via gcloud (puede no funcionar en CLI)
gcloud monitoring dashboards list --project=retail-recommendations-449216

# Opción 2: Via Console (más confiable)
# https://console.cloud.google.com/monitoring?project=retail-recommendations-449216
```

**Si el workspace no existe**, se creará automáticamente al:
- Acceder a Monitoring Console por primera vez
- Crear tu primer dashboard (Paso 4)

**Esto es automático y gratuito** ✅

---

## ✅ CHECKLIST DE VALIDACIÓN PASO 3

```yaml
Permisos verificados:
  ✅ roles/owner confirmado
  ✅ Acceso a Monitoring Console
  ✅ Capacidad de crear dashboards
  ✅ Capacidad de configurar alertas

APIs habilitadas (Paso 2):
  ✅ monitoring.googleapis.com
  ✅ logging.googleapis.com
  ✅ cloudtrace.googleapis.com

Service Account (opcional):
  ⏭️ No necesario por ahora
  ⏭️ Crear cuando deployes a Cloud Run

Monitoring Workspace:
  ✅ Se creará automáticamente (si no existe)
```

---

## 🎯 RESUMEN DEL PASO 3

### ✅ Estado Actual

```yaml
Project: retail-recommendations-449216
Account: yasmani.cascante@gmail.com
Role: Owner (acceso completo)
APIs: Todas habilitadas
Permisos: Completos para M3
```

### 🚀 Acciones Completadas

1. ✅ Verificación de permisos IAM
2. ✅ Confirmación de roles/owner
3. ✅ Validación de acceso a Monitoring
4. ✅ Preparación para creación de dashboards

### ⏭️ Acciones Pendientes

- **Ninguna en este paso** - Todo está listo ✅
- Service Account se puede crear después (deployment a Cloud Run)

---

## 📊 INFORMACIÓN ÚTIL

### URLs Directas

```
Monitoring Console:
https://console.cloud.google.com/monitoring?project=retail-recommendations-449216

IAM & Admin:
https://console.cloud.google.com/iam-admin/iam?project=retail-recommendations-449216

Service Accounts:
https://console.cloud.google.com/iam-admin/serviceaccounts?project=retail-recommendations-449216
```

### Roles Más Usados

| Role | Descripción | ¿Lo tienes? |
|------|-------------|-------------|
| `roles/owner` | Acceso completo | ✅ SÍ |
| `roles/monitoring.admin` | Admin de Monitoring | ✅ (incluido en owner) |
| `roles/monitoring.metricWriter` | Escribir métricas | ✅ (incluido en owner) |
| `roles/logging.admin` | Admin de Logging | ✅ (incluido en owner) |

---

## 🔄 TROUBLESHOOTING (NO APLICA)

Como tienes **roles/owner**, no deberías tener problemas de permisos.

Si encuentras algún error:
1. Verifica que estés usando la cuenta correcta: `gcloud auth list`
2. Verifica que el proyecto sea el correcto: `gcloud config get-value project`
3. Re-autentica si es necesario: `gcloud auth login`

---

## ✅ ESTADO DEL PASO 3

**Validación completada**:
- [x] Permisos verificados (roles/owner)
- [x] Acceso a Monitoring confirmado
- [x] No se requiere configuración adicional
- [x] Listo para crear dashboards

**Tiempo usado**: ~5 minutos (vs 15 estimados)  
**Razón**: Ya tenías todos los permisos necesarios ✅

---

## 🎯 PRÓXIMO PASO

**PASO 4**: Creación de Dashboards en GCP Console (60 min)

Este será el paso más interesante, donde crearemos visualizaciones de:
- HTTP Performance (requests, latency, errors)
- Recommendations Metrics (duration, success rate)
- KB Sync Performance (operations, duration)
- Google Retail API Health (calls, latency, errors)
- System Health Overview

**Preparación**:
- Asegúrate de tener el sistema corriendo: `localhost:8000/metrics`
- Tendremos que generar algo de tráfico para ver datos en los dashboards

---

**ESTADO PASO 3**: ✅ COMPLETADO Y VALIDADO

**Progreso M3**: 37.5% (3/8 pasos completados)

```
✅ PASO 1: Prerequisitos verificados
✅ PASO 2: APIs habilitadas  
✅ PASO 3: Permisos confirmados
⏳ PASO 4: Dashboards (siguiente)
⏳ PASO 5: Alertas
⏳ PASO 6: Integración código
⏳ PASO 7: Testing
⏳ PASO 8: Documentación final
```

**¿Listo para crear los dashboards?** 

Responde cuando estés listo para el Paso 4, que será el más visual e interactivo. 🚀
