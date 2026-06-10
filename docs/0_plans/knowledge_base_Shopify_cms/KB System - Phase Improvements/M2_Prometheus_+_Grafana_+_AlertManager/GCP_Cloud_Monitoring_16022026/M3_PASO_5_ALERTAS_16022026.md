# 🚨 FASE M3 - PASO 5: CONFIGURACIÓN DE ALERTAS

**Proyecto**: Retail Recommender System v2.1.0  
**Fase**: M3 - GCP Cloud Monitoring Integration  
**Documento**: Paso 5 de 8  
**Fecha**: 16 Febrero 2026  
**Tiempo estimado**: 30 minutos  
**Estado**: 🚨 EN PROGRESO

---

## 🎯 OBJETIVO DEL PASO 5

Configurar **alertas proactivas** que notifiquen automáticamente cuando:
1. El sistema tiene alta tasa de errores
2. La latencia excede SLOs
3. El servicio está caído
4. KB Sync falla repetidamente
5. Google Retail API presenta problemas

---

## 🚨 ALERTAS A CREAR

### Alertas Críticas (Pager/Email inmediato)

| # | Alerta | Condición | Severidad | Notificación |
|---|--------|-----------|-----------|--------------|
| 1 | Service Down | up == 0 por >1min | Critical | Email + Slack |
| 2 | High Error Rate | Error rate >5% por >5min | Critical | Email + Slack |
| 3 | Extreme Latency | p95 >5s por >5min | Critical | Email |

### Alertas de Warning (Email)

| # | Alerta | Condición | Severidad | Notificación |
|---|--------|-----------|-----------|--------------|
| 4 | Elevated Latency | p95 >2s por >10min | Warning | Email |
| 5 | KB Sync Failures | Failure rate >10% por >15min | Warning | Email |

---

## 📋 PREPARACIÓN

### Paso 5.1: Acceder a Alerting

1. **Abrir GCP Console**:
   ```
   https://console.cloud.google.com/monitoring/alerting?project=retail-recommendations-449216
   ```

2. **Verificar proyecto**: `retail-recommendations-449216`

3. **Navegar**: Monitoring → Alerting

---

## 📧 PASO 5.2: CONFIGURAR NOTIFICATION CHANNELS

Antes de crear alertas, configuramos dónde enviar notificaciones.

### Email Notification Channel

1. **Alerting** → **Notification Channels** (arriba)

2. Click **"ADD NEW"**

3. **Configurar Email**:
   ```
   Channel Type: Email
   Display Name: Yasmani - Primary Email
   Email Address: yasmani.cascante@gmail.com
   
   Description: Primary contact for critical alerts
   ```

4. **Save**

5. **Verificar email**:
   - Revisa inbox
   - Click en link de verificación de GCP
   - Confirmar

### Slack Notification Channel (Opcional)

Si tienes Slack workspace:

1. **ADD NEW** → **Slack**

2. **Connect Slack**:
   - Authorize GCP app
   - Select channel (ej: `#retail-recommender-alerts`)

3. **Display Name**: `Retail Recommender - Slack Alerts`

4. **Save**

**Si no tienes Slack**: Skip, usaremos solo Email

---

## 🚨 ALERTA 1: SERVICE DOWN (CRÍTICA)

### Paso 5.3: Crear Alerta Service Down

1. **Alerting** → **"+ CREATE POLICY"**

2. **Configurar Condición**:

   **Step 1: Select a metric**
   ```
   Metric: up (Prometheus metric)
   Resource type: Prometheus Target
   Filter: job = "retail-recommender"
   ```

   **Step 2: Configure alert trigger**
   ```
   Condition type: Threshold
   Alert trigger: Any time series violates
   Threshold position: Below threshold
   Threshold value: 1
   
   For: 1 minute (most recent value)
   ```

   **Significado**: Alerta si `up` < 1 por más de 1 minuto (servicio caído)

3. **Next**

4. **Configure notifications and finalize**:
   ```
   Alert policy name: [CRITICAL] Service Down
   
   Documentation (Email template):
   ---
   🚨 CRITICAL ALERT: Retail Recommender Service is DOWN
   
   The service has been unreachable for over 1 minute.
   
   IMMEDIATE ACTION REQUIRED:
   1. Check Cloud Run logs
   2. Verify deployment status
   3. Check recent deployments
   4. Escalate if not resolved in 5 minutes
   
   Runbook: https://wiki.company.com/retail-recommender/runbooks/service-down
   
   Dashboard: https://console.cloud.google.com/monitoring/dashboards?project=retail-recommendations-449216
   ---
   
   Notification channels:
   ☑ Yasmani - Primary Email
   ☑ Retail Recommender - Slack Alerts (if configured)
   
   Auto-close duration: 7 days
   ```

