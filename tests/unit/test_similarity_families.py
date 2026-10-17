"""
Tests de SIMILARITY_FAMILIES -- "que cuenta como MAS DE ESTO".

Gap G2, decidido con Yasmani el 07/10/2026 a partir de evidencia de
produccion: pidiendo "similares" sobre un clutch, el CLUTCH LEONOR aparecio
en 4a posicion por debajo de dos pares de aros, porque CARTERAS y CLUTCH son
product_type distintos en el catalogo.

Ejecutar:
    pytest tests/unit/test_similarity_families.py -v
"""
import pytest

from src.recommenders.product_taxonomy import (
    ALTERNATIVE_FAMILIES,
    PRODUCT_TAXONOMY,
    SIMILARITY_FAMILIES,
    get_alternative_types,
    get_outfit_slot,
    get_similarity_family,
    is_bridal_type,
    similarity_family_name,
)


# ════════════════════════════════════════════════════════════════════
# El caso que motivo el cambio
# ════════════════════════════════════════════════════════════════════

class TestCasoBolsos:

    def test_carteras_y_clutch_son_la_misma_familia(self):
        """Screenshot del 07/10/2026: el CLUTCH LEONOR debio ir en 2a posicion."""
        assert set(get_similarity_family("CARTERAS")) == {"CARTERAS", "CLUTCH"}
        assert set(get_similarity_family("CLUTCH")) == {"CARTERAS", "CLUTCH"}

    def test_la_familia_es_simetrica(self):
        """Da igual cual de los dos sea el ancla."""
        assert set(get_similarity_family("CARTERAS")) == set(get_similarity_family("CLUTCH"))

    def test_los_aros_NO_entran_en_bolsos(self):
        assert "AROS" not in get_similarity_family("CARTERAS")


# ════════════════════════════════════════════════════════════════════
# Decisiones de producto de Yasmani (07/10/2026)
# ════════════════════════════════════════════════════════════════════

