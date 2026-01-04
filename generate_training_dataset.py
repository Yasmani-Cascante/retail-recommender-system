"""
Dataset Generator para AI-shoppings
====================================

Genera 6,000 queries de entrenamiento personalizadas usando Claude API

Autor: AI Assistant
Fecha: 27 Diciembre 2025
Costo estimado: $1.50 USD
"""

import os
import json
import csv
import asyncio
import re
from anthropic import AsyncAnthropic
from typing import List, Dict
import time

# Configuración
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OUTPUT_FILE = "ai-shoppings-training-dataset-6000.csv"
STATS_FILE = "dataset-stats.json"
SAMPLE_FILE = "sample-queries.txt"

# Cliente Anthropic
client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Configuración de la tienda
STORE_CONFIG = {
    "name": "AI-shoppings",
    "niche": "Moda femenina para eventos especiales",
    "products": {
        "vestidos_fiesta": {
            "modelos": ["Emma", "Leire", "Alexa", "Lorena", "Camila", "Victoria", "Lia", "Cayetana", "Elena"],
            "tipos": ["cortos", "largos", "novias"],
            "tallas": ["XS", "S", "M", "L"],
            "material": "satín"
        },
        "lenceria": {
            "modelos": ["Camila", "Florencia", "Isidora", "Jacinta", "Julieta", "Laura", "Mia", "Lucia", "Mila", "Olivia"],
            "tipos": ["bralettes", "brami", "ropa interior"],
            "tallas": ["A", "B", "C", "D"],
            "caracteristicas": ["sin costuras", "invisible", "adhesivo"]
        },
        "productos_adhesivos": {
            "tipos": ["bras invisibles", "parches levanta busto", "pezoneras", "calzón adhesivo", 
                     "cinta doble contacto", "sostén de silicona"],
            "material": "biogel adhesivo, silicona"
        },
        "complementos": {
            "bolsos": ["Leonor", "Lorenza"],
            "aretes": ["aros acrílicos", "aros con piedras"],
            "tocados": ["tocados de novia", "peinetas", "accesorios para el cabello"]
        }
    },
    "policies": {
        "devolucion": {
            "dias": 30,
            "condiciones": "sin usar, con etiquetas, empaque original",
            "excepciones": "lencería y accesorios sin cambio por higiene",
            "reembolso": "10 días hábiles"
        },
        "envio": {
            "gratis": ">$50 USD",
            "costo": "$5.99 <$50",
            "tiempo": "3-5 días hábiles"
        },
        "pago": ["tarjeta crédito", "tarjeta débito", "PayPal", "transferencia"]
    },
    "markets": {
        "CL": {"weight": 0.40, "style": "formal_mix", "currency": "CLP"},
        "MX": {"weight": 0.25, "style": "informal", "currency": "MXN"},
        "ES": {"weight": 0.25, "style": "vosotros", "currency": "EUR"},
        "US": {"weight": 0.10, "style": "english", "currency": "USD"}
    }
}

# Distribución del dataset
DATASET_DISTRIBUTION = {
    "INFORMATIONAL": {
        "total": 2400,
        "sub_intents": {
            "policy_return": 800,
            "policy_shipping": 600,
            "policy_payment": 400,
            "product_material": 200,
            "product_size": 200,
            "product_care": 200
        }
    },
    "TRANSACTIONAL": {
        "total": 3600,
        "sub_intents": {
            "product_search": 2400,
            "purchase_intent": 800,
            "product_view": 400
        }
    }
}


