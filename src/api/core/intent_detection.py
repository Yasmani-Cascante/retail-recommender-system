"""
Intent Detection - Rule-Based Implementation
Simple, fast, and effective rule-based intent detector.

Design Principles:
- Rules over ML (for now) - simple, maintainable, fast
- High precision over high recall - better to default to products than give wrong info
- Easy to extend - adding new patterns is trivial
- Ready for extraction - designed as standalone module

Changelog:
- 2026-03-04: Renamed PRODUCT_SIZE → PRODUCT_SIZING to match DB value "product_sizing".
              Added question_words for PRODUCT_SIZING to prevent false-positive matches
              from PRODUCT_AVAILABILITY (which also matches the word "have/hay").
"""

import re
import logging
from typing import List, Dict, Optional, Set
from functools import lru_cache

from src.api.core.intent_types import (
    IntentType,
    InformationalSubIntent,
    TransactionalSubIntent,
    IntentDetectionResult
)


# ═══════════════════════════════════════════════════════════════
# GREETING PATTERNS
# ═══════════════════════════════════════════════════════════════
# Pre-compiled at module level for performance (used on every request).
# Kept separate from IntentPatterns to keep the greeting check fast
# and independent of the informational/transactional scoring logic.
#
# Design decision: greetings are detected BEFORE the question-indicator
# check, because "Hi!" and "Hola!" are NOT questions, so the existing
# is_question() gate would exclude them entirely, sending them to the
# TRANSACTIONAL fallback — which produces products with no greeting.
#
# Confidence assigned: 0.95 (very high — these patterns are unambiguous).
# If a query matches a greeting AND a transactional/informational pattern,
# the greeting wins because it is checked first.

_GREETING_PATTERNS = [
    # English greetings
    re.compile(r"^\s*(hi|hello|hey|howdy|greetings|good\s*(morning|afternoon|evening|day|night))\b",
               re.IGNORECASE),
    # Spanish greetings
    re.compile(r"^\s*(hola|buenos\s*(días|días|dias|tardes|noches)|buenas|qué\s*tal|que\s*tal|saludos)\b",
               re.IGNORECASE),
    # Short conversational openers without topic
    re.compile(r"^\s*(hi+!*|hey!*|hola!*|hello!*)\s*$", re.IGNORECASE),
]

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PATTERN DEFINITIONS
# ═══════════════════════════════════════════════════════════════