class TestDecisionesDeProducto:
    """
    Cada test fija una decision explicita. Si alguno falla, alguien cambio
    una decision de producto -- debe ser a proposito y con el test actualizado.
    """

    @pytest.mark.parametrize("tipo", ["AROS", "COLLARES"])
    def test_joyeria_NO_es_una_sola_familia(self, tipo):
        """"Viendo unos aros, el usuario no quiere collares" (Yasmani)."""
        fam = get_similarity_family(tipo)
        assert fam == [tipo]
        assert similarity_family_name(tipo) is None

    def test_brazaletes_agrupa_singular_y_plural(self):
        """
        PROBLEMA DE DATOS: BRAZALETES y BRAZALETE son el mismo producto con
        dos product_type. Esto es una tirita -- lo correcto es unificarlos en
        Shopify.
        """
        assert set(get_similarity_family("BRAZALETE")) == {"BRAZALETES", "BRAZALETE"}

    def test_brazaletes_no_arrastra_al_resto_de_joyeria(self):
        assert "AROS" not in get_similarity_family("BRAZALETES")
        assert "COLLARES" not in get_similarity_family("BRAZALETES")

    def test_tocados_y_alas_de_novia_si_son_familia(self):
        assert set(get_similarity_family("TOCADOS")) == {"TOCADOS", "ALAS DE NOVIA"}
        assert similarity_family_name("ALAS DE NOVIA") == "TOCADOS_NUPCIALES"

    def test_tops_y_bralettes_son_cosas_distintas(self):
        assert get_similarity_family("TOPS") == ["TOPS"]
        assert get_similarity_family("BRALETTES") == ["BRALETTES"]

    def test_pantalones_y_leggings_no_son_lo_mismo(self):
        assert get_similarity_family("PANTALONES") == ["PANTALONES"]
        assert get_similarity_family("LEGGINGS") == ["LEGGINGS"]

    @pytest.mark.parametrize("tipo", ["VESTIDOS CORTOS", "VESTIDOS MIDIS", "VESTIDOS LARGOS"])
    def test_los_vestidos_van_separados_por_largo(self, tipo):
        """
        "El largo es una decision, no un matiz" (Yasmani, 07/10/2026).
        Los otros largos NO desaparecen: bajan a alternativas, porque el pool
        lo sigue decidiendo el grupo padre de CATEGORY_KEYWORDS.
        """
        assert get_similarity_family(tipo) == [tipo]

    @pytest.mark.parametrize("tipo", ["ENTERITOS CORTOS", "ENTERITOS LARGOS"])
    def test_los_enteritos_tambien_van_separados_por_largo(self, tipo):
        """
        Hasta el 10/10/2026 estaban AGRUPADOS, incoherente con los vestidos.
        Separarlos es lo que permite que la alternativa respete el largo:
        enterito largo -> vestido largo, enterito corto -> vestido corto.
        """
        assert get_similarity_family(tipo) == [tipo]

    @pytest.mark.parametrize("tipo", ["CONJUNTOS FALDAS", "CONJUNTOS PANTALONES"])
    def test_los_conjuntos_de_invitada_van_separados_por_pieza_inferior(self, tipo):
        """
        Separados el 10/10/2026: siluetas distintas, con 41 y 22 productos --
        volumen de sobra. Juntarlos obligaba a una alternativa generica que
        acabaria ofreciendo pantalones a quien mira un conjunto con falda.
        """
        assert get_similarity_family(tipo) == [tipo]

    def test_los_conjuntos_de_novia_SI_siguen_juntos(self):
        """10 productos en total: sin volumen para sostener dos familias."""
        assert set(get_similarity_family("NOVIAS CONJUNTOS FALDAS")) == {
            "NOVIAS CONJUNTOS FALDAS", "NOVIAS CONJUNTOS PANTALONES"}

    def test_novia_nunca_se_mezcla_con_invitada(self):
        for novia in ("NOVIAS CORTOS", "NOVIAS LARGOS", "NOVIAS MIDIS"):
            fam = get_similarity_family(novia)
            assert not any(t.startswith("VESTIDOS") for t in fam), f"{novia} mezcla con invitada"
        assert "NOVIAS CONJUNTOS FALDAS" not in get_similarity_family("CONJUNTOS FALDAS")

    def test_capas_conserva_su_grupo_padre(self):
        assert set(get_similarity_family("CAPAS GASA")) == {"CAPAS GASA", "CAPAS BORDADAS"}

    def test_kimonos_y_chaquetas_van_solos(self):
        """
        Ninguno tiene grupo padre en CATEGORY_KEYWORDS, y agruparlos con las
        capas seria una decision de estilismo que nadie ha tomado.
        """
        assert get_similarity_family("KIMONOS") == ["KIMONOS"]
        assert get_similarity_family("CHAQUETAS") == ["CHAQUETAS"]


# ════════════════════════════════════════════════════════════════════
# Contrato de la funcion
# ════════════════════════════════════════════════════════════════════

class TestContratoDeLaFuncion:

    def test_siempre_incluye_al_propio_tipo(self):
        for t in PRODUCT_TAXONOMY:
            assert t.upper() in get_similarity_family(t), f"{t} no se incluye a si mismo"

    def test_default_es_su_propia_familia(self):
        """Un tipo nuevo del catalogo nunca se agrupa con otros por omision."""
        assert get_similarity_family("TIPO QUE NO EXISTE") == ["TIPO QUE NO EXISTE"]

    def test_insensible_a_mayusculas(self):
        assert set(get_similarity_family("carteras")) == {"CARTERAS", "CLUTCH"}

    def test_devuelve_siempre_en_mayusculas(self):
        """El consumidor (el contrato de recomendaciones) compara en mayusculas."""
        for t in ("carteras", "Clutch", "TOCADOS"):
            fam = get_similarity_family(t)
            assert fam == [x.upper() for x in fam]

    @pytest.mark.parametrize("vacio", ["", None])
    def test_sin_tipo_devuelve_lista_vacia(self, vacio):
        """Sin ancla no hay criterio; el contrato lo lee como 'todo cuenta'."""
        assert get_similarity_family(vacio) == []
        assert similarity_family_name(vacio) is None


