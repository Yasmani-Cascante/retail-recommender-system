"""
Script de invalidación de cache Redis para SizeProfile.

Necesario cuando:
  - Se actualiza la lógica de SizeProfileService (ej. fix confidence_by_category)
  - El cache contiene un perfil con schema viejo (sin confidence_by_category)
  - Se quiere forzar recálculo desde Shopify

La clave Redis es: mcp:size:profile:{customer_id}

Uso:
  # Invalidar un cliente específico (el cliente de prueba del fix):
  python scripts/invalidate_size_profile_cache.py --customer-id 8831066177845

  # Listar instrucciones para invalidar todos los perfiles:
  python scripts/invalidate_size_profile_cache.py --all

  # Dry-run: mostrar qué se haría sin ejecutar:
  python scripts/invalidate_size_profile_cache.py --customer-id 8831066177845 --dry-run
"""

import asyncio
import os
import sys
import argparse

# Asegurar que el root del proyecto está en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SIZE_PROFILE_KEY_PREFIX = "mcp:size:profile:"


async def invalidate_one(customer_id: str, dry_run: bool = False) -> None:
    """Invalida el cache de size profile para un cliente específico."""
    key = f"{SIZE_PROFILE_KEY_PREFIX}{customer_id}"

    if dry_run:
        print(f"[DRY-RUN] Habría eliminado: {key}")
        return

    try:
        from src.api.factories.service_factory import ServiceFactory
        sps = await ServiceFactory.get_size_profile_service()

        if sps is None:
            print("ERROR: SizeProfileService no disponible (ServiceFactory retornó None).")
            print("Intenta manualmente:")
            print(f"  redis-cli DEL {key}")
            return

        await sps.invalidate(customer_id)
        print(f"✅ Cache invalidado para customer_id={customer_id}")
        print(f"   Clave eliminada: {key}")
        print()
        print("El próximo request recalculará el perfil con el nuevo algoritmo")
        print("(confidence_by_category) y lo guardará con TTL 24h.")

    except ImportError as e:
        # Entorno sin el módulo disponible — dar instrucción manual
        print(f"ERROR: No se pudo importar ServiceFactory: {e}")
        print()
        print("Elimina la clave manualmente desde Redis CLI:")
        print(f"  redis-cli DEL {key}")
        print()
        print("O desde Python puro (sin el proyecto):")
        print(f"  import redis; r = redis.Redis(...); r.delete('{key}')")


def print_bulk_instructions() -> None:
    """Imprime instrucciones para invalidar todos los perfiles de talla."""
    print("Para invalidar TODOS los perfiles de talla en Redis:\n")
    print("  Opción A — redis-cli (más rápido):")
    print("    redis-cli KEYS 'mcp:size:profile:*' | xargs redis-cli DEL")
    print()
    print("  Opción B — Python con redis-py:")
    print("    import redis")
    print("    r = redis.Redis(host='...', port=..., password='...')")
    print("    keys = r.keys('mcp:size:profile:*')")
    print("    if keys: r.delete(*keys)")
    print(f"    print(f'Eliminadas {{len(keys)}} claves')")
    print()
    print("  Opción C — desde el REPL del servidor en Cloud Run:")
    print("    Conectarse a la instancia y ejecutar:")
    print("    from src.api.factories.service_factory import ServiceFactory")
    print("    import asyncio")
    print("    async def run():")
    print("        sps = await ServiceFactory.get_size_profile_service()")
    print("        # invalidar clientes específicos uno a uno:")
    print("        for cid in ['8831066177845', '10383403057461']:")
    print("            await sps.invalidate(cid)")
    print("    asyncio.run(run())")
    print()
    print("NOTA: Los perfiles con schema viejo (sin confidence_by_category)")
    print("      producirán has_data()=False hasta que sean invalidados y")
    print("      recalculados. El TTL natural es 24h.")


def main():
    parser = argparse.ArgumentParser(
        description="Invalida el cache Redis de SizeProfile para forzar recálculo."
    )
    parser.add_argument(
        "--customer-id",
        help="ID numérico del cliente Shopify (ej. 8831066177845)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Mostrar instrucciones para invalidar todos los perfiles",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar qué se haría sin ejecutar",
    )

    args = parser.parse_args()

    if args.all:
        print_bulk_instructions()
        return

    if not args.customer_id:
        parser.print_help()
        print()
        print("Ejemplo:")
        print("  python scripts/invalidate_size_profile_cache.py --customer-id 8831066177845")
        return

    asyncio.run(invalidate_one(args.customer_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