5. **Create Policy** ✅

---

## 🚨 ALERTA 2: HIGH ERROR RATE (CRÍTICA)

### Paso 5.4: Crear Alerta High Error Rate

1. **"+ CREATE POLICY"**

2. **Configurar Condición**:

   **Metric**:
   ```
   Use PromQL query:
   
   sum(rate(http_requests_total{status=~"5.."}[5m]))
   /
   sum(rate(http_requests_total[5m]))
   * 100
   ```

   **Alert trigger**:
   ```
   Condition type: Threshold
   Alert trigger: Any time series violates
   Threshold position: Above threshold
   Threshold value: 5
   
   For: 5 minutes
   ```

   **Significado**: Alerta si error rate > 5% durante 5 minutos continuos

3. **Next**

4. **Configure notifications**:
   ```
   Alert policy name: [CRITICAL] High HTTP Error Rate
   
   Documentation:
   ---
   🚨 CRITICAL: HTTP Error Rate Exceeding 5%
   
   Current error rate is above acceptable threshold (5%).
   This indicates a systemic issue affecting users.
   
   TROUBLESHOOTING STEPS:
   1. Check error logs in Cloud Logging
   2. Review recent deployments (rollback if needed)
   3. Verify external dependencies (Redis, Google Retail API)
   4. Check system resources (CPU, memory)
   
   Dashboard: [link to Dashboard 1]
   Logs: https://console.cloud.google.com/logs?project=retail-recommendations-449216
   ---
   
   Notification channels:
   ☑ Yasmani - Primary Email
   ☑ Slack Alerts
   
   Auto-close: 7 days
   ```

5. **Create Policy** ✅

---

## 🚨 ALERTA 3: EXTREME LATENCY (CRÍTICA)

### Paso 5.5: Crear Alerta Extreme Latency

1. **"+ CREATE POLICY"**

2. **PromQL Query**:
   ```
   histogram_quantile(0.95,
     rate(http_request_duration_seconds_bucket[5m])
   )
   ```

3. **Alert trigger**:
   ```
   Threshold: Above 5 seconds
   Duration: 5 minutes
   ```

4. **Notifications**:
   ```
   Name: [CRITICAL] Extreme API Latency (p95 > 5s)
   
   Documentation:
   ---
   🚨 CRITICAL: API Latency Extremely High
   
   95th percentile latency is above 5 seconds.
   This severely impacts user experience.
   
   IMMEDIATE ACTIONS:
   1. Check Redis cache performance
   2. Review slow query logs
   3. Verify Google Retail API latency
   4. Check if TF-IDF model is loaded
   5. Monitor active requests (possible overload)
   
   Normal p95 target: <2 seconds
   Current threshold: >5 seconds (250% over target)
   ---
   
   Channels: Email + Slack
   ```

5. **Create** ✅

---

## ⚠️ ALERTA 4: ELEVATED LATENCY (WARNING)

### Paso 5.6: Crear Alerta Elevated Latency

1. **"+ CREATE POLICY"**

2. **PromQL**:
   ```
   histogram_quantile(0.95,
     rate(http_request_duration_seconds_bucket[5m])
   )
   ```

3. **Alert trigger**:
   ```
   Threshold: Above 2 seconds
   Duration: 10 minutes
   ```

4. **Notifications**:
   ```
   Name: [WARNING] Elevated API Latency (p95 > 2s)
   
   Documentation:
   ---
   ⚠️ WARNING: API Latency Above Target
   
   95th percentile latency exceeds SLO target of 2 seconds.
   
   INVESTIGATION STEPS:
   1. Monitor trend (is it increasing?)
   2. Check cache hit rates
   3. Review concurrent request load
   4. Verify external API latencies
   
   If latency continues rising → May escalate to CRITICAL
   
   Target: <2s
   Current: >2s
   Critical threshold: >5s
   ---
   
   Channels: Email only (no Slack for warnings)
   ```

5. **Create** ✅

---

## ⚠️ ALERTA 5: KB SYNC FAILURES (WARNING)

### Paso 5.7: Crear Alerta KB Sync Failures