async def generate_queries_batch(
    intent_type: str,
    sub_intent: str,
    count: int,
    market: str = "CL"
) -> List[Dict]:
    """
    Genera un batch de queries usando Claude API
    
    Args:
        intent_type: INFORMATIONAL o TRANSACTIONAL
        sub_intent: Sub-categoría específica
        count: Número de queries a generar
        market: Mercado (CL, MX, ES, US)
    
    Returns:
        Lista de queries generadas
    """
    
    # Contexto de la tienda
    store_context = json.dumps(STORE_CONFIG, indent=2, ensure_ascii=False)
    
    # Estilo según mercado
    market_styles = {
        "CL": "español chileno (chilenismos como 'cuánto sale', 'despacho', mix formal/informal)",
        "MX": "español mexicano (mexicanismos como 'qué onda', '¿manejan...?', informal predominante)",
        "ES": "español de España (vosotros, peninsularismos como 'cuánto vale', '¿hacéis...?')",
        "US": "inglés americano o español latino neutro"
    }
    
    # Ejemplos específicos por sub-intent
    examples = {
        "policy_return": [
            "¿puedo devolver un vestido después de probarlo?",
            "cuántos días tengo para hacer un cambio",
            "la lencería se puede devolver si no me queda?"
        ],
        "policy_shipping": [
            "cuánto cuesta el envío a Santiago",
            "hacen envíos internacionales",
            "en cuántos días llega mi pedido"
        ],
        "policy_payment": [
            "aceptan PayPal",
            "puedo pagar en cuotas",
            "qué métodos de pago tienen"
        ],
        "product_material": [
            "el vestido Emma es de satín",
            "qué tela tiene el vestido largo",
            "los bralettes son de algodón"
        ],
        "product_size": [
            "tienen el vestido Alexa en talla S",
            "cómo saber mi talla de bralette",
            "las tallas son europeas o americanas"
        ],
        "product_care": [
            "cómo lavar el vestido de satín",
            "se puede planchar la lencería",
            "cuidados del bra invisible"
        ],
        "product_search": [
            "busco vestido largo para boda en playa",
            "necesito bralette color nude sin costuras",
            "clutch dorado para fiesta"
        ],
        "purchase_intent": [
            "quiero comprar el vestido Emma en talla M",
            "llevaré la lencería Florencia",
            "me interesa el conjunto EVA de novia"
        ],
        "product_view": [
            "ver detalles del vestido Leire",
            "características del tocado de novia",
            "fotos del bralette Mia"
        ]
    }
    
    prompt = f"""
Eres un experto en generar queries de usuarios REALES para una tienda e-commerce.

CONTEXTO DE LA TIENDA:
{store_context}

TAREA:
Genera {count} queries de usuarios en {market_styles[market]} que correspondan a:

Intent Type: {intent_type}
Sub-Intent: {sub_intent}
Mercado: {market}

REQUISITOS CRÍTICOS:

1. NATURALIDAD:
   - Queries REALES como las escribiría un usuario
   - Variedad de formalismos (tú/usted según mercado)
   - Errores ocasionales (5%): typos, sin acentos, mayúsculas incorrectas
   - Longitud variable: cortas (3-5 palabras) y detalladas (10-15 palabras)

2. DIVERSIDAD:
   - Diferentes formas de preguntar lo mismo
   - Con y sin signos de interrogación
   - Con y sin acentos (30% sin acentos)
   - Variantes regionales del mercado {market}

3. ESPECIFICIDAD AI-SHOPPINGS:
   - Mencionar productos reales: vestidos (Emma, Leire, Alexa...), bralettes (Florencia, Mia...)
   - Ocasiones: bodas, fiestas, eventos nocturnos, galas
   - Características: "sin costuras", "invisible", "adhesivo", "satín"
   - Tallas reales: XS, S, M, L (ropa), A, B, C, D (lencería)

4. CONTEXTO DE EVENTOS ESPECIALES:
   - "vestido para invitada de boda"
   - "lencería invisible para vestido escotado"
   - "clutch para ceremonia"
   - "tocado de novia elegante"

EJEMPLOS para {sub_intent}:
{json.dumps(examples.get(sub_intent, []), ensure_ascii=False, indent=2)}

FORMATO DE SALIDA - SOLO TEXTO PLANO:

Genera EXACTAMENTE {count} queries, UNA POR LÍNEA.
NO agregues números, viñetas, ni otro formato.
SOLO las queries, una por línea.

Ejemplo de formato correcto:
¿Puedo devolver un vestido si no me queda bien?
cuanto tiempo tengo para devolver
¿Se puede cambiar lencería?
la politica de devolucion es de 30 dias
quiero saber si aceptan devoluciones

GENERA {count} QUERIES AHORA (solo texto, una por línea):
"""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.8,  # Mayor creatividad para diversidad
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extraer texto de la respuesta
        response_text = response.content[0].text
        
        # Limpiar markdown si existe
        if "```" in response_text:
            # Extraer contenido entre ```
            parts = response_text.split("```")
            if len(parts) >= 3:
                response_text = parts[1]
                # Remover etiqueta de lenguaje si existe
                if response_text.startswith('text') or response_text.startswith('plaintext'):
                    response_text = '\n'.join(response_text.split('\n')[1:])
        
        response_text = response_text.strip()
        
        # ✅ NUEVO PARSER: Procesar línea por línea (texto plano)
        queries = []
        lines = response_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Saltar líneas vacías
            if not line:
                continue
            
            # Saltar líneas que parecen encabezados o números
            if line.startswith('#') or line.startswith('*') or line.startswith('-'):
                continue
            
            # Remover números al inicio (1. query, 2. query, etc.)
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            
            # Si la línea tiene contenido, es una query
            if len(line) > 3:  # Mínimo 3 caracteres
                # Detectar metadata de la query
                has_accents = any(c in line for c in 'áéíóúñÁÉÍÓÚÑ¿¡')
                has_question = '?' in line
                
                # Detectar si menciona productos
                mentioned_product = "null"
                for product in ["Emma", "Leire", "Alexa", "Lorena", "Camila", "Victoria", 
                               "Lia", "Cayetana", "Elena", "Florencia", "Isidora", "Jacinta",
                               "Julieta", "Laura", "Mia", "Lucia", "Mila", "Olivia", "Leonor", "Lorenza"]:
                    if product.lower() in line.lower():
                        mentioned_product = product
                        break
                
                # Detectar ocasión
                occasion = "null"
                if "boda" in line.lower() or "novia" in line.lower():
                    occasion = "boda"
                elif "fiesta" in line.lower() or "evento" in line.lower():
                    occasion = "fiesta"
                elif "gala" in line.lower() or "ceremonia" in line.lower():
                    occasion = "gala"
                
                # Detectar formalidad
                variant = "neutral"
                if "usted" in line.lower() or line.startswith("¿"):
                    variant = "formal"
                elif any(word in line.lower() for word in ["qué onda", "checa", "sale"]):
                    variant = "informal"
                
                # Detectar typos (heurística simple)
                has_typo = False
                # Palabras comunes mal escritas
                if any(word in line.lower() for word in ["politica", "devolucion", "envio", "metodo"]):
                    if not has_accents:  # Probablemente es sin acento intencional, no typo
                        has_typo = False
                
                queries.append({
                    "text": line,
                    "variant": variant,
                    "has_typo": has_typo,
                    "has_accents": has_accents,
                    "mentions_product": mentioned_product,
                    "occasion": occasion,
                    "confidence_expected": "HIGH" if has_question else "MEDIUM"
                })
        
        if len(queries) == 0:
            print(f"❌ No se pudieron extraer queries del texto")
            print(f"Response preview:")
            print(response_text[:500])
            return []
        
        # Agregar metadata
        for q in queries:
            q.update({
                "primary_intent": intent_type,
                "sub_intent": sub_intent,
                "market": market,
                "language": "en" if market == "US" and "?" in q.get("text", "") else "es",
                "source": "claude_synthetic",
                "timestamp": time.time()
            })
        
        print(f"✅ Generated {len(queries)} queries for {sub_intent} ({market})")
        return queries
        
    except Exception as e:
        print(f"❌ Error generating batch: {e}")
        import traceback
        traceback.print_exc()
        return []


