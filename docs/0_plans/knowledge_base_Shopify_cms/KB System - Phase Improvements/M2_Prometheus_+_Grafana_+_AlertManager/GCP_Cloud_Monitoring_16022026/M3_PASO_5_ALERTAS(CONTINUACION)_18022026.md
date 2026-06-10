Perfecto, veo exactamente dónde estás. Analizo las dos imágenes para guiarte con precisión.

---

## 🔍 ANÁLISIS DE TUS CAPTURAS

### Imagen 2 (Configure alert trigger)
Veo que estás en la pantalla **"Configure alert trigger"** con estos campos:

```yaml
Advanced Options:
  - Detect window: [0 min ▼]
    "Alerts are considered firing once their PromQL expression was evaluated to be 'true' for this long."
  
  - Evaluation interval: [Custom ▼]
    "How often this PromQL query should be evaluated"
  
  - Custom Value: [30] seconds(s) ▼
  
  - Condition name: [New condition]

PromQL Chart en la derecha: "No data is available" ← Normal

Costo: $0.10 → $0.00 (gratis)
```

### Imagen 1 (Notifications and name)
La siguiente pantalla después de "Next" donde configuras:

```yaml
Configure notifications: 
  - Notification Channels: [Yasmani] ✅ seleccionado
  - Notification subject line: CRITICAL ALERT! Retail Recommender Service is DOWN

Policy Severity Level: [No severity ▼]

Documentation: [Text field vacío]

Name the alert policy: [Alert policy name *]
```

---

## 🎯 GUÍA PASO A PASO CORRECTA

### PASO 2.1: Configure Alert Trigger (Imagen 2)

Veo que el problema es que GCP no muestra los campos "Threshold" y "Window" como mencioné antes. En su lugar, usa **"Detect window"** y **"Evaluation interval"**.

**Configura así**:

```yaml
Detect window: 
  Cambia de "0 min" a "1 min"
  (Esto es equivalente al "Window: 1 minute")

Evaluation interval:
  Deja en "Custom"
  
Custom Value:
  Cambia de "30" a "60"
  Unidad: seconds(s)
  (Esto significa: evaluar cada 60 segundos)

Condition name:
  Escribe: "Service Down Condition"
```

**Explicación**:
- **Detect window = 1 min**: La alerta se dispara si la condición es "true" durante 1 minuto seguido
- **Evaluation interval = 60s**: GCP evalúa la query cada 60 segundos

Luego click **"Next"** (botón abajo a la izquierda).

---

### PASO 2.2: Notifications and Name (Imagen 1)

Ahora estás en la pantalla correcta. Configura:

#### 1. Notification Channels
```yaml
✅ Ya tienes "Yasmani" seleccionado - perfecto
```

#### 2. Notification Subject Line
```yaml
Cambia de:
  "CRITICAL ALERT! Retail Recommender Service is DOWN"

A (más corto):
  "[CRITICAL] Service Down - Retail Recommender"
```

#### 3. Policy Severity Level
```yaml
Cambia de "No severity" a:
  → "Critical" o "Error"
  
(Busca en el dropdown, debería tener opciones como Critical/Error/Warning)
```

#### 4. Documentation
En el campo de texto grande, pega esto:

```
🚨 CRITICAL ALERT: Retail Recommender Service is DOWN

The service has been unreachable for over 1 minute.

IMMEDIATE ACTION REQUIRED:
1. Check Cloud Run logs: https://console.cloud.google.com/run?project=retail-recommendations-449216
2. Verify deployment status
3. Check recent deployments
4. Escalate if not resolved in 5 minutes

Dashboard: https://console.cloud.google.com/monitoring/dashboards?project=retail-recommendations-449216

Runbook: Check /health endpoint and verify service is responsive
```

#### 5. Name the Alert Policy
En el campo **"Alert policy name"**, escribe:

```
[CRITICAL] Service Down
```

---

### PASO 2.3: Create Policy

Click el botón **"Create Policy"** (azul, abajo a la derecha).

---

## 📋 CONFIGURACIÓN CORREGIDA PARA LAS 5 ALERTAS

Ahora que entiendo la interfaz real, aquí está la configuración correcta:

### ALERTA 1: Service Down ✅ (La que estás creando ahora)

