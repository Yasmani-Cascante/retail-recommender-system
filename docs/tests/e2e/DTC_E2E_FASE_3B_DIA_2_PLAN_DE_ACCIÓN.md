# 🎯 PRÓXIMOS PASOS - RETAIL RECOMMENDER SYSTEM
## Estado: Post E2E Tests Success (2/2 Passing) ✅
**Actualizado:** 16 Diciembre 2025

---

## ✅ ESTADO ACTUAL - LO QUE ACABAMOS DE LOGRAR

### Tests E2E (100% Passing) 🎉
```
✅ test_environment_setup.py       - Environment validation
✅ test_user_journey_discovery.py  - Discovery flow (search → recommendations)
✅ test_user_journey_purchase.py   - Purchase flow (search → view → cart → checkout)
```

**Fixes Aplicados en Esta Sesión:**
1. ✅ Fix timestamp format en recommendations.py (datetime.utcnow().isoformat())
2. ✅ Fix dual authentication mock (get_api_key + get_current_user)
3. ✅ Fix producto validation usando datos reales del catálogo
4. ✅ Fix type consistency (string vs int en product_id)

**Aprendizajes Clave:**
- FastAPI puede requerir múltiples dependencias de auth en un endpoint
- Mocks deben cubrir TODAS las dependencias, no solo las obvias
- Tests E2E deben usar datos reales del catálogo, no hardcoded
- Type consistency es crítico en comparaciones (str vs int)

---

## 🎯 PLAN DE ACCIÓN - PRÓXIMAS 4 SEMANAS

### 📅 SEMANA 1: Expansión de Tests E2E (Alta Prioridad)
**Objetivo:** Aumentar cobertura de user journeys y edge cases
**Tiempo estimado:** 5 días (~3-4 horas/día)

#### Día 1-2: Implementar User Journey 3 - Conversational Flow
```python
# tests/e2e/test_user_journey_conversational.py

Scenario: Usuario usa chat conversacional para encontrar productos
- STEP 1: Iniciar conversación MCP
- STEP 2: Hacer pregunta sobre productos ("vestidos elegantes para boda")
- STEP 3: Recibir recomendaciones personalizadas con contexto
- STEP 4: Refinar búsqueda ("más baratos de $500")
- STEP 5: Verificar que contexto se mantiene entre turnos
- STEP 6: Agregar producto recomendado a carrito

Expected: < 5s total, contexto persistente, recomendaciones relevantes
```

**Tareas concretas:**
- [ ] Crear test_user_journey_conversational.py
- [ ] Implementar 6 steps del flow conversacional
- [ ] Validar persistencia de contexto en Redis
- [ ] Verificar turn increment logic
- [ ] Ejecutar test y validar passing

**Deliverable:** 1 nuevo E2E test passing (total: 3/3)

---

#### Día 3: Implementar Edge Cases Tests
```python
# tests/e2e/test_edge_cases.py

Test Cases:
1. Empty search results
   - Search: "producto inexistente xyz123"
   - Expected: 200 OK, empty array, no crash

2. Invalid product ID
   - GET /v1/products/999999999999
   - Expected: 404 Not Found, error message claro

3. Search with special characters
   - Search: "vestido ñoño @#$%"
   - Expected: 200 OK, sanitized query, results válidos

4. Concurrent requests (simulated)
   - 10 requests simultáneos a /v1/products/search
   - Expected: Todas 200 OK, sin race conditions

5. Large result pagination
   - Search: "vestido" (debe retornar muchos)
   - Paginar con offset/limit
   - Expected: Pagination correcta, sin duplicados

6. Multi-market switching
   - Request 1: market=US
   - Request 2: market=MX
   - Expected: Precios y currency correctos para cada market
```

**Tareas concretas:**
- [ ] Crear test_edge_cases.py
- [ ] Implementar 6 test cases
- [ ] Validar error handling apropiado
- [ ] Ejecutar suite completa

**Deliverable:** 6 nuevos tests passing, mejor cobertura de error scenarios

---