# ════════════════════════════════════════════════════════════════════
# Integridad del mapa contra el catalogo real
# ════════════════════════════════════════════════════════════════════

class TestIntegridadDelMapa:

    def test_todos_los_tipos_declarados_existen_en_la_taxonomia(self):
        """Un typo en el mapa crearia una familia fantasma que nunca aplica."""
        conocidos = {t.upper() for t in PRODUCT_TAXONOMY}
        for familia, miembros in SIMILARITY_FAMILIES.items():
            for m in miembros:
                assert m.upper() in conocidos, f"{familia}: '{m}' no esta en PRODUCT_TAXONOMY"

    def test_ningun_tipo_pertenece_a_dos_familias(self):
        """
        Dos familias compartiendo un tipo harian que la resolucion dependiera
        del orden del diccionario -- el mismo contrato implicito que ya nos
        mordio con ACCESSORIES/JOYAS (gap B6).
        """
        visto = {}
        for familia, miembros in SIMILARITY_FAMILIES.items():
            for m in miembros:
                k = m.upper()
                assert k not in visto, f"'{k}' esta en {visto[k]} y en {familia}"
                visto[k] = familia

    def test_ninguna_familia_tiene_un_solo_miembro(self):
        """Una familia de uno es el default: declararla solo anade ruido."""
        for familia, miembros in SIMILARITY_FAMILIES.items():
            assert len(miembros) >= 2, f"{familia} tiene un solo miembro"

    def test_ninguna_familia_cruza_novia_e_invitada(self):
        """
        Invariante de producto: novia e invitada nunca comparten familia.
        outfit_slot SI los mezcla (bucket `dress` y `conjunto`), que es
        correcto para completar un outfit pero no para "mas de esto".
        """
        for familia, miembros in SIMILARITY_FAMILIES.items():
            hay_novia = any(m.upper().startswith("NOVIAS") for m in miembros)
            hay_invitada = any(not m.upper().startswith("NOVIAS") for m in miembros)
            assert not (hay_novia and hay_invitada), f"{familia} mezcla novia e invitada"


# ════════════════════════════════════════════════════════════════════
# Relacion con outfit_slot: son taxonomias DISTINTAS
# ════════════════════════════════════════════════════════════════════

class TestNoEsOutfitSlot:
    """
    Documenta por que hizo falta un campo propio en vez de reutilizar
    outfit_slot. Si estos tests empiezan a fallar, alguien esta convergiendo
    las dos taxonomias -- y eso hay que decidirlo, no dejarlo pasar.
    """

    def test_en_bolsos_coinciden(self):
        assert set(get_similarity_family("CARTERAS")) == {"CARTERAS", "CLUTCH"}
        assert get_outfit_slot("CARTERAS") == get_outfit_slot("CLUTCH") == "bag"

    def test_en_accesorios_NO_coinciden(self):
        """`accessory` mete aros, cinturones y tocados en la misma bolsa."""
        assert get_outfit_slot("AROS") == get_outfit_slot("CINTURONES") == "accessory"
        assert "CINTURONES" not in get_similarity_family("AROS")

    def test_en_vestidos_NO_coinciden(self):
        """`dress` mezcla novia con invitada."""
        assert get_outfit_slot("VESTIDOS LARGOS") == get_outfit_slot("NOVIAS LARGOS") == "dress"
        assert "NOVIAS LARGOS" not in get_similarity_family("VESTIDOS LARGOS")


# ═════════════════════════════════════════════════════════════════
# ALTERNATIVE_FAMILIES -- "si no queda de esto, que ofrezco"
# ═════════════════════════════════════════════════════════════════

