Reintroducción de Transformers — Análisis
1. Cómo mejoraría el sistema, en particular la detección de intenciones
El punto de dolor más concreto que tenemos hoy está en la zona 0.5–0.8 de confidence del rule-based detector: es donde el ML fallback interviene y, como acabamos de ver esta sesión, a veces corrige mal (TRANSACTIONAL → INFORMATIONAL). El guard que aplicamos hoy es una solución defensiva. Un transformer resolvería la causa raíz.
Mejoras específicas al intent detector:
El sistema actual tiene dos capas: rule-based (regex) + sklearn TF-IDF + Logistic Regression. El problema estructural del sklearn es que trabaja sobre bag-of-words: no entiende orden ni contexto. Para el detector, "no quiero devolver" y "quiero devolver" tienen vectores muy similares. Un transformer entiende negación, matices y orden. Ejemplos concretos donde un pequeño transformer ganaría al sistema actual:

"aceptan solo efectivo o también tarjeta?" — rule-based puntúa ambiguamente porque tiene tanto keywords TRANSACTIONAL ("también") como INFORMATIONAL ("tarjeta", "efectivo"). sklearn lo resolvería con bag-of-words que puede confundirse con casos similares. Un transformer interpreta la pregunta completa en contexto.
"¿este vestido rojo que vi antes también lo tienen en azul?" — requiere comprensión de la referencia anafórica "este... que vi antes". Rule-based ni sklearn la procesan.
"quiero saber si puedo devolver algo que ya usé" — INFORMATIONAL policy_return, pero "quiero" activa el rule-based TRANSACTIONAL. El guard no ayuda aquí porque rule-based retorna TRANSACTIONAL. Un transformer clasifica correctamente porque procesa la oración completa.

Más allá del intent detector, los transformers abrirían capacidades nuevas que hoy no existen:

Sub-intent semántico preciso: Hoy para saber si una query INFORMATIONAL es policy_return o policy_payment dependemos de keywords. Un transformer puede distinguir "me cobraron dos veces" (payment issue) de "quiero devolver el pago" (return) sin necesidad de reglas manuales.
Embeddings de producto para el TF-IDF: Reemplazar la vectorización TF-IDF del recomendador por embeddings semánticos (sentence-transformers). "necesito algo elegante para una cena" encontraría vestidos de noche aunque ningún producto tenga la palabra "elegante" en el título.
Detección de idioma robusta: El sistema que implementamos hoy con regex es una aproximación. Un modelo de detección de idioma (fastText o similar, 900KB) sería más preciso para frases cortas y ambiguas.

2. Ventajas y desventajas
Ventajas:
El beneficio principal es cobertura semántica real. El sistema actual maneja bien los casos directos pero falla en oraciones complejas, negaciones, referencias y lenguaje coloquial — exactamente los casos que los usuarios reales escriben. Un transformer pequeño como all-MiniLM-L6-v2 (22MB) o paraphrase-multilingual-MiniLM-L12-v2 (120MB, multilingüe) cubre esos huecos con 99% de accuracy en intent detection en benchmarks de NLU en español.
La segunda ventaja es mantenimiento reducido a largo plazo. Cada vez que aparece una nueva forma de preguntar algo ("¿manejan cuotas sin intereses?", "pagan con crypto?"), hoy hay que añadir un regex manualmente. Con un transformer entrenado en suficientes ejemplos, esas variantes se capturan automáticamente.
Desventajas:
El problema crítico para tu arquitectura es el cold start en Cloud Run. Es exactamente lo que mencionas. Los transformers de sentence-transformers cargan el modelo completo en memoria al inicio: all-MiniLM-L6-v2 tarda ~400ms en cargarse en frío en CPU, MiniLM-L12 ~900ms, y modelos multilingües más grandes como distiluse-base-multilingual pueden llegar a 2–3s. En Cloud Run con mínimas instancias en 0, esto se suma a los ya existentes tiempos de startup de FastAPI + Redis + sklearn.
La segunda desventaja es costo de memoria: el sistema actual en Cloud Run corre con ~256MB RAM mínima. Un transformer añade 50–200MB de overhead dependiendo del modelo. Esto puede forzar subir el tier de memoria (256MB → 512MB o más), con impacto en costos.
La tercera es complejidad de deployment: sentence-transformers requiere PyTorch como dependencia, que pesa ~600MB instalado. Esto engorda la imagen Docker significativamente y ralentiza los builds de Cloud Build.
3. Consideraciones y recomendaciones
Recomendación principal: implementación diferida + lazy loading
No reintroducir transformers como dependencia del cold start path. En cambio, usar el mismo patrón que ya tienes con _ensure_ml_loaded() en hybrid_detector.py: carga lazy en el primer request que lo necesite, después de que la instancia ya esté caliente.
La arquitectura concreta sería:
Request llega
    ↓
Rule-based detector (0ms — siempre primero)
    ↓ confidence < 0.6
sklearn fallback (0.4ms — ya cargado)
    ↓ confidence < 0.7 Y instancia ya caliente > 30s
Transformer fallback (carga lazy si no está cargado)
    ↓
Guard de protección TRANSACTIONAL (el que aplicamos hoy)
El transformer solo se activa en casos genuinamente ambiguos, nunca en el hot path de arranque.
Modelo recomendado para tu caso concreto:
Para el recomendador semántico, paraphrase-multilingual-MiniLM-L12-v2 es el punto óptimo: 120MB, 50ms de inferencia, cubre ES/EN/DE/FR y está optimizado para similitud semántica — directamente útil para mejorar el TF-IDF de productos.
Para el intent detector, lo más pragmático es no usar un transformer general sino entrenar una cabeza de clasificación sobre embeddings fijos. El proceso sería: generar embeddings con all-MiniLM-L6-v2 para el dataset de 4.944 queries que ya tienes, entrenar un clasificador ligero (MLP de 2 capas o SVM con kernel RBF) sobre esos embeddings, y serializar solo el clasificador. El modelo de embeddings se carga una sola vez, el clasificador es trivialmente pequeño. Accuracy esperada: 98%+ vs el 96.26% actual, con cobertura de casos semánticos que el sklearn bag-of-words no puede resolver.
Plan de implementación de bajo riesgo:
Una aproximación que no afecta el cold start es pre-computar los embeddings del catálogo de productos en un job offline (o durante el startup asíncrono, después de servir el primer request) y guardarlos en Redis. Así el transformer nunca está en el critical path. Cuando llega una query, se vectoriza en ~10ms (inferencia rápida de un query corto) y se busca por similitud coseno en los embeddings precalculados del catálogo. Esto es exactamente lo que hace el TF-IDF hoy, pero con representaciones semánticas reales.
Veredicto para tu sistema en este momento: Los fixes de rule-based que implementamos hoy (guard, nuevos keywords, detección de idioma) resuelven los bugs de alta prioridad con zero overhead. Los transformers son la evolución correcta para el siguiente nivel de calidad, pero el momento adecuado es después de estabilizar F-01 (Contextual Upsell) y tener métricas de producción que justifiquen el esfuerzo de integración. La recomendación es planificarlo como una fase independiente con lazy loading y embeddings pre-computados, no como un cambio urgente.