#### Día 4-5: Implementar Performance & Load Tests
```python
# tests/e2e/test_performance.py

Performance Tests:
1. Response time validation
   - Search: < 2s (95th percentile)
   - Product details: < 1s
   - Recommendations: < 1.5s

2. Cache effectiveness
   - First request: cache miss (slower)
   - Second request: cache hit (faster)
   - Expected: 10x speedup on cache hit

3. Concurrent users simulation
   - Simulate 10 users (asyncio.gather)
   - Expected: No degradation, all < 3s

# tests/load/test_load_basic.py (usando locust o pytest-benchmark)

Load Tests:
1. Baseline load (10 users)
2. Medium load (50 users)
3. Peak load (100 users)
4. Stress test (200 users)

Metrics tracked:
- Response time (avg, p50, p95, p99)
- Error rate
- Throughput (requests/sec)
- Resource usage (memory, CPU)
```

**Tareas concretas:**
- [ ] Crear test_performance.py con benchmarks
- [ ] Implementar cache effectiveness tests
- [ ] Crear test_load_basic.py con locust
- [ ] Documentar performance baselines
- [ ] Ejecutar load tests y documentar resultados

**Deliverable:** Performance baseline documentado + load test suite

---

### 📅 SEMANA 2: Code Cleanup & Legacy Removal (Media Prioridad)
**Objetivo:** Limpiar código legacy y duplicado
**Tiempo estimado:** 3 días (~2-3 horas/día)

#### Día 1: Audit & Planning
```bash
# Identificar archivos legacy
src/api/routers/0_legacy/          # ¿Qué hay aquí?
src/api/routers/0_backups/         # ¿Necesario mantener?
tests/phase0_consolidation/        # ¿Obsoleto?
tests/phase2_consolidation/        # ¿Obsoleto?

# Identificar duplicados
products_router.py
products_router copy.py            # ❌ Eliminar
recommendations.py
recommendations_original_backup_*  # ❌ Mover a archive/
```

**Tareas concretas:**
- [ ] Hacer inventory completo de archivos legacy
- [ ] Documentar qué se puede eliminar vs archivar
- [ ] Crear plan de cleanup con safe delete order
- [ ] Backup completo antes de eliminar

**Deliverable:** Cleanup plan documentado

---

#### Día 2-3: Execute Cleanup
```bash
# Step 1: Create archive for important backups
mkdir -p archive/2025-12-16-pre-cleanup/
mv src/api/routers/0_legacy/ archive/2025-12-16-pre-cleanup/
mv src/api/routers/0_backups/ archive/2025-12-16-pre-cleanup/

# Step 2: Remove obvious duplicates
rm src/api/routers/products_router\ copy.py
rm src/api/routers/recommendations_original_backup_*.py

# Step 3: Consolidate test directories
mv tests/phase0_consolidation/ archive/2025-12-16-pre-cleanup/
mv tests/phase2_consolidation/ archive/2025-12-16-pre-cleanup/

# Step 4: Run full test suite to ensure nothing broke
pytest tests/ -v

# Step 5: Commit cleanup
git add .
git commit -m "chore: cleanup legacy code and duplicates - Phase 3B post-E2E"
```

**Tareas concretas:**
- [ ] Ejecutar cleanup según plan
- [ ] Validar que tests siguen pasando
- [ ] Actualizar imports si es necesario
- [ ] Commit changes con mensaje descriptivo

**Deliverable:** Codebase limpio, sin archivos duplicados

---

### 📅 SEMANA 3: Factory Pattern Sprawl Resolution (Media Prioridad)
**Objetivo:** Consolidar factories y eliminar duplicación
**Tiempo estimado:** 5 días (~4-5 horas/día)

Según documentación del project knowledge, existe un problema identificado:
- **60% code duplication** entre factories
- **900+ líneas duplicadas**
- Múltiples factories haciendo lo mismo

#### Análisis Requerido Primero
```bash
# Encontrar todas las factories
find src/ -name "*factory*" -type f

# Analizar duplicación
# - ¿Cuántas factories hay?
# - ¿Qué hacen cada una?
# - ¿Qué código está duplicado?
# - ¿Se pueden consolidar?
```