class TestDecisionesDeAlternativas:
    """
    Decisiones de estilismo de Yasmani (10/10/2026). Cada test fija una, con
    su razon. Si uno falla, alguien cambio una decision de producto y debe
    ser a proposito.
    """

    def test_joyeria_acotada_a_joyeria(self):
        """
        Antes, via grupo padre ACCESSORIES, unos aros ofrecian ademas bolsos,
        cinturones y tocados. "Quien mira unos aros no viene buscando un
        bolso" (Yasmani).
        """
        alt = get_alternative_types("AROS")
        assert set(alt) == {"COLLARES", "BRAZALETES", "BRAZALETE"}
        assert "CARTERAS" not in alt and "CINTURONES" not in alt

    def test_la_expansion_cubre_el_duplicado_de_brazaletes(self):
        """
        Declarar "BRAZALETES" debe cubrir tambien "BRAZALETE" (singular) sin
        repetirlo en el mapa: lo hace get_similarity_family().
        """
        assert "BRAZALETE" in get_alternative_types("AROS")

    def test_pantalones_ofrece_faldas_y_leggings(self):
        assert get_alternative_types("PANTALONES") == ["FALDAS", "LEGGINGS"]

    def test_conjuntos_apuntan_a_SU_pieza_inferior(self):
        """
        "Quien mira un conjunto de dos piezas puede estar considerando
        componerlo por separado" (Yasmani). Cada conjunto a su pieza, no a un
        "bottom" generico.
        """
        assert get_alternative_types("CONJUNTOS FALDAS") == ["FALDAS", "TOPS"]
        assert get_alternative_types("CONJUNTOS PANTALONES") == ["PANTALONES", "TOPS"]

    def test_enteritos_cruzan_a_vestidos_del_MISMO_largo(self):
        assert get_alternative_types("ENTERITOS LARGOS") == ["VESTIDOS LARGOS"]
        assert get_alternative_types("ENTERITOS CORTOS") == ["VESTIDOS CORTOS"]

    def test_vestidos_cruzan_a_enteritos_del_MISMO_largo(self):
        """Simetrico (Yasmani, 10/10)."""
        assert "ENTERITOS LARGOS" in get_alternative_types("VESTIDOS LARGOS")
        assert "ENTERITOS CORTOS" in get_alternative_types("VESTIDOS CORTOS")

    def test_vestidos_midis_no_cruza_a_enteritos(self):
        """Asimetria DELIBERADA: no existe un enterito midi en el catalogo."""
        assert not any(a.startswith("ENTERITOS") for a in get_alternative_types("VESTIDOS MIDIS"))

    def test_tops_y_bralettes_SI_son_alternativa_mutua(self):
        """
        Son tipos distintos para el bloque PRINCIPAL (07/10) pero si valen
        como alternativa etiquetada el uno del otro (10/10).
        """
        assert get_alternative_types("TOPS") == ["BRALETTES"]
        assert get_alternative_types("BRALETTES") == ["TOPS"]

    def test_abrigo_ligero_entre_si(self):
        assert set(get_alternative_types("KIMONOS")) == {
            "CAPAS BORDADAS", "CAPAS GASA", "CHAQUETAS"}

    @pytest.mark.parametrize("tipo", ["ZAPATOS", "CALZONES", "LENCERIA", "PIJAMAS", "REDUCTORES"])
    def test_sin_alternativas_a_proposito(self, tipo):
        """
        Ropa interior: compras con intenciones muy distintas entre si, y es la
        familia por la que se colo el defecto del 10/10 (ropa reductora SIN
        STOCK recomendada para una consulta de pantalones). Zapatos: no hay
        nada comparable. Vacio es mas seguro que acertar a medias.
        """
        assert get_alternative_types(tipo) == []


