"""
Tests para f08b2_category_resolution.resolve_f08b2_complement_types
======================================================================

Cubre, con los casos REALES reproducidos en produccion (20-21/09/2026), los
dos bugs corregidos esa semana y confirma que el comportamiento amplio
("accesorios"/"vestidos") sigue igual tras la decision de unificacion de
taxonomia del 26/09/2026 (retiro de _B08B2_SHOPIFY_TO_OUTFIT_CAT y
_OUTFIT_COMPLEMENT_MAP en favor de product_taxonomy.py).

Sirve como red de seguridad para esa refactorizacion -- ver docstring de
src/recommenders/f08b2_category_resolution.py para el contexto completo.

Ejecutar:
    pytest tests/unit/test_f08b2_category_resolution.py -v
"""
import pytest

from src.recommenders.f08b2_category_resolution import resolve_f08b2_complement_types


# ════════════════════════════════════════════════════════════════════
# STUBS de las dependencias inyectadas
# ════════════════════════════════════════════════════════════════════
#
# Replican, para las frases exactas usadas en estos tests, el comportamiento
# real de extract_categories_from_query() / get_concrete_categories() /
# product_taxonomy.get_outfit_slot() / types_in_outfit_slot() -- confirmado
# contra los logs de produccion del 20-24/09/2026 y el catalogo real via
# taxonomy_centroid_audit.py (26/09/2026), no inventado.

_AVAILABLE_CATEGORIES = {
    "ZAPATOS", "VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS",
    "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS",
    "AROS", "COLLARES", "BRAZALETES", "CLUTCH", "CINTURONES",
    "CARTERAS", "TOCADOS",
}

_SLOT_TYPES = {
    "accessory": ["AROS", "COLLARES", "BRAZALETES", "BRAZALETE",
                  "CINTURONES", "TOCADOS", "ALAS DE NOVIA"],
    "bag": ["CARTERAS", "CLUTCH"],
    "dress": ["VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS",
              "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS"],
    "shoes": ["ZAPATOS"],
}

_TYPE_TO_SLOT = {t: slot for slot, types in _SLOT_TYPES.items() for t in types}

# Todo accessory+bag junto (usado en varias aserciones de "sin categoria
# explicita" -- el nuevo fallback, reemplazo de _OUTFIT_COMPLEMENT_MAP).
_ALL_ACCESSORY_AND_BAG = set(_SLOT_TYPES["accessory"]) | set(_SLOT_TYPES["bag"])


def stub_extract_categories(query: str, available):
    """
    Replica el comportamiento real observado en logs para las frases
    exactas usadas en estos tests -- incluyendo la deteccion de auto-
    referencia via substring (asi es como extract_categories_from_query
    detecto 'AROS' en "esto aros" y 'COLLARES' NO en "este collar", per
    logs reales del 20-21/09/2026).
    """
    q = query.lower()
    detected = []
    if "accesorio" in q:
        detected += ["AROS", "COLLARES", "BRAZALETES", "CLUTCH",
                     "CINTURONES", "CARTERAS", "TOCADOS"]
    if "zapato" in q:
        detected.append("ZAPATOS")
    if "vestidos" in q:  # plural -- "vestido" singular (referencia al ancla) no dispara
        detected += ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"]
    if "aros" in q:
        detected.append("AROS")
    if "arete" in q:
        detected.append("AROS")
    seen, out = set(), []
    for c in detected:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return [c for c in out if c in available]


def stub_get_concrete_categories():
    return set(_AVAILABLE_CATEGORIES)


def stub_get_outfit_slot(t: str):
    return _TYPE_TO_SLOT.get(t.upper())


def stub_types_in_outfit_slot(slot: str):
    return list(_SLOT_TYPES.get(slot, []))


def resolve(query: str, anchor_type: str):
    """Helper para no repetir las 4 dependencias inyectadas en cada test."""
    return resolve_f08b2_complement_types(
        conversation_query=query,
        outfit_product_type=anchor_type,
        extract_categories_fn=stub_extract_categories,
        get_concrete_categories_fn=stub_get_concrete_categories,
        get_outfit_slot_fn=stub_get_outfit_slot,
        types_in_outfit_slot_fn=stub_types_in_outfit_slot,
    )


# ════════════════════════════════════════════════════════════════════
# Bug 1 (20/09/2026): auto-referencia al propio tipo del ancla
# ════════════════════════════════════════════════════════════════════