**Plan de ataque (será refinado después de análisis):**
1. Identificar todas las factories existentes
2. Mapear funcionalidad de cada una
3. Identificar código común duplicado
4. Diseñar nueva estructura consolidada
5. Implementar migration incremental
6. Validar con tests

**Deliverable:** Plan detallado de consolidación de factories

---

### 📅 SEMANA 4: Documentation & Final Validation (Baja Prioridad)
**Objetivo:** Documentar sistema y preparar para producción
**Tiempo estimado:** 3 días (~2-3 horas/día)

#### Documentación a Crear/Actualizar

**1. API Documentation**
```markdown
# docs/API_REFERENCE.md

Complete reference de todos los endpoints:
- GET /v1/products/search
- GET /v1/products/{id}
- GET /v1/recommendations/{id}
- POST /v1/events/user/{user_id}
- POST /v1/mcp/conversation

Para cada endpoint:
- Request format
- Response format
- Error codes
- Example usage
- Rate limits (si aplica)
```

**2. Testing Guide**
```markdown
# docs/TESTING_GUIDE.md

- Cómo ejecutar tests
- Cómo escribir nuevos tests
- Testing best practices
- CI/CD integration
- Coverage goals
```

**3. Deployment Guide**
```markdown
# docs/DEPLOYMENT.md

- Environment setup
- Configuration
- Docker deployment
- Cloud Run deployment
- Monitoring setup
- Troubleshooting
```

**4. Developer Onboarding**
```markdown
# docs/DEVELOPER_ONBOARDING.md

- Project structure
- Architecture overview
- Development workflow
- Contributing guidelines
- Code review process
```

**Tareas concretas:**
- [ ] Crear/actualizar cada documento
- [ ] Generar OpenAPI/Swagger docs
- [ ] Crear diagramas de arquitectura
- [ ] Review por peer (si disponible)

**Deliverable:** Documentation completa y actualizada

---

## 🚀 QUICK WINS - Para Hacer YA (< 30 minutos cada uno)

### 1. Agregar más assertions a tests existentes
```python
# En test_user_journey_purchase.py, agregar:
- assert product_details.get("category") is not None
- assert product_details.get("price") > 0
- assert product_details.get("stock_quantity") >= 0
```

### 2. Agregar logging a tests E2E
```python
# En conftest.py, mejorar logging:
logger.info(f"✅ Test {request.node.name} started")
logger.info(f"✅ Test {request.node.name} completed in {duration:.2f}s")
```

### 3. Crear test para health check endpoint
```python
# tests/e2e/test_health.py
async def test_health_endpoint(test_client_with_warmup):
    response = await test_client_with_warmup.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
```

### 4. Documentar fixtures existentes
```python
# En tests/e2e/conftest.py, agregar docstrings detallados:
@pytest.fixture(scope="function")
def mock_auth(app_with_overrides: FastAPI):
    """
    Mock authentication for E2E tests.
    
    Overrides BOTH get_current_user AND get_api_key dependencies
    to allow tests to call authenticated endpoints without real API keys.
    
    Usage:
        async def test_something(test_client_with_warmup, mock_auth):
            # Auth is automatically bypassed
            response = await test_client_with_warmup.get("/protected-endpoint")
    """
```

---

## 📊 MÉTRICAS DE ÉXITO

### Tests E2E
- **Actual:** 2 user journeys ✅
- **Meta corto plazo:** 5 user journeys
- **Meta mediano plazo:** 10 user journeys + edge cases

### Code Quality
- **Actual:** Legacy code presente
- **Meta:** Legacy code archivado/eliminado

### Coverage
- **Actual:** ~80-85% (según docs)
- **Meta:** Validar número real con coverage report

### Documentation
- **Actual:** Buena (150+ páginas)
- **Meta:** Excelente (200+ páginas + API docs)

---

## 🎓 LEARNING OPPORTUNITIES

### 1. Load Testing con Locust
Locust es una herramienta Python para load testing. Aprende:
- Cómo simular usuarios concurrentes
- Cómo medir response times bajo carga
- Cómo identificar bottlenecks

**Recurso:** https://docs.locust.io/en/stable/

---