1. **"+ CREATE POLICY"**

2. **PromQL**:
   ```
   sum(rate(kb_sync_operations_total{status="failed"}[15m]))
   /
   sum(rate(kb_sync_operations_total[15m]))
   * 100
   ```

3. **Alert trigger**:
   ```
   Threshold: Above 10
   Duration: 15 minutes
   ```

4. **Notifications**:
   ```
   Name: [WARNING] Knowledge Base Sync Failures
   
   Documentation:
   ---
   ⚠️ WARNING: KB Sync Failure Rate High
   
   More than 10% of KB sync operations are failing.
   This may impact recommendation freshness.
   
   TROUBLESHOOTING:
   1. Check Notion API connectivity
   2. Verify Notion page access permissions
   3. Review KB sync logs for specific errors
   4. Check semaphore configuration (M1 optimization)
   
   Impact:
   - Recommendations may use stale data
   - Market-specific content may be outdated
   
   Logs query:
   resource.type="cloud_run_revision"
   jsonPayload.component="kb_sync"
   severity="ERROR"
   ---
   
   Channels: Email
   ```

5. **Create** ✅

---

## 📊 PASO 5.8: CONFIGURAR ALERT POLICIES ADICIONALES

### Bonus: Google Retail API Error Alert

1. **"+ CREATE POLICY"**

2. **PromQL**:
   ```
   sum(rate(google_retail_api_calls_total{status="error"}[5m]))
   /
   sum(rate(google_retail_api_calls_total[5m]))
   * 100
   ```

3. **Threshold**: >20% por 10 minutos

4. **Name**: `[WARNING] Google Retail API High Error Rate`

5. **Create**

---

## 🔔 PASO 5.9: CONFIGURAR NOTIFICATION SETTINGS

### Alert Policy Settings Globales

1. **Alerting** → **Settings** (arriba a la derecha)

2. **Configurar**:
   ```yaml
   Default notification channels:
     - Yasmani - Primary Email
   
   Snooze duration: 1 hour
   
   Auto-close alerts after: 7 days
   
   Alert grouping: By policy name
   
   Notification rate limit:
     - Critical: No limit (always send)
     - Warning: Max 1 per hour
   
   Incident creation: Enabled
   ```

3. **Save**

---

## 📧 PASO 5.10: PERSONALIZAR EMAIL TEMPLATES

### Template para Alertas Críticas

```html
Subject: 🚨 [CRITICAL] ${ALERT_POLICY_NAME}

Body:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 CRITICAL ALERT - IMMEDIATE ACTION REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Alert: ${ALERT_POLICY_NAME}
Project: retail-recommendations-449216
Time: ${INCIDENT_START_TIME}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${DOCUMENTATION}

Current Value: ${OBSERVED_VALUE}
Threshold: ${THRESHOLD_VALUE}
Duration: ${INCIDENT_DURATION}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 QUICK LINKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Dashboard: https://console.cloud.google.com/monitoring/dashboards?project=retail-recommendations-449216

Logs: https://console.cloud.google.com/logs/query?project=retail-recommendations-449216

Incident: ${INCIDENT_URL}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Aplicar**:
- Settings → Notification templates → Critical alerts

---

## 🔍 PASO 5.11: TEST DE ALERTAS (Opcional)

### Simular Alerta de Service Down

```bash
# Detener el servicio temporalmente para testear alerta
# (Solo en development/staging, NO EN PRODUCCIÓN)

# Método 1: Detener localmente
# Ctrl+C en terminal donde corre uvicorn
# Esperar 2 minutos → Debe llegar email

# Método 2: Cloud Run (si está desplegado)
gcloud run services update retail-recommender \
  --region=us-central1 \
  --min-instances=0 \
  --max-instances=0 \
  --project=retail-recommendations-449216

# Esperar 2 minutos
# Verificar email recibido
# Restaurar:
gcloud run services update retail-recommender \
  --region=us-central1 \
  --min-instances=1 \
  --max-instances=10 \
  --project=retail-recommendations-449216
```

**NO ejecutar ahora** (solo cuando tengas deployment)

---

## 📊 PASO 5.12: VERIFICAR ALERTAS CREADAS

### Lista de Alertas

```bash
# Listar todas las alertas
gcloud alpha monitoring policies list \
  --project=retail-recommendations-449216 \
  --format="table(displayName, enabled, conditions[0].conditionThreshold.thresholdValue)"

