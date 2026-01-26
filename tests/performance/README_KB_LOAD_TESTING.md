# 🧪 Load Testing - Knowledge Base Multi-Language

## 📍 Ubicación del Archivo

```
tests/performance/locustfile_kb.py
```

## 🚀 Ejecución Rápida

### **Opción 1: Web UI** ⭐ RECOMENDADO

```bash
# Desde la raíz del proyecto
locust -f tests/performance/locustfile_kb.py --host=http://localhost:8000

# Abrir browser: http://localhost:8089
# Configurar:
#   - Number of users: 100
#   - Spawn rate: 10 users/second
# Click "Start swarming"
```

### **Opción 2: Headless (CI/CD)**

```bash
# Scenario 1: Normal load (5 min)
locust -f tests/performance/locustfile_kb.py \
       --host=http://localhost:8000 \
       --users 100 \
       --spawn-rate 10 \
       --run-time 5m \
       --headless

# Scenario 2: Peak load (2 min)
locust -f tests/performance/locustfile_kb.py \
       --host=http://localhost:8000 \
       --users 500 \
       --spawn-rate 50 \
       --run-time 2m \
       --headless
```

## 📊 Success Criteria

```
┌────────────────────────────────────────────────────────────┐
│ METRIC                    TARGET        ACCEPTABLE         │
├────────────────────────────────────────────────────────────┤
│ P50 Response Time         <300ms        <500ms            │
│ P95 Response Time         <500ms        <800ms            │
│ P99 Response Time         <1000ms       <2000ms           │
│ Error Rate                <0.1%         <1%               │
│ Requests/Second           >50           >20               │
│ Cache Hit Ratio           >85%          >70%              │
└────────────────────────────────────────────────────────────┘
```

## 🎯 Escenarios de Testing

### Scenario 1: SMOKE TEST (5 min)
```bash
locust -f tests/performance/locustfile_kb.py \
       --host=http://localhost:8000 \
       --users 10 --spawn-rate 2 --run-time 5m --headless
```
**Objetivo:** Validación básica de funcionalidad

### Scenario 2: NORMAL LOAD (10 min)
```bash
locust -f tests/performance/locustfile_kb.py \
       --host=http://localhost:8000 \
       --users 100 --spawn-rate 10 --run-time 10m --headless
```
**Objetivo:** Performance bajo carga esperada

### Scenario 3: PEAK LOAD (5 min)
```bash
locust -f tests/performance/locustfile_kb.py \
       --host=http://localhost:8000 \
       --users 300 --spawn-rate 30 --run-time 5m --headless
```
**Objetivo:** Identificar breaking point

### Scenario 4: SOAK TEST (30 min)
```bash
locust -f tests/performance/locustfile_kb.py \
       --host=http://localhost:8000 \
       --users 50 --spawn-rate 5 --run-time 30m --headless
```
**Objetivo:** Detectar memory leaks

## 📋 Pre-requisitos

```bash
# 1. Instalar Locust (si no está instalado)
pip install locust

# 2. Verificar servidor corriendo
curl http://localhost:8000/api/v1/kb/health

# 3. (Opcional) Warm cache
curl "http://localhost:8000/api/v1/kb/answer?sub_intent=policy_return&language=es"
curl "http://localhost:8000/api/v1/kb/answer?sub_intent=policy_return&language=en"
```

## 📈 Interpretación de Resultados

### Web UI - Tabs Importantes:

**Statistics:**
- Request count, failures, median, 95%, 99%
- ✅ Median < 500ms
- ✅ 95% < 800ms
- ✅ Failures < 1%

**Charts:**
- Response times over time
- RPS (requests per second)
- Number of users
- ✅ Response times estables (no degradación)

**Failures:**
- Should be mostly empty
- ✅ Only [invalid] requests should fail (expected)

### Headless - Output:

```
Name                          # reqs   # fails  Avg    Min    Max  Median  99%
/api/v1/kb/answer [explicit]   5000     0       295    156    567   290    520
/api/v1/kb/answer [header]     5000     0       302    160    589   295    535
/api/v1/kb/answer [cached]     1500     0       185    142    345   180    310
/api/v1/kb/answer [invalid]     500    500      12      8     25    11     22
```

**Validar:**
- ✅ Avg < 500ms
- ✅ 99% < 2000ms
- ✅ [cached] significativamente más rápido que [explicit]/[header]
- ✅ Failures solo en [invalid] (comportamiento esperado)

## ⚠️ Troubleshooting

### Error: "Connection refused"
```bash
# Verificar servidor corriendo
curl http://localhost:8000/api/v1/kb/health
```

### Alta latencia (>2s)
**Causas:**
1. Cold cache (first requests) → Normal, mejora después
2. Database overload → Check PostgreSQL connections
3. Redis slow → Check Redis latency

**Fix:**
```bash
# Warm cache antes de test
for intent in policy_return policy_shipping product_care; do
    curl "http://localhost:8000/api/v1/kb/answer?sub_intent=$intent&language=es"
    curl "http://localhost:8000/api/v1/kb/answer?sub_intent=$intent&language=en"
done
```

### High failure rate (>1%)
**Check:**
```bash
# Revisar logs del servidor
# Buscar errores 500
```

## 🎓 Qué Validamos

**Performance:**
- ✅ Response times bajo carga
- ✅ Throughput (requests/second)
- ✅ Escalabilidad (degradación con más users)

**Cache:**
- ✅ Cache hit rate
- ✅ Redis vs PostgreSQL performance
- ✅ Cache warming effectiveness

**Robustez:**
- ✅ Error handling (invalid requests)
- ✅ Stability (no crashes bajo carga)
- ✅ Recovery (después de peak load)

**Concurrencia:**
- ✅ Multiple users simultáneos
- ✅ No race conditions
- ✅ Connection pool management

## 📝 Checklist Pre-Production

```
[ ] Smoke test passed (10 users, 5 min)
[ ] Normal load test passed (100 users, 10 min)
[ ] Peak load test passed (300 users, 5 min)
[ ] P95 < 800ms en todos los scenarios
[ ] Error rate < 1% en todos los scenarios
[ ] No memory leaks (soak test)
[ ] Cache hit rate > 70%
[ ] Sistema recovers gracefully después de peak
```

## 🔗 Referencias

- Locust documentation: https://docs.locust.io/
- Load Testing Guide: `LOAD_TESTING_GUIDE.md`
- Architecture docs: `docs/architecture/ARCHITECTURE_KNOWLEDGE_BASE_MULTI-LANGUAGE.md`