class IntentPatterns:
    """
    Pattern definitions for intent detection.
    Organized by intent type and sub-intent.

    ──────────────────────────────────────────────────────────────
    SCORING LOGIC (for reference when adding new patterns):
    ──────────────────────────────────────────────────────────────
    Each keyword match adds +0.4 pts.
    Each question_word match adds +0.3 pts (bonus, one-time).
    Each negative_context match adds +0.2 pts (bonus, one-time).
    Minimum threshold to be considered: 0.4 pts (at least 1 keyword).
    Minimum confidence to be returned as INFORMATIONAL: 0.7 pts.

    IMPORTANT: Be careful with generic verbs like "have/hay/tiene" —
    they appear in queries about ANY sub-intent (sizing, availability,
    payment, etc.).  Put them in question_words (bonus) rather than
    keywords (required) to avoid unintended matches.
    """

    # ───────────────────────────────────────────────────────────
    # INFORMATIONAL PATTERNS
    # ───────────────────────────────────────────────────────────

    INFORMATIONAL_PATTERNS = {

        # ── Policy: Returns / Refunds ───────────────────────────
        InformationalSubIntent.POLICY_RETURN: {
            "keywords": [
                r"\b(política|policy|políticas|policies)\b",
                r"\b(devolución|devolucion|devolver|devoluciones|return|returns)\b",
                r"\b(reembolso|refund|reintegro)\b",
                r"\b(cambio|cambiar|exchange)\b",
                r"\b(garantía|warranty|garantia)\b",
                r"\b(regresar|devuelta|volver)\b",   # LATAM variants
                r"\b(días|plazo|tiempo)\b",           # Time references
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(cuál|cual|cuáles|cuales|what|which)\b",
                r"\b(puedo|puede|can|may)\b",
            ],
            "negative_context": [
                r"\b(no (me )?(queda|gusta|sirve))\b",
                r"\b(mal(o)?|defectuoso|roto|damaged)\b",
                r"\b(est[aá]|est[aá]n|estan|is\s+it|still)\b(?=.*\b(disponible|available)\b)",
                r"\b(sigue|todav[ií]a|todavia)\b(?=.*\b(disponible|available)\b)",
            ],
        },

        # ── Policy: Shipping / Delivery ─────────────────────────
        InformationalSubIntent.POLICY_SHIPPING: {
            "keywords": [
                # FIX (25/03/2026): \b(envio)\b did NOT match 'envios' (plural) because
                # the trailing 's' is a word character — no word boundary fires after 'o'.
                # "hacen envios hasta casa?" scored 0.0 and fell to TRANSACTIONAL (products).
                # Added s? to cover plural; added 'envía(n)?' and 'domicilio' for natural variants.
                r"\b(envíos?|envios?|envía(n|s)?|envia(n|s)?|shipping|deliver(y|s)?|entregas?)\b",
                r"\b(enviar|mandar|manda|mandan|send|ship)\b",
                r"\b(domicilio|a\s+casa|home\s+delivery|a\s+mi\s+casa)\b",
                r"\b(paquete|package|pedido|order)\b",
                r"\b(rastreo|tracking|seguimiento)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(cuándo|cuando|cuanto|cuánto|cuanto.*tarda|when)\b",
                r"\b(dónde|donde|where)\b",
                # Added: catches action-style queries with no explicit question word.
                # "hacen envios hasta casa?" has no cómo/cuándo/dónde — 'hacen' fills the gap.
                # 'dirección' catches "enviar a otra dirección?"; 'home' catches English variants.
                r"\b(hacen|mandan|llega|llegan|hasta|do\s+you|can\s+you|dirección|direccion|home|address)\b",
            ],
        },

        # ── Policy: Payment ──────────────────────────────────────
        InformationalSubIntent.POLICY_PAYMENT: {
            "keywords": [
                r"\b(pago|payment|pagos|payments)\b",
                r"\b(pagar|pay|paid)\b",
                r"\b(tarjeta|card|crédito|credito|débito|debito)\b",
                r"\b(efectivo|cash|transferencia|transfer)\b",
                r"\b(paypal|mercadopago|mercado.*pago)\b",
                r"\b(cuotas|meses.*sin.*intereses|installments)\b",
                # FIX (25/03/2026): "Cuales son los Metodos de Pagos aceptados?" scored
                # only 0.4 (just 'pagos' keyword matched), below the 0.7 INFORMATIONAL
                # threshold — fell through to TRANSACTIONAL and got the prior turn's response.
                # With 'métodos' as a keyword the query now scores:
                #   'pagos'(+0.4) + 'metodos'(+0.4) + question_word 'son'(+0.3) = 1.0
                # Safely scoped: only fires when paired with another payment keyword.
                r"\b(métodos?|metodos?|method|methods|forma|formas|medio|medios)\b",
                # FIX (09/04/2026): Marcas de tarjetas y terminos de financiamiento.
                # Queries como "aceptan Mastercard", "aceptan Visa", "pago con Amex"
                # no matcheaban ningun keyword — score 0.0, caia a TRANSACTIONAL.
                # Riesgo 'visa': en un e-commerce de ropa el unico contexto relevante
                # es el de metodos de pago. Para llegar a 0.7 necesita ademas un
                # question_word (acepta/como/puede), lo que filtra naturalmente queries
                # de viaje como "necesito visa" (no tienen question_word de pago).
                r"\b(visa|mastercard|master\s*card|amex|american\s*express)\b",
                # Terminos de financiamiento: 'plazos' es sinonimo de 'cuotas' en ES/CL.
                # 'diferido' cubre pagos diferidos (MX). 'contra\s*entrega' es COD.
                r"\b(plazos?|diferido|contra\s*entrega|cash\s*on\s*delivery|cod)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                # FIX (25/03/2026): 'aceptan' missed 'aceptados' (different verb form).
                # Broadened to match: acepta, aceptan, aceptados, accepted, accepts.
                r"\b(acepta(n|dos?)?|accept(s|ed)?)\b",
                r"\b(puedo|puede|can)\b",
                # Added: catches "Cuales son..." / "What are..." list-style questions.
                r"\b(cuáles?|cuales?|son|are|what)\b",
                # FIX (09/04/2026): 'pagan/cobran/manejan' como question_word captura
                # queries como "pagan con Visa?" o "cobran con tarjeta?".
                r"\b(pagan|cobran|manejan|usan|tienen|do\s+you\s+take)\b",
            ],
        },

        # ── Policy: Warranty ────────────────────────────────────
        InformationalSubIntent.POLICY_WARRANTY: {
            "keywords": [
                r"\b(garantía|garantia|warranty|garantías)\b",
                r"\b(defecto|defectuoso|defect|broken|roto)\b",
                r"\b(reparar|repair|reemplazar|replace)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(cuál|cual|what)\b",
                r"\b(puedo|puede|can)\b",
            ],
        },

        # ── Policy: Privacy ─────────────────────────────────────
        InformationalSubIntent.POLICY_PRIVACY: {
            "keywords": [
                r"\b(privacidad|privacy|datos|data)\b",
                r"\b(información personal|personal information)\b",
                r"\b(cookies|gdpr|lgpd)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(qué|que|what)\b",
            ],
        },

        # ── Product Info: Material ───────────────────────────────
        InformationalSubIntent.PRODUCT_MATERIAL: {
            "keywords": [
                r"\b(material|tela|fabric|hecho.*de)\b",
                r"\b(algodón|cotton|polyester|poliéster|seda|silk)\b",
                r"\b(cuero|leather|sintético|synthetic)\b",
            ],
            "question_words": [
                r"\b(de qué|what.*made|qué tipo)\b",
                r"\b(cuál|cual|what)\b",
            ],
        },

        # ── Product Info: Sizing / Size Guide ───────────────────
        # ✅ FIX 2026-03-04: Clave actualizada de PRODUCT_SIZE → PRODUCT_SIZING
        #    para coincidir con el valor "product_sizing" en KB y Shopify.
        #
        #    BUG ANTERIOR: "What sizes do they have?" se clasificaba como
        #    PRODUCT_AVAILABILITY porque "have" está en sus keywords (+0.4)
        #    y question_words (+0.3 bonus) → score 0.7.
        #    PRODUCT_SIZING solo tenía "size" en keywords (+0.4) sin question_words
        #    → score 0.4, menor que AVAILABILITY.
        #
        #    FIX: Añadidos question_words para PRODUCT_SIZING que capturan
        #    "do they have", "what sizes", "how do I know", etc.
        #    Ahora PRODUCT_SIZING gana: keywords(0.4) + question_word(0.3) = 0.7
        #    vs AVAILABILITY: keywords(0.4) + question_word(0.3) = 0.7 (empate)
        #    → En empate gana el primero detectado (PRODUCT_SIZING por orden).
        #
        #    ALTERNATIVA si quieres más margen: añadir más keywords específicos
        #    de tallas que no aparezcan en availability (ver comentarios abajo).
        InformationalSubIntent.PRODUCT_SIZING: {
            "keywords": [
                # FIX (12/04/2026): Separado en dos patrones para que 'talla' y 'medidas'
                # puedan sumar +0.4 cada uno de forma independiente.
                # ANTES: r"\b(talla|...|medida|medidas|...)\b" -> ambas palabras = 1 match = +0.4
                # AHORA: dos patrones separados -> hasta +0.8 cuando ambas aparecen.
                # Esto resuelve queries como "¿Me puedes dar las medidas de la talla M?"
                # donde tanto 'medidas' como 'talla' son señales independientes de sizing.
                r"\b(talla|tallas|size|sizes|sizing|talle|talles)\b",   # nomenclatura de talla
                r"\b(medida|medidas|measurement|measurements|número|numero)\b",  # mediciones
                r"\b(chico|mediano|grande|pequeño|small|medium|large|xl|xxl|xs)\b",
                r"\b(guía.*de.*tallas|size.*guide|sizing.*chart|tabla.*de.*tallas)\b",
                r"\b(corre|queda|fit|fits|ajuste|ajusta)\b",
                r"\b(mido|mide|medida.*corporal|body.*measurement)\b",
                r"\b(centímetros?|cms?|inches?|pulgadas?)\b",
            ],
            "question_words": [
                r"\b(qué.*talla|what.*size|which.*size)\b",
                r"\b(cómo.*saber|how.*know|how.*find)\b",
                r"\b(cuál.*es.*mi|what.*my|which.*is.*my)\b",
                # ✅ FIX: Capturar "What sizes do they have?" / "¿Qué tallas tienen?"
                # El patrón anterior no tenía esto → perdía contra PRODUCT_AVAILABILITY
                r"\b(qué.*tallas.*tienen|what.*sizes.*do|do.*they.*have.*sizes?)\b",
                r"\b(tienen|they.*have|do.*you.*have)\b",  # Genérico pero en contexto de tallas
                # ✅ FIX (12/04/2026): Capturar queries personales de recomendación de talla.
                #
                # PROBLEMA: Queries como "Que talla me recomiendas?", "recomiendame una talla",
                # "¿Cómo sé mi talla?", "¿Está disponible en otras tallas?" y "cual es mi talla?"
                # solo matchean el keyword `talla` (+0.4) sin ningún question_word.
                # Score final = 0.4 < umbral 0.7 → cae a TRANSACTIONAL (fallback).
                #
                # SOLUCIÓN: question_words que capturan:
                #   A) Pronombres personales + verbo → "me recomiendas", "me quedo",
                #      "me pido", "soy (talla X)", "sé (mi talla)"
                #   B) Verbo recomendar con sufijo pronominal → "recomiéndame", "recomiendame"
                #   C) Adjetivo "disponible" → "¿está disponible en mi talla?"
                #   D) Verbo ser/identificar en 1P → "cual es mi talla", "cual soy"
                #
                # RIESGO DE FALSE POSITIVES: bajo. Estos patrones solo dan +0.3 bonus;
                # para llegar a 0.7 siempre se necesita un keyword de talla (+0.4).
                # "recomiéndame un vestido" (sin keyword de talla) no sería afectado.
                r"\b(me\s+recom[ie][eé]ndas?|recom[ie][eé]nd[ao]me|recommend\s+me)\b",  # recomiéndame/recomiendame
                r"\b(mi\s+talla|talla\s+me|me\s+queda|me\s+quedo|me\s+pido|soy\s+talla|my\s+size)\b",  # mi talla / soy talla
                r"\b(cómo\s+sé|como\s+se|cómo\s+me|como\s+me|how\s+do\s+i)\b",  # como sé mi talla / how do I know
                r"\b(disponible.*talla|talla.*disponible|available.*size|size.*available)\b",  # disponible en mi talla
                r"\b(cual\s+es\s+mi|cuál\s+es\s+mi|which\s+is\s+my|what\s+is\s+my)\b",  # cual es mi talla
                r"\b(me\s+recomiend|should\s+i\s+order|should\s+i\s+get)\b",  # me recomiend... / should I order
                # FIX (19/04/2026): queries informales EN que preguntan por asistencia con la talla.
                # "Can you help me choose my size?" → keywords: 'size'(+0.4); question_words: 'help'(+0.3)
                # Necesitaba 'help' como question_word para llegar a 0.7.
                r"\b(help|ayuda|ayudar|assist|guide)\b",  # 'help me choose', 'ayudame', 'guide me'
                r"\b(choose|elegir|elegirla|seleccionar|escoger|pick)\b",  # 'help me choose my size'
                r"\b(can\s+you|could\s+you|puedes|podr[ií]as)\b",  # 'can you help' en contexto de tallas
            ],
        },
        # ✅ CHANGELOG 12/04/2026: Ampliados question_words de PRODUCT_SIZING para cubrir:
        #   - "Que talla me recomiendas?" → ahora matchea via `me recomiendas`
        #   - "¿Cómo sé mi talla?" → ahora matchea via `cómo sé`
        #   - "¿Está disponible en otras tallas?" → ahora matchea via `disponible.*talla`
        #   - "cual es mi talla?" → ahora matchea via `cual es mi`
        #   - "recomiendame una talla" → ahora matchea via `recoméndame`
        #   Todos los chips del frontend de talla + queries naturales de clientes cubiertos.

        # ── Product Info: Care ───────────────────────────────────
        InformationalSubIntent.PRODUCT_CARE: {
            "keywords": [
                r"\b(lavar|wash|washing|limpieza|clean)\b",
                r"\b(cuidado|care|mantenimiento|maintenance)\b",
                r"\b(planchar|iron|secar|dry)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(puedo|puede|can)\b",
            ],
        },

        # ── Product Info: Availability ──────────────────────────
        # ⚠️  IMPORTANTE: No añadir "have/hay/tienen" a keywords aquí.
        #    Mantenerlos SOLO en question_words (bonus) para evitar que
        #    queries como "What sizes do they have?" caigan aquí en lugar
        #    de en PRODUCT_SIZING (que tiene keywords más específicos).
        InformationalSubIntent.PRODUCT_AVAILABILITY: {
            "keywords": [
                r"\b(disponible|available|availability|stock)\b",
                r"\b(cuándo.*llega|when.*arrive|when.*available)\b",
                r"\b(agotado|out.*of.*stock|sold.*out|sin.*stock)\b",
                # ✅ FIX: "hay/have/tiene" movidos a question_words.
                #    Antes estaban como keywords, lo que causaba falsos positivos
                #    cuando la query preguntaba sobre tallas ("do they have sizes").
            ],
            "question_words": [
                # ✅ FIX: "hay/have/tiene" son question_words (bonus +0.3) no keywords.
                #    Así solo suman si YA hay un keyword de disponibilidad.
                r"\b(hay|have|tiene|tienen|there.*is)\b",
                r"\b(est[aá]|est[aá]n|estan|is\s+it|still)\b(?=.*\b(disponible|available)\b)",
                r"\b(queda|quedan|left)\b(?=.*\b(stock|disponible|available)\b)",
                r"\b(sigue|todav[ií]a|todavia)\b(?=.*\b(disponible|available)\b)",
                r"\b((lo\s+)?tiene(n)?\s+en\s+stock|hay\s+stock|en\s+stock|in\s+stock|do\s+you\s+have\s+it)\b",
                r"\b(cuándo|cuando|when)\b",
            ],
        },

        # ── Account: Orders ──────────────────────────────────────
        InformationalSubIntent.ACCOUNT_ORDERS: {
            "keywords": [
                r"\b(pedido|order|orders|pedidos)\b",
                r"\b(compra|purchase|compras|purchases)\b",
                r"\b(historial.*pedidos|order.*history)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(dónde|donde|where)\b",
                r"\b(ver|see|consultar|check)\b",
            ],
        },

        # ── Account: Modifications ──────────────────────────────
        InformationalSubIntent.ACCOUNT_MODIFICATIONS: {
            "keywords": [
                r"\b(modificar|modify|cambiar|change|editar|edit)\b",
                r"\b(cuenta|account|perfil|profile)\b",
                r"\b(contraseña|password|dirección|address)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(puedo|puede|can)\b",
            ],
        },

        # ── General FAQ ──────────────────────────────────────────
        InformationalSubIntent.GENERAL_FAQ: {
            "keywords": [
                r"\b(faq|preguntas.*frecuentes|frequently.*asked)\b",
                r"\b(ayuda|help|soporte|support|contacto|contact)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(qué|que|what)\b",
            ],
        },
    }

    # ───────────────────────────────────────────────────────────
    # TRANSACTIONAL PATTERNS
    # ───────────────────────────────────────────────────────────

    TRANSACTIONAL_PATTERNS = {
        TransactionalSubIntent.PRODUCT_SEARCH: {
            "keywords": [
                r"\b(busco|buscando|estoy.*buscando|looking.*for)\b",
                r"\b(necesito|quiero|me.*interesa|need|want)\b",
                r"\b(mostrar|ver|enseñar|dame|show|display)\b",
                # FIX (09/04/2026): El patrón anterior \b(recomienda)\b no capturaba
                # "Recoméndame" ni "recómiendanos" por dos razones:
                #   1. Python re con IGNORECASE NO normaliza acentos Unicode:
                #      "recomienda" != "Recoménda" (é vs e son code points distintos).
                #   2. Los sufijos pronominales "me/te/nos/le" están fuera del grupo.
                # Solución: capturar la raíz "recomend" con variantes acentuadas
                # y sufijos opcionales, más verbos sinónimos con el mismo patrón.
                r"\b(recom[ie][eé]nda(?:me|te|nos|le|r)?|suggest|recommend(?:me)?)\b",
                r"\b(sug[ie]e?re(?:me|te|nos)?|sugerir|sugiere)\b",
                r"\b(opciones.*de|options|alternativas)\b",
                # FIX (09/04/2026): Patrones de SIMILITUD — deben ser siempre TRANSACTIONAL.
                # Queries como "Muéstrame similares", "Ver productos similares",
                # "Recoméndame parecidos a este" son peticisiones de producto, no
                # consultas informacionales. Se añaden aquí para que el rule-based
                # alcance confianza >= 0.5 y el ML no pueda hacer override a INFORMATIONAL.
                r"\b(similar(?:es)?|parecido(?:s)?|como.*este|like.*this)\b",
                r"\b(muéstrame|muestrame|enséñame|ensenname)\b",
                r"\b(más.*opciones|more.*options|otras.*opciones|other.*options)\b",
                # FIX (13/06/2026 — FR-transactional): Palabras clave de busqueda en FRANCES.
                # Problema: "Je cherche une robe pour un mariage" era clasificada INFORMATIONAL
                # (ML 0.865) porque rule-based no tenia patrones FR → ML override TRANSACTIONAL.
                # Con estos patrones, rule-based alcanza score 0.5 → GUARD protege TRANSACTIONAL.
                # Verbos de busqueda FR: chercher (buscar), montrer (mostrar), trouver (encontrar)
                r"\b(cherche|chercher|cherches|cherchons|cherchez|recherche|rechercher)\b",
                r"\b(montre|montre-moi|montrez|montrez-moi|montrer)\b",
                r"\b(recommande|recommandez|recommander|sugg[eè]re|sugg[eè]rer)\b",
                r"\b(trouver|trouve|trouvez|voudrais.*voir|je.*voudrais)\b",
            ],
        },

        TransactionalSubIntent.PRODUCT_VIEW: {
            "keywords": [
                r"\b(ver.*este|ver.*ese|see.*this|see.*that)\b",
                r"\b(detalles|details|información.*del.*producto)\b",
                r"\b(características|features|especificaciones)\b",
            ],
        },

        TransactionalSubIntent.PURCHASE_INTENT: {
            "keywords": [
                r"\b(comprar|buy|purchase|adquirir)\b",
                r"\b(llevar|me.*llevo|take|get)\b",
                r"\b(agregar.*carrito|add.*cart|añadir)\b",
                r"\b(checkout|finalizar.*compra|pay)\b",
            ],
        },

        # F-08 Fase B: Detectar peticiones de outfit/complementos.
        # Alta precisión: solo activa cuando la intención es combinar prendas,
        # no cuando pide "similares" (eso sigue siendo PRODUCT_SEARCH).
        # El handler solo ejecuta visual search si product_ctx está disponible.
        TransactionalSubIntent.OUTFIT_COMPLETION: {
            "keywords": [
                # ── Español ──────────────────────────────────────────────────
                r"\b(complet(?:a|ar|o).*(?:outfit|look|estilo))\b",
                r"\b(armar.*(?:outfit|look)|outfit.*completo|look.*completo)\b",
                r"\b(combin[ao](?:r|s)?.*(?:con|esto|esta)|qu[eé].*combin[ao])\b",
                r"\b(qu[eé].*(?:va|poner|usar).*con|what.*(?:goes|wear).*with)\b",
                r"\b(complementar|complemento|complementa.*(?:con|esto|esta))\b",
                r"\b(complemento.*(?:para|de)|un.*complemento)\b",
                r"\b(accesorio.*(?:para|que.*combine)|bolso.*que.*combine)\b",
                # ── Français (14/06/2026 — CH-multilang) ─────────────────────
                # Diseñados para que "Je cherche quelque chose qui va avec ça"
                # sume score=1.0 (2×0.5) > product_search score=0.5 ("cherche").
                # Así OUTFIT_COMPLETION gana sin tocar el GUARD.
                # Pattern A v2 (15/06/2026 — fix "vont avec"):
                # "Quels accessoires vont avec cette robe?" usaba conjugación
                # "vont" (3ª plural de aller) que no estaba cubierta.
                # Con vont/irait/iraient, cualquier forma de "aller avec" suma +0.5.
                r"\b(qui\s+va\s+avec|va\s+(?:bien\s+)?avec|vont\s+(?:bien\s+)?avec)\b",  # +0.5
                r"\b(aller\s+(?:bien\s+)?avec|irait\s+(?:bien\s+)?avec|iraient\s+(?:bien\s+)?avec)\b",
                r"\b(quelque\s+chose\s+(qui|que|pour|à))\b",                # Pattern B (+0.5)
                r"\b(compl[eé]ter\s+(la\s+tenue|le\s+look|l.outfit))\b",  # "compléter la tenue"
                r"\b(quoi\s+(mettre|porter|associer)\s+avec)\b",            # "quoi mettre avec"
                r"\b(accessoires?\s+(pour|avec|à\s+porter))\b",             # "accessoires pour/avec"
                # ── Deutsch ───────────────────────────────────────────────────
                r"\b(passend\s+zu|dazu\s+kombin|was\s+geht\s+dazu)\b",
                # ── Italiano ──────────────────────────────────────────────────
                r"\b(abbinare\s+con|cosa\s+abbinare|completare\s+il\s+look)\b",
            ],       },
    }

    # ───────────────────────────────────────────────────────────
    # QUESTION INDICATORS
    # ───────────────────────────────────────────────────────────

    QUESTION_INDICATORS = [
        r"^\s*¿",       # Spanish question start
        r"\?\s*$",      # Question mark at end
        r"\b(cómo|como|cuál|cual|cuáles|cuales|qué|que|cuándo|cuando|cuánto|cuántos|cuanto|dónde|donde|por qué|porque)\b",
        r"\b(how|what|which|when|where|why|who)\b",
        r"\b(puedo|puedes|puede|pueden|can|may|could)\b",  # FIX (12/04/2026): 'puedes' añadido — faltaba la 2ª persona singular
        r"\b(acepta|aceptan|accept|accepts)\b",
        # FIX (12/04/2026): 'saber' como indicador de pregunta informacional.
        # Cubre queries como 'Necesito saber mi talla', 'quiero saber el precio',
        # 'necesito saber si tienen envío'. Sin este fix, estas queries no pasan el
        # gate is_question=True y caen al path TRANSACTIONAL (que solo evalua keywords).
        # Riesgo de false positives: bajo — 'saber' sin contexto informacional no activa
        # ningún keyword de sub-intent, por lo que no produce falsos INFORMATIONAL.
        r"\b(saber|averiguar|conocer|entender|find\s+out|know)\b",
        r"\b(est[aá]\s+disponible|est[aá]n\s+disponibles|estan\s+disponibles|sigue\s+disponible|still\s+available)\b",
        r"\b((lo\s+)?tiene(n)?\s+en\s+stock|hay\s+stock|in\s+stock)\b",
    ]