async def generate_complete_dataset():
    """
    Genera el dataset completo de 6,000 queries
    """
    
    all_queries = []
    total_generated = 0
    
    print("=" * 80)
    print("🚀 GENERANDO DATASET PARA AI-SHOPPINGS")
    print("=" * 80)
    print()
    
    # FASE 1: Queries INFORMACIONALES (2,400 queries)
    print("📚 FASE 1: Generando queries INFORMACIONALES (2,400)")
    print("-" * 80)
    
    for sub_intent, count in DATASET_DISTRIBUTION["INFORMATIONAL"]["sub_intents"].items():
        # Distribuir por mercados
        market_distribution = {
            "CL": int(count * 0.40),
            "MX": int(count * 0.25),
            "ES": int(count * 0.25),
            "US": int(count * 0.10)
        }
        
        for market, market_count in market_distribution.items():
            if market_count > 0:
                queries = await generate_queries_batch(
                    "INFORMATIONAL",
                    sub_intent,
                    market_count,
                    market
                )
                all_queries.extend(queries)
                total_generated += len(queries)
                
                print(f"   ✓ {sub_intent} ({market}): {len(queries)} queries")
                
                # Delay para evitar rate limits
                await asyncio.sleep(1)
    
    print()
    print(f"✅ FASE 1 completada: {total_generated} queries informacionales generadas")
    print()
    
    # FASE 2: Queries TRANSACCIONALES (3,600 queries)
    print("🛍️ FASE 2: Generando queries TRANSACCIONALES (3,600)")
    print("-" * 80)
    
    phase2_start = total_generated
    
    for sub_intent, count in DATASET_DISTRIBUTION["TRANSACTIONAL"]["sub_intents"].items():
        # Distribuir por mercados
        market_distribution = {
            "CL": int(count * 0.40),
            "MX": int(count * 0.25),
            "ES": int(count * 0.25),
            "US": int(count * 0.10)
        }
        
        for market, market_count in market_distribution.items():
            if market_count > 0:
                queries = await generate_queries_batch(
                    "TRANSACTIONAL",
                    sub_intent,
                    market_count,
                    market
                )
                all_queries.extend(queries)
                total_generated += len(queries)
                
                print(f"   ✓ {sub_intent} ({market}): {len(queries)} queries")
                
                # Delay para evitar rate limits
                await asyncio.sleep(1)
    
    print()
    print(f"✅ FASE 2 completada: {total_generated - phase2_start} queries transaccionales generadas")
    print()
    
    # FASE 3: Guardar dataset
    print("💾 FASE 3: Guardando dataset...")
    print("-" * 80)
    
    # Guardar CSV para Vertex AI
    csv_file = OUTPUT_FILE
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'text', 'primary_intent', 'sub_intent', 'market', 'language',
            'variant', 'has_typo', 'has_accents', 'mentions_product', 
            'occasion', 'confidence_expected', 'source', 'timestamp'
        ])
        writer.writeheader()
        writer.writerows(all_queries)
    
    print(f"✅ CSV guardado: {csv_file}")
    
    # Generar estadísticas
    stats = {
        "total_queries": len(all_queries),
        "by_intent": {},
        "by_market": {},
        "by_language": {},
        "with_typos": sum(1 for q in all_queries if q.get("has_typo")),
        "without_accents": sum(1 for q in all_queries if not q.get("has_accents")),
        "mentions_products": sum(1 for q in all_queries if q.get("mentions_product") != "null"),
        "generation_time": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Contar por intent
    for q in all_queries:
        intent = q["primary_intent"]
        stats["by_intent"][intent] = stats["by_intent"].get(intent, 0) + 1
        
        market = q["market"]
        stats["by_market"][market] = stats["by_market"].get(market, 0) + 1
        
        lang = q["language"]
        stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Estadísticas guardadas: {STATS_FILE}")
    
    # Guardar sample
    sample_queries = all_queries[:100]
    with open(SAMPLE_FILE, 'w', encoding='utf-8') as f:
        f.write("SAMPLE QUERIES (100 primeras)\n")
        f.write("=" * 80 + "\n\n")
        for i, q in enumerate(sample_queries, 1):
            f.write(f"{i}. {q['text']}\n")
            f.write(f"   Intent: {q['primary_intent']} > {q['sub_intent']}\n")
            f.write(f"   Market: {q['market']} | Lang: {q['language']}\n\n")
    
    print(f"✅ Sample guardado: {SAMPLE_FILE}")
    print()
    
    # Resumen final
    print("=" * 80)
    print("✅ DATASET GENERADO EXITOSAMENTE")
    print("=" * 80)
    print()
    print(f"📊 Total queries: {len(all_queries)}")
    print(f"📚 Informacionales: {stats['by_intent'].get('INFORMATIONAL', 0)}")
    print(f"🛍️ Transaccionales: {stats['by_intent'].get('TRANSACTIONAL', 0)}")
    print()
    print("🌍 Por mercado:")
    for market, count in stats['by_market'].items():
        pct = (count / len(all_queries)) * 100
        print(f"   {market}: {count} ({pct:.1f}%)")
    print()
    print("🌐 Por idioma:")
    for lang, count in stats['by_language'].items():
        pct = (count / len(all_queries)) * 100
        print(f"   {lang}: {count} ({pct:.1f}%)")
    print()
    print(f"📁 Archivos generados:")
    print(f"   - {csv_file}")
    print(f"   - {STATS_FILE}")
    print(f"   - {SAMPLE_FILE}")
    print()
    print("🎯 DATASET LISTO PARA VERTEX AI")
    print("=" * 80)


if __name__ == "__main__":
    # Verificar API key
    if not ANTHROPIC_API_KEY:
        print("❌ Error: ANTHROPIC_API_KEY no encontrada en variables de entorno")
        exit(1)
    
    # Ejecutar generación
    asyncio.run(generate_complete_dataset())