```yaml
Query PromQL: up{job="retail-recommender"} < 1
Detect window: 1 min
Evaluation interval: 60 seconds
Severity: Critical
Name: [CRITICAL] Service Down
```

---

### ALERTA 2: High Error Rate

**Configure trigger**:
```yaml
Query PromQL:
  sum(rate(http_requests_total{status=~"5.."}[5m]))
  /
  sum(rate(http_requests_total[5m]))
  * 100 > 5

Detect window: 5 min
Evaluation interval: 60 seconds
Condition name: High Error Rate Condition
```

**Notifications**:
```yaml
Severity: Critical
Subject: [CRITICAL] High HTTP Error Rate
Documentation:
  🚨 CRITICAL: HTTP Error Rate Exceeding 5%
  
  Current error rate is above acceptable threshold (5%).
  This indicates a systemic issue affecting users.
  
  TROUBLESHOOTING STEPS:
  1. Check error logs in Cloud Logging
  2. Review recent deployments (rollback if needed)
  3. Verify external dependencies (Redis, Google Retail API)
  4. Check system resources (CPU, memory)
  
  Dashboard: https://console.cloud.google.com/monitoring/dashboards?project=retail-recommendations-449216

Name: [CRITICAL] High HTTP Error Rate
```

---

### ALERTA 3: Extreme Latency

**Configure trigger**:
```yaml
Query: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5
Detect window: 5 min
Evaluation interval: 60 seconds
```

**Notifications**:
```yaml
Severity: Critical
Subject: [CRITICAL] Extreme API Latency (p95 > 5s)
Documentation:
  🚨 CRITICAL: API Latency Extremely High
  
  95th percentile latency is above 5 seconds (250% over target).
  
  IMMEDIATE ACTIONS:
  1. Check Redis cache performance
  2. Review slow query logs
  3. Verify Google Retail API latency
  4. Monitor active requests (possible overload)
  
  Normal p95: <2s | Current threshold: >5s

Name: [CRITICAL] Extreme API Latency
```

---

### ALERTA 4: Elevated Latency

**Configure trigger**:
```yaml
Query: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
Detect window: 10 min
Evaluation interval: 60 seconds
```

**Notifications**:
```yaml
Severity: Warning
Subject: [WARNING] Elevated API Latency
Documentation:
  ⚠️ WARNING: API Latency Above SLO Target
  
  95th percentile exceeds 2 seconds.
  Monitor for escalation to critical (>5s).
  
  INVESTIGATION:
  1. Check cache hit rates
  2. Review concurrent load
  3. Verify external API latencies

Name: [WARNING] Elevated API Latency
```

---

### ALERTA 5: KB Sync Failures

**Configure trigger**:
```yaml
Query:
  sum(rate(kb_sync_operations_total{status="failed"}[15m]))
  /
  sum(rate(kb_sync_operations_total[15m]))
  * 100 > 10

Detect window: 15 min
Evaluation interval: 60 seconds
```

**Notifications**:
```yaml
Severity: Warning
Subject: [WARNING] KB Sync Failures
Documentation:
  ⚠️ WARNING: KB Sync Failure Rate > 10%
  
  This may impact recommendation freshness.
  
  TROUBLESHOOTING:
  1. Check Notion API connectivity
  2. Verify page access permissions
  3. Review KB sync logs
  
  Impact: Recommendations may use stale data

Name: [WARNING] KB Sync Failures
```

---

## 🎯 RESUMEN DEL FLUJO CORRECTO

```
Para cada alerta:

1. Alerting → "+ Create Policy"
2. Code editor (PromQL) → Escribir query
3. Advanced Options:
   - Detect window: [tiempo]
   - Evaluation interval: 60 seconds
   - Condition name: [nombre descriptivo]
4. Next
5. Notification Channels: ✅ [Tu email]
6. Severity Level: Critical/Warning
7. Documentation: [Pegar texto]
8. Alert policy name: [nombre]
9. Create Policy
```

---

## ✅ SIGUIENTE ACCIÓN

**Termina de crear la Alerta 1** (Service Down) siguiendo los pasos 2.1, 2.2, y 2.3 que detallé arriba.

Cuando hayas dado click en **"Create Policy"** y la alerta esté creada, **comparte una captura** de la lista de alertas para verificar que quedó correcta, y luego continuamos con las alertas 2, 3, 4, y 5.

¿Alguna duda sobre estos pasos corregidos? 🚀