# ═══════════════════════════════════════════════════════════════
# INTENT DETECTOR
# ═══════════════════════════════════════════════════════════════

class RuleBasedIntentDetector:
    """
    Rule-based intent detector.

    Strategy:
    1. Detect if query is a question
    2. Check for informational patterns
    3. Check for transactional patterns
    4. Default to TRANSACTIONAL (safe fallback)
    """

    def __init__(self):
        """Initialize detector."""
        self.patterns = IntentPatterns()

        # Compile regex patterns for performance — done once at init
        self._compiled_patterns = self._compile_patterns()

        # Metrics
        self.metrics = {
            "total_detections": 0,
            "informational_detected": 0,
            "transactional_detected": 0,
            "avg_confidence": 0.0,
        }

        logger.info("✅ RuleBasedIntentDetector initialized")

    def _compile_patterns(self) -> Dict:
        """
        Compile regex patterns for better performance.
        Called once during initialization.
        """
        compiled = {
            "question_indicators": [
                re.compile(pattern, re.IGNORECASE)
                for pattern in self.patterns.QUESTION_INDICATORS
            ],
            "informational": {},
            "transactional": {},
        }

        # Compile informational patterns
        for sub_intent, patterns_dict in self.patterns.INFORMATIONAL_PATTERNS.items():
            compiled["informational"][sub_intent] = {
                "keywords": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("keywords", [])
                ],
                "question_words": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("question_words", [])
                ] if "question_words" in patterns_dict else [],
                "negative_context": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("negative_context", [])
                ] if "negative_context" in patterns_dict else [],
            }

        # Compile transactional patterns
        for sub_intent, patterns_dict in self.patterns.TRANSACTIONAL_PATTERNS.items():
            compiled["transactional"][sub_intent] = {
                "keywords": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("keywords", [])
                ],
            }

        return compiled

    def detect(self, query: str, context: Optional[Dict] = None) -> IntentDetectionResult:
        """
        Detect intent from user query.

        Args:
            query: User query string
            context: Optional context (not used yet, for future expansion)

        Returns:
            IntentDetectionResult with detected intent
        """
        self.metrics["total_detections"] += 1

        logger.debug(f"Detecting intent for query: '{query[:50]}...'")

        # ═══════════════════════════════════════════════════════
        # STEP 0: Check for GREETING (before question-indicator gate)
        # ═══════════════════════════════════════════════════════
        # Greetings must be detected BEFORE the is_question() check because
        # "Hi!" and "Hola!" are not questions, so they would fall through to
        # the TRANSACTIONAL default (confidence 0.5) and return products
        # without any conversational response. Added 24/03/2026 — BUG #3 fix.

        greeting_result = self._detect_greeting(query)
        if greeting_result is not None:
            self.metrics["informational_detected"] += 1  # reuse counter (no products)
            self._update_avg_confidence(greeting_result.confidence)
            logger.info(
                f"👋 Detected GREETING (confidence: {greeting_result.confidence:.2f}) "
                f"for query: '{query[:40]}'"
            )
            return greeting_result

        # ═══════════════════════════════════════════════════════
        # STEP 1: Check if it's a question
        # ═══════════════════════════════════════════════════════

        is_question = self._is_question(query)

        # ═══════════════════════════════════════════════════════
        # STEP 2: Try informational detection
        # ═══════════════════════════════════════════════════════

        if is_question:
            info_result = self._detect_informational(query)

            if info_result and info_result.confidence >= 0.7:
                self.metrics["informational_detected"] += 1
                self._update_avg_confidence(info_result.confidence)
                logger.info(
                    f"✅ Detected INFORMATIONAL: {info_result.sub_intent} "
                    f"(confidence: {info_result.confidence:.2f})"
                )
                return info_result

        # ═══════════════════════════════════════════════════════
        # STEP 3: Try transactional detection
        # ═══════════════════════════════════════════════════════

        trans_result = self._detect_transactional(query)

        # Lower threshold for transactional (0.5) since single keyword is strong signal
        if trans_result and trans_result.confidence >= 0.5:
            self.metrics["transactional_detected"] += 1
            self._update_avg_confidence(trans_result.confidence)
            logger.info(
                f"✅ Detected TRANSACTIONAL: {trans_result.sub_intent} "
                f"(confidence: {trans_result.confidence:.2f})"
            )
            return trans_result

        # ═══════════════════════════════════════════════════════
        # STEP 4: Default fallback (TRANSACTIONAL)
        # ═══════════════════════════════════════════════════════

        logger.warning("⚠️ No clear pattern match, defaulting to TRANSACTIONAL")

        default_result = IntentDetectionResult(
            primary_intent=IntentType.TRANSACTIONAL,
            sub_intent=TransactionalSubIntent.PRODUCT_SEARCH,
            confidence=0.5,
            reasoning="Default fallback - no clear pattern matched",
            matched_patterns=[],
        )

        self.metrics["transactional_detected"] += 1
        self._update_avg_confidence(0.5)

        return default_result

    def _detect_greeting(self, query: str) -> Optional[IntentDetectionResult]:
        """
        Detect if the query is a greeting / conversational opener.

        Uses module-level _GREETING_PATTERNS (pre-compiled) for speed.
        Returns an IntentDetectionResult with IntentType.GREETING if matched,
        or None if the query is not a greeting.

        Design notes:
        - Confidence 0.95: greeting patterns are highly unambiguous.
        - sub_intent is None: greetings have no KB sub-category.
        - Called BEFORE is_question() because greetings are not questions
          and would otherwise reach the TRANSACTIONAL fallback.
        """
        query_stripped = query.strip()
        for pattern in _GREETING_PATTERNS:
            if pattern.search(query_stripped):
                return IntentDetectionResult(
                    primary_intent=IntentType.GREETING,
                    sub_intent=None,
                    confidence=0.95,
                    reasoning="Greeting pattern matched — conversational opener detected",
                    matched_patterns=[pattern.pattern],
                )
        return None

    def _is_question(self, query: str) -> bool:
        """Check if query is a question."""
        for pattern in self._compiled_patterns["question_indicators"]:
            if pattern.search(query):
                return True
        return False

    def _detect_informational(self, query: str) -> Optional[IntentDetectionResult]:
        """
        Detect informational intent and sub-intent.

        Returns best match based on:
        1. Keywords match (+0.4 each)
        2. Question words match (+0.3 bonus, one-time)
        3. Negative context (+0.2 bonus, one-time)
        """
        best_score = 0.0
        best_sub_intent = None
        matched_patterns_list: List[str] = []

        for sub_intent, patterns in self._compiled_patterns["informational"].items():
            score = 0.0
            local_matches: List[str] = []

            # ── Keywords (required) ──────────────────────────────
            keyword_matches = 0
            for pattern in patterns["keywords"]:
                if pattern.search(query):
                    keyword_matches += 1
                    local_matches.append(pattern.pattern)

            if keyword_matches == 0:
                continue  # No keyword match → skip this sub-intent entirely

            score += keyword_matches * 0.4  # Base score from keywords

            # ── Question words (bonus) ───────────────────────────
            if patterns["question_words"]:
                for pattern in patterns["question_words"]:
                    if pattern.search(query):
                        score += 0.3  # One-time bonus
                        local_matches.append(pattern.pattern)
                        break  # Only count the first matching question word

            # ── Negative context (bonus) ─────────────────────────
            if patterns["negative_context"]:
                for pattern in patterns["negative_context"]:
                    if pattern.search(query):
                        score += 0.2  # One-time bonus
                        local_matches.append(pattern.pattern)
                        break

            # ── Update best match ────────────────────────────────
            if score > best_score:
                best_score = score
                best_sub_intent = sub_intent
                matched_patterns_list = local_matches

        if best_score >= 0.4 and best_sub_intent is not None:
            confidence = min(best_score, 1.0)  # Cap at 1.0

            return IntentDetectionResult(
                primary_intent=IntentType.INFORMATIONAL,
                sub_intent=best_sub_intent.value,
                confidence=confidence,
                reasoning=f"Question + {best_sub_intent.value} keywords",
                matched_patterns=matched_patterns_list[:3],  # Limit for readability
            )

        return None

    def _detect_transactional(self, query: str) -> Optional[IntentDetectionResult]:
        """Detect transactional intent and sub-intent."""
        best_score = 0.0
        best_sub_intent = None
        matched_patterns_list: List[str] = []

        for sub_intent, patterns in self._compiled_patterns["transactional"].items():
            score = 0.0
            local_matches: List[str] = []

            for pattern in patterns["keywords"]:
                if pattern.search(query):
                    score += 0.5  # Each keyword match
                    local_matches.append(pattern.pattern)

            if score > best_score:
                best_score = score
                best_sub_intent = sub_intent
                matched_patterns_list = local_matches

        if best_score >= 0.5 and best_sub_intent is not None:
            confidence = min(best_score, 0.95)  # Cap at 0.95 (less certain than informational)

            return IntentDetectionResult(
                primary_intent=IntentType.TRANSACTIONAL,
                sub_intent=best_sub_intent.value,
                confidence=confidence,
                reasoning=f"Transactional keywords: {best_sub_intent.value}",
                matched_patterns=matched_patterns_list[:3],
            )

        return None

    def _update_avg_confidence(self, confidence: float):
        """Update rolling average confidence."""
        n = self.metrics["total_detections"]
        current_avg = self.metrics["avg_confidence"]
        self.metrics["avg_confidence"] = (current_avg * (n - 1) + confidence) / n

    def get_metrics(self) -> Dict:
        """Get detector metrics."""
        total = self.metrics["total_detections"]
        return {
            **self.metrics,
            "informational_rate": (
                self.metrics["informational_detected"] / total
                if total > 0 else 0.0
            ),
            "transactional_rate": (
                self.metrics["transactional_detected"] / total
                if total > 0 else 0.0
            ),
        }


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

# Singleton instance — lazy initialization
_detector_instance: Optional[RuleBasedIntentDetector] = None


def get_intent_detector() -> RuleBasedIntentDetector:
    """
    Get singleton instance of intent detector.
    Lazy initialization.
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = RuleBasedIntentDetector()
    return _detector_instance


def detect_intent(query: str, context: Optional[Dict] = None) -> IntentDetectionResult:
    """
    Public API for intent detection.

    Args:
        query: User query string
        context: Optional context dictionary

    Returns:
        IntentDetectionResult

    Example:
        >>> result = detect_intent("¿cuál es la política de devolución?")
        >>> print(result.primary_intent)
        IntentType.INFORMATIONAL
        >>> print(result.sub_intent)
        'policy_return'

        >>> result = detect_intent("What sizes do they have?")
        >>> print(result.sub_intent)
        'product_sizing'   # ← correcto tras el fix
    """
    detector = get_intent_detector()
    return detector.detect(query, context)