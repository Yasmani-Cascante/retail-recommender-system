"""
test_f04_customer_profile.py
============================
Script de verificacion manual de F-04 Personalizacion por Historial.

Permite probar el flujo completo sin necesitar un plan de Shopify pagado
ni un usuario logueado en la tienda. Prueba directamente contra:
  1. Shopify Admin REST API (get_customer_by_id / get_orders_by_customer)
  2. CustomerProfileService (fetch lazy + cache Redis)
  3. Endpoint MCP /v1/mcp/conversation con customer_id inyectado

USO:
    # Desde la raiz del proyecto:
    python tests/test_f04_customer_profile.py

    # Para probar con un customer_id especifico:
    python tests/test_f04_customer_profile.py --customer-id 7890123456

    # Para listar clientes disponibles en tu tienda de prueba:
    python tests/test_f04_customer_profile.py --list-customers
"""

import asyncio
import argparse
import json
import os
import sys
import time
import requests
from typing import Optional

# ── Asegurar que el proyecto raiz esta en el path ─────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ── Credenciales desde .env (cargadas manualmente para no depender de dotenv) ─
SHOPIFY_SHOP_URL   = "ai-shoppings.myshopify.com"
SHOPIFY_ACCESS_TOKEN = "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"
REDIS_HOST         = "redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com"
REDIS_PORT         = 14272
REDIS_PASSWORD     = "34rleeRxTmFYqBZpSA5UoDP71bHEq6zO"
BACKEND_URL        = "http://localhost:8000"   # servidor local
API_KEY            = "2fed9999056fab6dac5654238f0cae1c"

SHOPIFY_API_BASE   = f"https://{SHOPIFY_SHOP_URL}/admin/api/2025-01"
SHOPIFY_HEADERS    = {
    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    "Content-Type": "application/json",
}