class TestInvariantesDeAlternativas:
    """Reglas transversales que ninguna entrada del mapa puede violar."""

    INTIMA = {"CALZONES", "LENCERIA", "PIJAMAS", "REDUCTORES"}

    def test_ninguna_alternativa_cruza_la_frontera_nupcial(self):
        """
        Se aplica POR CONSTRUCCION en get_alternative_types(), no confiando en
        que el mapa este bien escrito.

        Defecto real que lo motivo (10/10/2026): CARTERAS ofrecia ALAS DE
        NOVIA. No estaba declarado -- se colo por la expansion a familia,
        porque ALAS DE NOVIA comparte la familia TOCADOS_NUPCIALES con
        TOCADOS, que SI es alternativa legitima de un bolso. Y el chequeo de
        entonces no lo vio, porque buscaba el prefijo "NOVIAS" y ese tipo no
        lo lleva.
        """
        for t in PRODUCT_TAXONOMY:
            for a in get_alternative_types(t):
                assert is_bridal_type(a) == is_bridal_type(t), (
                    f"{t} (nupcial={is_bridal_type(t)}) ofrece "
                    f"{a} (nupcial={is_bridal_type(a)})")

    def test_el_caso_concreto_que_se_colo(self):
        assert "ALAS DE NOVIA" not in get_alternative_types("CARTERAS")
        assert "TOCADOS" in get_alternative_types("CARTERAS")

    def test_alas_de_novia_es_nupcial_pese_a_no_llevar_el_prefijo(self):
        """La convencion de nombres no basta: hace falta la lista explicita."""
        assert is_bridal_type("ALAS DE NOVIA")
        assert not "ALAS DE NOVIA".upper().startswith("NOVIAS")

    def test_la_ropa_interior_nunca_es_alternativa_de_nada(self):
        for t in PRODUCT_TAXONOMY:
            for a in get_alternative_types(t):
                assert a.upper() not in self.INTIMA, f"{t} ofrece {a}"

    def test_una_alternativa_nunca_es_de_la_propia_familia(self):
        """Eso seria `principal`, no alternativa."""
        for t in PRODUCT_TAXONOMY:
            propia = {m.upper() for m in get_similarity_family(t)}
            for a in get_alternative_types(t):
                assert a.upper() not in propia, f"{t}: {a} es de su propia familia"

    def test_todos_los_tipos_del_mapa_existen(self):
        conocidos = {t.upper() for t in PRODUCT_TAXONOMY}
        for clave, valores in ALTERNATIVE_FAMILIES.items():
            assert clave.upper() in conocidos, f"clave inexistente: {clave}"
            for v in valores:
                assert v.upper() in conocidos, f"{clave}: valor inexistente {v}"

    def test_sin_duplicados_en_la_salida(self):
        for t in PRODUCT_TAXONOMY:
            alt = get_alternative_types(t)
            assert len(alt) == len(set(alt)), f"{t} repite alternativas"


class TestContratoDeAlternativas:

    def test_default_es_sin_alternativas(self):
        """Un tipo nuevo del catalogo nunca arrastra sugerencias por omision."""
        assert get_alternative_types("TIPO QUE NO EXISTE") == []

    @pytest.mark.parametrize("vacio", ["", None])
    def test_sin_tipo_devuelve_lista_vacia(self, vacio):
        assert get_alternative_types(vacio) == []
        assert is_bridal_type(vacio) is False

    def test_insensible_a_mayusculas(self):
        assert get_alternative_types("pantalones") == ["FALDAS", "LEGGINGS"]

    def test_devuelve_en_mayusculas(self):
        alt = get_alternative_types("CONJUNTOS FALDAS")
        assert alt == [a.upper() for a in alt]

    def test_preserva_el_orden_declarado(self):
        """Es el orden de preferencia del estilista, no alfabetico."""
        assert get_alternative_types("CONJUNTOS FALDAS")[0] == "FALDAS"

    def test_cobertura_tras_el_mapa(self):
        """
        Antes del mapa, 17 de 36 tipos no podian tener alternativas porque su
        grupo padre coincidia con su familia. Ahora solo 6 -- y en esos seis
        el bloque vacio es la respuesta correcta.
        """
        sin = [t for t in PRODUCT_TAXONOMY if not get_alternative_types(t)]
        assert len(sin) == 6
        assert set(sin) == {"ZAPATOS", "CALZONES", "LENCERIA", "PIJAMAS",
                            "REDUCTORES", "ALAS DE NOVIA"}
