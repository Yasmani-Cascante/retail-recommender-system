"""
check_retail_test_events.py -- DIAGNOSTICO DE SOLO LECTURA (19/10/2026).
Versionado en tools/validation/ el 30/10/2026 (ver README.md de esa carpeta).

QUE COMPRUEBA
-------------
Si el catalogo de Google Retail API contiene los eventos FALSOS que enviaba
tests/unit/test_currency_validation.py cada vez que se ejecutaba la suite de
pytest (hallazgo H-9 de SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md): eventos
purchase-complete de los visitantes test_currency_0 ... test_currency_4.

COMO LO HACE SIN BORRAR NADA
----------------------------
Retail API no tiene un metodo para listar eventos de usuario. La documentacion
oficial de userEvents.purge indica que, con force=false, el metodo devuelve el
numero de eventos que se borrarian SIN borrar ninguno:
  https://docs.cloud.google.com/retail/docs/reference/rest/v2/projects.locations.catalogs.userEvents/purge
Es un metodo DESTRUCTIVO usado en modo simulacion. Por eso este script:
  1. Fija force=False en una constante, y no acepta argumentos que la cambien.
  2. Comprueba con assert, justo antes de CADA llamada, que la peticion lleva
     force=False. Si alguien edita la constante, el script se detiene.
  3. Filtra por un visitorId concreto cada vez. Nunca usa filtros de tiempo o
     de tipo de evento, que podrian incluir eventos REALES de clientes.

APUNTA AL MISMO CATALOGO QUE EL SCRIPT ORIGINAL
-----------------------------------------------
Construye el catalogo igual que test_currency_validation.py y retail_api.py:
  projects/{GOOGLE_PROJECT_NUMBER}/locations/{GOOGLE_LOCATION|global}/catalogs/{GOOGLE_CATALOG|default_catalog}
Lee esos tres valores del .env con dotenv_values(), que NO modifica os.environ,
y no lee ni imprime ninguna otra variable del fichero.

USO (desde la raiz del repo, con el venv activado)
--------------------------------------------------
    python tools\\validation\\check_retail_test_events.py
Usa las mismas credenciales de Google que usaba el script original.
"""
import sys
from pathlib import Path

from dotenv import dotenv_values
from google.cloud import retail_v2

# --- Salvaguarda principal -------------------------------------------------
# NUNCA cambiar a True: con True, el mismo metodo BORRA los eventos.
FORCE = False

VISITANTES = [f"test_currency_{i}" for i in range(5)]  # los que usaba el script
TIMEOUT_S = 300  # espera maxima por visitante para la operacion de larga duracion


def catalogo_desde_env() -> str:
    """Construye la ruta del catalogo exactamente como el script original."""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        sys.exit(f"ERROR: no encuentro {env_path}. Ejecuta el script desde la raiz del repo.")
    valores = dotenv_values(env_path)  # solo lee; no toca os.environ
    proyecto = valores.get("GOOGLE_PROJECT_NUMBER")
    if not proyecto:
        sys.exit("ERROR: GOOGLE_PROJECT_NUMBER no esta en .env; el script original no podia enviar eventos.")
    ubicacion = valores.get("GOOGLE_LOCATION") or "global"
    catalogo = valores.get("GOOGLE_CATALOG") or "default_catalog"
    return f"projects/{proyecto}/locations/{ubicacion}/catalogs/{catalogo}"


def main() -> int:
    # Primera salvaguarda: negarse a arrancar si la constante fue alterada,
    # ANTES de imprimir nada (evita una cabecera "SIMULACION" engañosa).
    if FORCE is not False:
        sys.exit("ABORTADO: FORCE debe ser False. Este script es solo de lectura.")
    parent = catalogo_desde_env()
    print(f"Catalogo consultado: {parent}")
    print(f"Modo: SIMULACION (force={FORCE}) -- no se borra ningun evento\n")

    client = retail_v2.UserEventServiceClient()  # credenciales por defecto de Google (las mismas del script original)
    total = 0
    for visitante in VISITANTES:
        request = retail_v2.PurgeUserEventsRequest(
            parent=parent,
            filter=f'visitorId = "{visitante}"',
            force=FORCE,
        )
        # Salvaguarda por llamada: si force no es False, no se envia nada.
        assert request.force is False, "ABORTADO: la peticion no esta en modo simulacion"

        operacion = client.purge_user_events(request=request)
        try:
            respuesta = operacion.result(timeout=TIMEOUT_S)
        except Exception as exc:  # timeout u otro error: informar y seguir con el siguiente
            print(f"  {visitante}: sin resultado ({type(exc).__name__}: {exc}). Operacion: {operacion.operation.name}")
            continue
        n = respuesta.purged_events_count
        total += n
        print(f"  {visitante}: {n} evento(s)")

    print(f"\nTOTAL de eventos falsos en el catalogo: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