# ─────────────────────────────────────────────────────────────────────────────
# COLORES para la salida de consola
# ─────────────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}  ✅ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}  ⚠️  {msg}{RESET}")
def err(msg):  print(f"{RED}  ❌ {msg}{RESET}")
def info(msg): print(f"{BLUE}  ℹ️  {msg}{RESET}")
def sep(title=""): print(f"\n{BOLD}{'─'*60}{RESET}")
def header(title): print(f"\n{BOLD}{BLUE}{'═'*60}\n  {title}\n{'═'*60}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Listar clientes disponibles en la tienda
# ─────────────────────────────────────────────────────────────────────────────
def test_list_customers(limit: int = 5):
    """Lista los primeros N clientes de la tienda para obtener IDs reales."""
    header("TEST 1: Listar clientes en Shopify Admin")
    
    url = f"{SHOPIFY_API_BASE}/customers.json?limit={limit}"
    try:
        resp = requests.get(url, headers=SHOPIFY_HEADERS, timeout=10)
        resp.raise_for_status()
        customers = resp.json().get("customers", [])
        
        if not customers:
            warn("No hay clientes en la tienda. Crea al menos uno en Shopify Admin.")
            return None
        
        ok(f"Se encontraron {len(customers)} clientes:")
        for c in customers:
            print(f"\n    ID:           {BOLD}{c['id']}{RESET}")
            print(f"    Nombre:       {c.get('first_name','')} {c.get('last_name','')}")
            print(f"    Email:        {c.get('email','')}")
            print(f"    Pedidos:      {c.get('orders_count', 0)}")
            print(f"    Total gastado:{c.get('total_spent', '0.00')}")
            print(f"    Tags:         {c.get('tags','(ninguno)')}")
        
        return customers[0]["id"]  # retorna el ID del primero
        
    except requests.exceptions.RequestException as e:
        err(f"Error conectando a Shopify: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Fetch directo desde Shopify REST API
# ─────────────────────────────────────────────────────────────────────────────
def test_shopify_rest_fetch(customer_id: str):
    """
    Verifica que get_customer_by_id y get_orders_by_customer funcionan.
    Prueba directamente el endpoint REST de Shopify, sin pasar por el backend.
    """
    header(f"TEST 2: Fetch Shopify REST para customer_id={customer_id}")
    
    # 2a. Perfil del cliente
    sep()
    info("2a. GET /customers/{id}.json")
    url = f"{SHOPIFY_API_BASE}/customers/{customer_id}.json"
    try:
        resp = requests.get(url, headers=SHOPIFY_HEADERS, timeout=10)
        resp.raise_for_status()
        customer = resp.json().get("customer", {})
        
        ok(f"Cliente encontrado: {customer.get('first_name')} {customer.get('last_name')}")
        
        # Verificar campos críticos para F-04
        campos = {
            "id":           customer.get("id"),
            "total_spent":  customer.get("total_spent"),
            "orders_count": customer.get("orders_count"),
            "tags":         customer.get("tags"),
            "email":        customer.get("email"),
        }
        for campo, valor in campos.items():
            if valor is not None and valor != "":
                ok(f"{campo}: {valor}")
            else:
                warn(f"{campo}: vacío (normal para clientes nuevos)")
        
        print(f"\n  {YELLOW}Nota Shopify 2025-01:{RESET} Los campos total_spent, orders_count")
        print(f"  y tags siguen disponibles en el endpoint REST (no fueron eliminados).")
        print(f"  Solo se eliminaron del payload del WEBHOOK customers/update.")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            err(f"Cliente {customer_id} no existe en la tienda")
        else:
            err(f"Error HTTP {e.response.status_code}: {e}")
        return False
    except Exception as e:
        err(f"Error: {e}")
        return False
    
    # 2b. Órdenes del cliente
    sep()
    info(f"2b. GET /orders.json?customer_id={customer_id}")
    url = f"{SHOPIFY_API_BASE}/orders.json?customer_id={customer_id}&status=any&limit=5"
    try:
        resp = requests.get(url, headers=SHOPIFY_HEADERS, timeout=10)
        resp.raise_for_status()
        orders = resp.json().get("orders", [])
        
        if not orders:
            warn("El cliente no tiene órdenes todavía")
            info("Para probar preferred_categories, crea una orden en Shopify Admin")
        else:
            ok(f"{len(orders)} orden(es) encontradas")
            for order in orders[:3]:
                items = order.get("line_items", [])
                print(f"\n    Orden #{order.get('order_number')} — {order.get('total_price')} {order.get('currency')}")
                for item in items:
                    print(f"      • {item.get('title')} [{item.get('product_type','sin categoria')}]")
        
        return True
        
    except Exception as e:
        err(f"Error obteniendo órdenes: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — CustomerProfileService (async, usa Redis)
# ─────────────────────────────────────────────────────────────────────────────
async def test_customer_profile_service(customer_id: str):
    """
    Prueba CustomerProfileService directamente:
    - Cache miss → fetch Shopify → build_profile → save Redis
    - Cache hit → retorna desde Redis en <5ms
    - Invalidation → elimina la clave de Redis
    """
    header(f"TEST 3: CustomerProfileService para customer_id={customer_id}")
    
    try:
        # Inicializar dependencias como lo hace el backend
        from src.api.integrations.shopify_client import ShopifyIntegration
        from src.api.mcp_services.customer.service import CustomerProfileService

        # Usar Redis real
        try:
            import redis.asyncio as aioredis
            redis_client_raw = aioredis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                decode_responses=True,
                ssl=False,
            )
            # Envolver en una clase simple compatible con el servicio
            class SimpleRedis:
                def __init__(self, r): self._r = r
                async def get_json(self, key):
                    v = await self._r.get(key)
                    return json.loads(v) if v else None
                async def set_json(self, key, value, ttl=None):
                    await self._r.set(key, json.dumps(value), ex=ttl)
                async def delete(self, key):
                    await self._r.delete(key)
            redis_service = SimpleRedis(redis_client_raw)
            ok("Redis conectado")
        except Exception as e:
            warn(f"Redis no disponible ({e}), usando modo sin cache")
            redis_service = None
        
        # Cliente Shopify real
        shopify = ShopifyIntegration(
            shop_url=SHOPIFY_SHOP_URL,
            access_token=SHOPIFY_ACCESS_TOKEN,
        )
        
        service = CustomerProfileService(
            redis_service=redis_service,
            shopify_client=shopify,
        )
        
        # ── 3a. Primera llamada (cache miss) ─────────────────────────────
        sep()
        info("3a. Primera llamada → debe hacer fetch a Shopify (cache miss)")
        t0 = time.time()
        profile = await service.get_profile(customer_id)
        elapsed_ms = (time.time() - t0) * 1000
        
        if profile is None:
            err(f"get_profile retornó None — verifica que customer_id={customer_id} existe")
            return
        
        ok(f"Perfil obtenido en {elapsed_ms:.0f}ms (incluye fetch Shopify)")
        print()
        
        # Mostrar el perfil completo
        fields = [
            ("shopify_id",           "ID Shopify"),
            ("orders_count",         "Número de pedidos"),
            ("total_spent",          "Total gastado (LTV)"),
            ("ltv_tier",             "Tier de cliente"),
            ("tags",                 "Tags de segmentación"),
            ("preferred_categories", "Categorías preferidas"),
            ("top_brands",           "Marcas preferidas"),
            ("last_order_date",      "Fecha última compra"),
        ]
        for key, label in fields:
            value = profile.get(key)
            if value and value != [] and value != "":
                icon = "🎯" if key == "ltv_tier" else "📊" if key in ("total_spent","orders_count") else "•"
                print(f"    {icon} {label}: {BOLD}{value}{RESET}")
            else:
                print(f"      {label}: {YELLOW}vacío{RESET}")
        
        # Verificar que el tier es correcto
        tier = profile.get("ltv_tier", "?")
        total = float(profile.get("total_spent", 0))
        orders = int(profile.get("orders_count", 0))
        sep()
        
        tier_logic = {
            "vip":       total >= 500,
            "loyal":     total >= 200 or orders >= 5,
            "returning": total >= 50  or orders >= 2,
            "new":       True,
        }
        expected = next(t for t, cond in tier_logic.items() if cond)
        
        if tier == expected:
            ok(f"LTV tier correcto: '{tier}' (total={total}, orders={orders})")
        else:
            warn(f"LTV tier inesperado: '{tier}' (esperado '{expected}' con total={total}, orders={orders})")
        
        # ── 3b. Segunda llamada (cache hit) ──────────────────────────────
        if redis_service:
            sep()
            info("3b. Segunda llamada → debe venir de Redis (cache hit)")
            t0 = time.time()
            profile2 = await service.get_profile(customer_id)
            elapsed_ms2 = (time.time() - t0) * 1000
            
            if elapsed_ms2 < 50:
                ok(f"Cache hit en {elapsed_ms2:.1f}ms  ← Redis funcionando correctamente")
            else:
                warn(f"Tardó {elapsed_ms2:.1f}ms — ¿problema con Redis?")
            
            # ── 3c. Invalidación ─────────────────────────────────────────
            sep()
            info("3c. Invalidar cache (simula llegada de webhook customers/update)")
            await service.invalidate(customer_id)
            ok("Cache invalidado")
            
            t0 = time.time()
            profile3 = await service.get_profile(customer_id)
            elapsed_ms3 = (time.time() - t0) * 1000
            
            if elapsed_ms3 > 100:
                ok(f"Post-invalidación: fetch Shopify en {elapsed_ms3:.0f}ms  ← ciclo completo funciona")
            else:
                info(f"Post-invalidación completado en {elapsed_ms3:.0f}ms")
        
        print()
        ok("CustomerProfileService funciona end-to-end")
        return profile
        
    except ImportError as e:
        err(f"Error importando módulos: {e}")
        info("Asegúrate de correr desde la raíz del proyecto con el virtualenv activado")
        return None
    except Exception as e:
        err(f"Error en CustomerProfileService: {e}")
        import traceback
        traceback.print_exc()
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Endpoint MCP completo con customer_id
# ─────────────────────────────────────────────────────────────────────────────
def test_mcp_endpoint_with_customer(customer_id: str, query: str = "busco algo informal"):
    """
    Envía un mensaje al endpoint /v1/mcp/conversation con customer_id en
    widget_context. Verifica que el backend lo procese y el perfil aparezca
    en los logs.

    Si el servidor local no está corriendo, muestra el curl equivalente
    para usar manualmente o con el servidor en producción.
    """
    header("TEST 4: Endpoint MCP con customer_id inyectado")
    
    payload = {
        "query": query,
        "user_id": f"test_user_{customer_id}",
        "market_id": "CH",
        "language": "es",
        "widget_context": {
            "page_url": "https://ai-shoppings.myshopify.com/",
            "page_type": "general",
            "user_agent": "TestScript/1.0 F04Verification",
            "customer_id": str(customer_id),       # ← el campo clave de F-04
        }
    }
    
    info("Payload que se enviará:")
    print(json.dumps(payload, indent=4, ensure_ascii=False))
    
    # ── Intentar con el servidor local ───────────────────────────────────
    sep()
    info(f"Enviando request a {BACKEND_URL}...")
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/v1/mcp/conversation",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            json=payload,
            timeout=30,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            ok(f"Respuesta recibida en {data.get('took_ms', '?'):.0f}ms")
            
            # Verificar la respuesta del asistente
            answer = data.get("answer", "")
            print(f"\n  {BOLD}Respuesta del asistente:{RESET}")
            print(f"  {answer[:300]}")
            
            # Buscar indicios de personalización en la respuesta
            personalization_meta = data.get("personalization_metadata", {})
            if personalization_meta:
                ok(f"Personalización activa: strategy={personalization_meta.get('strategy_used','?')}")
            
            print()
            ok("El endpoint MCP recibió el customer_id correctamente")
            print()
            info("VERIFICA EN LOS LOGS DEL SERVIDOR que aparezcan estas líneas:")
            print(f"    {GREEN}customer_profile_cache_miss_fetching  customer_id={customer_id}{RESET}")
            print(f"    {GREEN}customer_profile_injected  ltv_tier=<tier>  preferred_categories=[...]{RESET}")
            
            return True
            
        else:
            warn(f"Servidor respondió con HTTP {resp.status_code}")
            try:
                print(f"  Detalle: {resp.json()}")
            except Exception:
                print(f"  Body: {resp.text[:200]}")
    
    except requests.exceptions.ConnectionError:
        warn("El servidor local no está corriendo.")
    except Exception as e:
        warn(f"Error conectando al servidor local: {e}")
    
    # ── Fallback: mostrar curl para test manual ───────────────────────────
    sep()
    info("Usa este comando para probar manualmente (servidor local o producción):")
    print()
    
    curl_local = f"""curl -X POST {BACKEND_URL}/v1/mcp/conversation \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: {API_KEY}" \\
  -d '{json.dumps(payload)}'"""
    
    prod_url = "https://retail-recommender-lzf2y6pspa-uc.a.run.app"
    curl_prod = f"""curl -X POST {prod_url}/v1/mcp/conversation \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: {API_KEY}" \\
  -d '{json.dumps(payload)}'"""
    
    print(f"  {BOLD}Local:{RESET}")
    print(f"  {curl_local}")
    print()
    print(f"  {BOLD}Producción (Cloud Run):{RESET}")
    print(f"  {curl_prod}")
    
    return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — Verificar que usuario anónimo no rompe nada
# ─────────────────────────────────────────────────────────────────────────────
def test_anonymous_user():
    """Verifica que el sistema funciona correctamente sin customer_id."""
    header("TEST 5: Usuario anónimo (sin customer_id)")
    
    payload = {
        "query": "busco un vestido",
        "user_id": "anon_test_user",
        "market_id": "CL",
        "language": "es",
        "widget_context": {
            "page_url": "https://ai-shoppings.myshopify.com/",
            "page_type": "general",
            "user_agent": "TestScript/1.0",
            # Sin customer_id → usuario anónimo
        }
    }
    
    info("Payload sin customer_id (usuario anónimo):")
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/v1/mcp/conversation",
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            ok("Usuario anónimo funciona correctamente (degradación graciosa)")
            ok("No aparecerá 'customer_profile_injected' en los logs — correcto")
        else:
            warn(f"HTTP {resp.status_code}")
    except requests.exceptions.ConnectionError:
        info("Servidor no disponible — test saltado")
    except Exception as e:
        warn(f"Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(customer_id: Optional[str]):
    header("RESUMEN — Qué verificar en los logs del servidor")
    
    print(f"""
  {BOLD}Cuando F-04 funciona correctamente, los logs muestran:{RESET}

  {GREEN}# Primera request con este customer_id (cache miss):{RESET}
  customer_profile_cache_miss_fetching  customer_id={customer_id or 'XXXX'}
  customer_profile_injected  customer_id={customer_id or 'XXXX'}  ltv_tier=returning

  {GREEN}# Segunda request (cache hit — Redis, ~1ms):{RESET}
  customer_profile_cache_hit  customer_id={customer_id or 'XXXX'}
  customer_profile_injected  customer_id={customer_id or 'XXXX'}  ltv_tier=returning

  {GREEN}# Cuando llega webhook customers/update o customers/purchasing_summary:{RESET}
  customers_webhook_accepted  customer_id={customer_id or 'XXXX'}  topic=customers/update
  webhook_customer_invalidating_cache  customer_id={customer_id or 'XXXX'}
  customer_profile_cache_invalidated  customer_id={customer_id or 'XXXX'}

  {BOLD}El prompt de Claude incluirá algo como:{RESET}
  Perfil cliente: Cliente recurrente — puedes mencionar que conoce la tienda.
  Categorias preferidas: Vestidos, Chaquetas.
""")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
async def run_all_tests(customer_id: Optional[str], list_only: bool):
    print(f"""
{BOLD}{BLUE}╔══════════════════════════════════════════════════════════╗
║   F-04 Verificación — Personalización por Historial      ║
║   Retail Recommender System v2.1.0                        ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")
    
    # Test 1: listar clientes (siempre)
    first_id = test_list_customers(limit=5)
    
    if list_only:
        info("Modo --list-customers: terminando aquí.")
        info(f"Usa: python tests/test_f04_customer_profile.py --customer-id <ID>")
        return
    
    # Decidir qué customer_id usar
    target_id = customer_id or first_id
    
    if not target_id:
        err("No hay clientes disponibles. Crea al menos uno en Shopify Admin → Customers.")
        return
    
    print(f"\n{BOLD}  Usando customer_id: {GREEN}{target_id}{RESET}")
    
    # Test 2: Shopify REST directo
    shopify_ok = test_shopify_rest_fetch(str(target_id))
    
    if not shopify_ok:
        err("El fetch de Shopify falló — el resto de los tests no tiene sentido continuar")
        return
    
    # Test 3: CustomerProfileService (async)
    profile = await test_customer_profile_service(str(target_id))
    
    # Test 4: Endpoint MCP completo
    if profile:
        test_mcp_endpoint_with_customer(str(target_id))
    
    # Test 5: Usuario anónimo
    test_anonymous_user()
    
    # Resumen
    print_summary(str(target_id))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verifica F-04 Personalización por Historial sin plan Shopify pagado"
    )
    parser.add_argument(
        "--customer-id",
        type=str,
        help="ID del cliente Shopify a usar (ej: 7890123456). "
             "Si no se especifica, usa el primero de la lista.",
    )
    parser.add_argument(
        "--list-customers",
        action="store_true",
        help="Solo listar los clientes disponibles y salir",
    )
    args = parser.parse_args()
    
    asyncio.run(run_all_tests(
        customer_id=args.customer_id,
        list_only=args.list_customers,
    ))