class TestAutoReferencia:
    """
    Antes del fix: mencionar el propio tipo del ancla en la consulta se
    trataba como un pedido nuevo, mezclando accesorios no pedidos.
    """

    def test_vestidos_mas_auto_referencia_a_aros_da_solo_vestidos(self):
        """
        Caso real (20/09/2026): "Con que vestidos combina mejor esto aros?",
        ancla AROS. Antes: mezclaba COLLARES/BRAZALETES. Ahora: solo vestidos.
        """
        result = resolve("Con que vestidos combina mejor esto aros?", "AROS")
        assert set(result) == {
            "VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS",
            "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS",
        }
        assert "COLLARES" not in result
        assert "BRAZALETES" not in result
        assert "AROS" not in result

    def test_aretes_mas_auto_referencia_a_collar_da_solo_aros(self):
        """
        Caso real (20/09/2026): "Que aretes puedo combinar este collar?",
        ancla COLLARES. Antes: mezclaba BRAZALETES/CINTURONES/etc. Ahora:
        solo AROS (la especificidad del pedido, ver Bug 2 mas abajo).
        """
        result = resolve("Que aretes puedo combinar este collar?", "COLLARES")
        assert result == ["AROS"]


# ════════════════════════════════════════════════════════════════════
# Bug 2 (20/09/2026): sobre-expansion de categoria especifica y unica
# ════════════════════════════════════════════════════════════════════

class TestEspecificidadNoSeExpande:
    """
    Antes del fix: un pedido especifico y unico (ej. "aretes") se mapeaba
    a su bucket completo (accessory), devolviendo collares/brazaletes/etc.
    ademas de aros.
    """

    def test_aretes_especifico_da_solo_aros_no_todo_el_bucket(self):
        """Caso real (20/09/2026): "Con que aretes puedo combinar esto?", ancla BRAZALETES."""
        result = resolve("Con que aretes puedo combinar esto?", "BRAZALETES")
        assert result == ["AROS"]

    def test_zapatos_especifico_da_solo_zapatos(self):
        """Caso real (20/09/2026): "Que zapatos combinan con este vestido?", ancla NOVIAS LARGOS."""
        result = resolve("Que zapatos combinan con este vestido?", "NOVIAS LARGOS")
        assert result == ["ZAPATOS"]


# ════════════════════════════════════════════════════════════════════
# Comportamiento amplio preservado: pedidos amplios SI expanden
# ════════════════════════════════════════════════════════════════════

class TestPedidoAmplioSiExpande:
    """
    Un pedido amplio (la deteccion YA devuelve multiples tipos, senal de
    que el usuario no fue especifico) debe seguir expandiendo por bucket,
    igual que antes de la unificacion -- ahora via product_taxonomy.py en
    vez de la copia local retirada, sin cambio de resultado.
    """

    def test_accesorios_amplio_expande_a_todo_el_bucket_accessory_y_bag(self):
        """Caso real (20/09/2026): "Que accesorios combinan con este vestido?", ancla NOVIAS LARGOS."""
        result = resolve("Que accesorios combinan con este vestido?", "NOVIAS LARGOS")
        assert set(result) == {
            "AROS", "COLLARES", "BRAZALETES", "BRAZALETE",
            "CINTURONES", "TOCADOS", "ALAS DE NOVIA", "CARTERAS", "CLUTCH",
        }

    def test_vestidos_amplio_expande_a_todo_el_bucket_dress(self):
        """Caso real (20/09/2026): "Con que vestidos combina mejor?", ancla AROS."""
        result = resolve("Con que vestidos combina mejor?", "AROS")
        assert set(result) == {
            "VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS",
            "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS",
        }


# ════════════════════════════════════════════════════════════════════
# Caso historico: el bug original que motivo Fix 2 (Fase 1b, 28/07/2026)
# ════════════════════════════════════════════════════════════════════

class TestCasoHistoricoT8:
    """
    El caso que origino el "Fix 2" documentado en
    DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md, seccion 12.4:
    ancla AROS (accesorio) pidiendo una prenda -- direccion que el retirado
    _OUTFIT_COMPLEMENT_MAP nunca contemplo (solo tenia entradas de prenda).
    """

    def test_t8_ancla_aros_pidiendo_vestidos_ya_no_cae_al_mapa_de_accesorios(self):
        result = resolve("con que vestidos combina mejor?", "AROS")
        assert any("VESTIDOS" in t or "NOVIAS" in t for t in result)
        assert "COLLARES" not in result


# ════════════════════════════════════════════════════════════════════
# Sin categoria explicita: nuevo fallback (26/09/2026) -- reemplazo de
# _OUTFIT_COMPLEMENT_MAP (retirado en la decision de unificacion)
# ════════════════════════════════════════════════════════════════════