# Esperado:
# [CRITICAL] Service Down                     True  1
# [CRITICAL] High HTTP Error Rate             True  5
# [CRITICAL] Extreme API Latency              True  5
# [WARNING] Elevated API Latency              True  2
# [WARNING] Knowledge Base Sync Failures      True  10
```

### Verificar en Console

1. **Alerting** → **Policies**

2. **Debe mostrar 5 policies** (o 6 si creaste la bonus)

3. **Verificar**:
   - ✅ Todas habilitadas (Enabled = True)
   - ✅ Notification channels configurados
   - ✅ Documentation presente

---

## 🎯 MEJORES PRÁCTICAS APLICADAS

### Estrategia de Alerting

```yaml
Severidades:
  CRITICAL:
    - Impacto inmediato en usuarios
    - Requiere acción en <5 minutos
    - Notificación: Email + Slack + (opcional) PagerDuty
    - Ejemplos: Service down, high error rate
  
  WARNING:
    - Degradación de servicio
    - Requiere investigación en <1 hora
    - Notificación: Email only
    - Ejemplos: Elevated latency, sync failures

Umbrales:
  Error Rate:
    - WARNING: >2%
    - CRITICAL: >5%
    - Rationale: 5% = 1 de cada 20 requests falla
  
  Latency (p95):
    - TARGET: <2s (SLO)
    - WARNING: >2s
    - CRITICAL: >5s
    - Rationale: 2s es UX acceptable, 5s es muy malo

Durations:
  CRITICAL: 1-5 minutos
    - Balance entre noise y respuesta rápida
  
  WARNING: 10-15 minutos
    - Evitar alertas por blips temporales
```

### Runbook Integration

Cada alerta incluye:
- ✅ **Descripción clara** del problema
- ✅ **Pasos de troubleshooting** específicos
- ✅ **Links directos** a dashboards y logs
- ✅ **Contexto** (valores normales vs actuales)
- ✅ **Criterios de escalación**

---

## 📧 PASO 5.13: CONFIGURAR SLACK (OPCIONAL)

Si configuraste Slack, personalizar mensajes:

### Slack Alert Template

```json
{
  "text": "🚨 *${ALERT_SEVERITY}*: ${ALERT_POLICY_NAME}",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "🚨 ${ALERT_SEVERITY} Alert"
      }
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "*Alert:*\n${ALERT_POLICY_NAME}"
        },
        {
          "type": "mrkdwn",
          "text": "*Project:*\nretail-recommendations-449216"
        },
        {
          "type": "mrkdwn",
          "text": "*Started:*\n${INCIDENT_START_TIME}"
        },
        {
          "type": "mrkdwn",
          "text": "*Value:*\n${OBSERVED_VALUE}"
        }
      ]
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "${DOCUMENTATION}"
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "View Dashboard"
          },
          "url": "https://console.cloud.google.com/monitoring/dashboards?project=retail-recommendations-449216"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "View Logs"
          },
          "url": "https://console.cloud.google.com/logs?project=retail-recommendations-449216"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "View Incident",
            "style": "danger"
          },
          "url": "${INCIDENT_URL}"
        }
      ]
    }
  ]
}
```

---

## ⚠️ TROUBLESHOOTING

### No Recibo Emails

**Causa**: Email no verificado

**Solución**:
```bash
# Re-enviar verificación
# Alerting → Notification Channels → Email → "Resend verification"

# Verificar spam folder
```

### Alertas Flapping (On/Off repetidamente)

**Causa**: Threshold muy cerca del valor normal

**Solución**:
- Aumentar duration (ej: 5min → 10min)
- Ajustar threshold con más margen
- Agregar hysteresis (ej: alert at 5%, resolve at 4%)

### Demasiadas Alertas

**Causa**: Thresholds muy sensibles

**Solución**:
1. Review alert history
2. Identificar alertas ruidosas
3. Ajustar thresholds o durations
4. Considerar combinar alertas similares

---

## 📊 MONITOREO DE ALERTAS

### Dashboard de Alertas

Crear un widget en Dashboard 3:

```promql
# Alertas activas por severidad
count(ALERTS{alertstate="firing"}) by (severity)
```

### Alert History

```bash
# Ver historial de incidentes (últimos 7 días)
gcloud alpha monitoring policies list \
  --project=retail-recommendations-449216 \
  --filter="enabled=true" \
  --format="table(displayName, alertStrategy.notificationRateLimit.period)"