### 2. Pytest Advanced Features
Profundiza en:
- Parametrized tests (`@pytest.mark.parametrize`)
- Fixtures con scope avanzado
- Custom markers para test organization
- Coverage plugins y reporting

**Recurso:** https://docs.pytest.org/en/stable/

---

### 3. FastAPI Testing Best Practices
Aprende:
- TestClient vs AsyncClient
- Dependency injection para testing
- Database testing strategies
- Mocking external services

**Recurso:** https://fastapi.tiangolo.com/tutorial/testing/

---

### 4. Factory Pattern Consolidation
Estudia:
- Abstract Factory pattern
- Builder pattern para construction compleja
- Registry pattern para factory management
- Dependency Injection vs Factory

**Recurso:** 
- "Design Patterns" by Gang of Four
- "Clean Architecture" by Robert Martin

---

## ❓ PREGUNTAS PARA DECIDIR DIRECCIÓN

Antes de continuar, considera:

1. **¿Cuál es la prioridad del negocio?**
   - ¿Launch rápido? → Focus en quick wins
   - ¿Calidad máxima? → Focus en tests + cleanup
   - ¿Performance? → Focus en load testing + optimization

2. **¿Cuál es el timeline para producción?**
   - < 1 mes → Minimal viable tests + deployment
   - 1-3 meses → Full test suite + cleanup
   - > 3 meses → Todo lo planificado + optimizations

3. **¿Hay equipo para code review?**
   - Sí → Parallelizar tareas, más aggressive refactoring
   - No → Tareas secuenciales, más conservador

4. **¿Qué te emociona más trabajar?**
   - Tests → Semana 1
   - Architecture → Semana 3
   - Documentation → Semana 4
   - Cleanup → Semana 2

---

## 💡 MI RECOMENDACIÓN PERSONAL

Basándome en el momentum actual y el éxito reciente:

### Opción A: "Momentum Ride" (RECOMENDADA 🌟)
```
Próxima sesión: Implementar test_user_journey_conversational.py
Razón: Estás en modo testing, aprovecha el momentum
Tiempo: 2-3 horas
Impacto: Alto (valida MCP integration end-to-end)
```

### Opción B: "Quick Cleanup First"
```
Próxima sesión: Cleanup de archivos legacy
Razón: Mental clarity antes de continuar
Tiempo: 1-2 horas
Impacto: Medio (codebase más limpio)
```

### Opción C: "Performance First"
```
Próxima sesión: Implementar performance tests
Razón: Validar que sistema puede escalar
Tiempo: 3-4 horas
Impacto: Alto (identifica bottlenecks reales)
```

**Mi voto:** **Opción A** - El momentum de testing está fuerte, aprovéchalo.

---

## 📝 TEMPLATE PARA PRÓXIMA SESIÓN

Cuando empieces la próxima sesión, usa este template:

```markdown
# Sesión [Fecha]
## Objetivo: [e.g., "Implementar test_user_journey_conversational.py"]

### Pre-requisitos
- [ ] Tests E2E existentes pasando
- [ ] Redis test environment running
- [ ] Development environment ready

### Tareas
1. [ ] Crear test_user_journey_conversational.py
2. [ ] Implementar Step 1: Iniciar conversación
3. [ ] Implementar Step 2: Primera pregunta
4. [ ] ... (etc)

### Validation
- [ ] Test pasa individualmente
- [ ] Test pasa en suite completa
- [ ] No regresiones en tests existentes

### Documentation
- [ ] Comentar código complejo
- [ ] Actualizar README si es necesario
- [ ] Documentar decisiones arquitectónicas
```

---

## 🎯 SIGUIENTE ACCIÓN CONCRETA

**Para la próxima sesión, te sugiero:**

```bash
# 1. Verificar que tests actuales siguen pasando
pytest tests/e2e/test_user_journey_discovery.py -v
pytest tests/e2e/test_user_journey_purchase.py -v

# 2. Si ambos pasan, empezar con nuevo test:
# Crear: tests/e2e/test_user_journey_conversational.py

# 3. Decirme: "Claude, vamos a implementar el test conversacional"
```

¿Qué opción prefieres? ¿O tienes otra prioridad en mente?