class TestSinCategoriaExplicita:
    """
    Cuando la consulta no tiene ninguna categoria explicita detectable, el
    fallback -- desde la decision de unificacion de taxonomia (26/09/2026)
    -- es TODO el bucket accessory+bag, menos el propio tipo del ancla.
    Reemplaza al retirado _OUTFIT_COMPLEMENT_MAP, que tenia 19 de 29 tipos
    de prenda ya cayendo a su fallback generico de solo 4 items de todas
    formas -- esto amplia esa cobertura a los 9 tipos reales del bucket,
    usando el mismo mecanismo ya validado para pedidos como "accesorios".
    """

    def test_ancla_tipo_prenda_devuelve_todo_accessory_mas_bag(self):
        result = resolve("que combina con esto?", "VESTIDOS LARGOS")
        assert set(result) == _ALL_ACCESSORY_AND_BAG

    def test_ancla_tipo_accesorio_excluye_su_propio_tipo(self):
        """
        Antes (mapa retirado): AROS no tenia entrada -> fallback generico de
        4 items ["AROS","COLLARES","CLUTCH","CINTURONES"] (incluyendo,
        incorrectamente, al propio AROS antes del filtro final). Ahora:
        todo el bucket, correctamente sin el propio tipo.
        """
        result = resolve("que combina con esto?", "AROS")
        assert "AROS" not in result
        assert set(result) == _ALL_ACCESSORY_AND_BAG - {"AROS"}

    def test_ancla_tipo_bolso_excluye_su_propio_tipo(self):
        result = resolve("que combina con esto?", "CARTERAS")
        assert "CARTERAS" not in result
        assert set(result) == _ALL_ACCESSORY_AND_BAG - {"CARTERAS"}


# ════════════════════════════════════════════════════════════════════
# Casos limite / adversariales
# ════════════════════════════════════════════════════════════════════

class TestCasosLimite:

    def test_deteccion_vacia_no_rompe_cae_al_fallback_amplio(self):
        """Si extract_categories_fn no encuentra nada, cae al fallback amplio."""
        def empty_extract(query, available):
            return []
        result = resolve_f08b2_complement_types(
            "asdkjhaskjdh", "VESTIDOS LARGOS",
            empty_extract, stub_get_concrete_categories,
            stub_get_outfit_slot, stub_types_in_outfit_slot,
        )
        assert set(result) == _ALL_ACCESSORY_AND_BAG

    def test_deteccion_solo_auto_referencia_queda_vacia_cae_al_fallback_amplio(self):
        """
        Si lo unico detectado es el propio tipo del ancla (auto-referencia
        pura, sin ningun pedido real), debe caer al fallback amplio -- no a
        una lista vacia silenciosa.
        """
        def only_self_extract(query, available):
            return ["AROS"]
        result = resolve_f08b2_complement_types(
            "esto aros", "AROS",
            only_self_extract, stub_get_concrete_categories,
            stub_get_outfit_slot, stub_types_in_outfit_slot,
        )
        assert "AROS" not in result
        assert set(result) == _ALL_ACCESSORY_AND_BAG - {"AROS"}

    def test_anchor_type_en_minuscula_se_normaliza(self):
        """El tipo del ancla puede llegar en minuscula -- debe normalizarse."""
        result_lower = resolve("Con que aretes puedo combinar esto?", "brazaletes")
        result_upper = resolve("Con que aretes puedo combinar esto?", "BRAZALETES")
        assert result_lower == result_upper == ["AROS"]

    def test_nunca_incluye_el_propio_tipo_del_ancla(self):
        """Invariante general: el resultado nunca debe incluir el tipo del ancla."""
        casos = [
            ("Que accesorios combinan con esto?", "AROS"),
            ("Con que vestidos combina mejor?", "VESTIDOS LARGOS"),
            ("que combina con esto?", "CARTERAS"),
        ]
        for query, anchor in casos:
            result = resolve(query, anchor)
            assert anchor.upper() not in result

    def test_ancla_sin_bucket_conocido_aun_asi_cae_al_fallback_amplio(self):
        """
        Un tipo de ancla que get_outfit_slot_fn no reconoce (ej. un tipo
        nuevo sin taxonomia asignada todavia) no debe romper -- el fallback
        amplio no depende de conocer el bucket del ancla, solo lo usa para
        decidir si excluirlo de accessory/bag (no aplica si no es ninguno).
        """
        result = resolve("que combina con esto?", "TURBANTES")
        assert set(result) == _ALL_ACCESSORY_AND_BAG