```

---

## ✅ VERIFICACIÓN FINAL PASO 5

### Checklist de Completación

```yaml
Notification Channels:
  [✓] Email configurado y verificado
  [✓] Slack configurado (opcional)

Alertas Críticas:
  [✓] Service Down (up < 1 por 1min)
  [✓] High Error Rate (>5% por 5min)
  [✓] Extreme Latency (p95 >5s por 5min)

Alertas Warning:
  [✓] Elevated Latency (p95 >2s por 10min)
  [✓] KB Sync Failures (>10% por 15min)
  [✓] (Bonus) Google API Errors

Configuración:
  [✓] Documentation en cada alerta
  [✓] Links a dashboards/logs
  [✓] Notification settings optimizados
  [✓] Email templates (opcional)

Testing:
  [✓] Email verificado funcionando
  [✓] Alertas listadas correctamente
```

### Comando de Verificación

```bash
# Verificar que todas las alertas estén habilitadas
gcloud alpha monitoring policies list \
  --project=retail-recommendations-449216 \
  --filter="enabled=true" \
  --format="value(displayName)" | wc -l

# Debe mostrar: 5 (o 6 si creaste bonus)
```

---

## 🎓 APRENDIZAJES CLAVE

### Conceptos Aplicados

1. **SRE Best Practices**:
   - Alerting on symptoms (no causes)
   - Actionable alerts only
   - Clear escalation paths

2. **Alert Fatigue Prevention**:
   - Thresholds basados en SLOs reales
   - Durations apropiadas para evitar noise
   - Severity levels diferenciados

3. **Incident Response**:
   - Runbooks integrados en alertas
   - Links directos a herramientas
   - Contexto completo en notificación

4. **Error Budget**:
   - 5% error rate = consumir error budget rápidamente
   - p95 latency >2s = SLO breach
   - Alerts alineadas con objetivos de negocio

---

## 📊 COSTOS DE ALERTING

```yaml
Alerting (GCP Cloud Monitoring):
  Primeras 50 reglas: GRATIS
  Reglas adicionales: $0.75/regla/mes
  
  Tu configuración: 5 reglas
  Costo: $0.00 ✅

Notification Channels:
  Email: GRATIS (ilimitado)
  Slack: GRATIS
  PagerDuty: $19/mes (si se usa)
  
  Tu configuración: Email + Slack
  Costo: $0.00 ✅

Total mensual: $0.00 ✅
```

---

## 🔄 EXPORTAR ALERTAS (VERSION CONTROL)

```bash
# Exportar cada alert policy
gcloud alpha monitoring policies list \
  --project=retail-recommendations-449216 \
  --format=json > alert_policies.json

# Versionarlo en Git
git add monitoring/alert_policies.json
git commit -m "feat(monitoring): Add GCP alert policies"

# Restaurar desde backup (si es necesario)
gcloud alpha monitoring policies create --policy-from-file=alert_policies.json \
  --project=retail-recommendations-449216
```

---

## ✅ ESTADO PASO 5

**Alertas configuradas**:
- [✓] 5 alertas (3 critical, 2 warning)
- [✓] Notification channels setup
- [✓] Email verificado
- [✓] Documentation completa
- [✓] Best practices aplicadas

**Tiempo real**: ~30 minutos (según estimado)

---

## 🎯 PRÓXIMO PASO

**PASO 6**: Integración con Código (45 min)

Configuraremos:
1. Variables de entorno para GCP
2. (Opcional) Exporter desde localhost
3. Preparación para Cloud Run deployment
4. Service Account configuration

---

**ESTADO PASO 5**: ✅ COMPLETADO

**PROGRESO GENERAL**:
```
✅ PASO 1: Prerequisitos (15 min)
✅ PASO 2: APIs (0 min)
✅ PASO 3: IAM (5 min)
✅ PASO 4: Dashboards (60 min)
✅ PASO 5: Alertas (30 min)
⏳ PASO 6: Integración código (45 min)
⏳ PASO 7: Testing (30 min)
⏳ PASO 8: Documentación (15 min)
```

**Progreso**: 62.5% (5/8 pasos)  
**Tiempo invertido**: ~110 minutos  
**Tiempo restante**: ~90 minutos

---

**¿Continuar con Paso 6 (Integración con Código)?** 🔧

O prefieres:
- Tomar un break
- Revisar alertas creadas en console
- Hacer deployment antes de continuar

¡Tú decides! 🎯
