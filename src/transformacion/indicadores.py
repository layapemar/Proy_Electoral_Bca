# -*- coding: utf-8 -*-
"""Indicadores derivados: los que piden los objetivos 3.5 a 3.11.

Cada función deja escrito qué mide y, cuando hace falta, qué **no** se puede concluir de
ella. Eso no es adorno: la mitad de estos indicadores se malinterpretan con facilidad.
El número efectivo de partidos no dice que haya tantos partidos; la volatilidad no dice
que la gente cambió de opinión; y ningún indicador agregado por puesto dice nada sobre
cómo votó una persona.

**La falacia ecológica, concretamente.** Varias de estas tablas cruzan una característica
del censo de un puesto —edad, sexo— con un resultado electoral del mismo puesto. Eso
describe **puestos**, no personas. Que los puestos con censo más joven registren menos
participación no permite afirmar que los jóvenes votan menos: dentro de cada puesto votan
personas de todas las edades y no se sabe cuáles. La metodología del proyecto prohíbe ese
salto de forma explícita.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

UMBRAL_CORPORACION = 0.5  # el umbral legal es el 50 % del cuociente electoral


def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Za-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip().upper()


# ------------------------------------------------------ estabilidad de códigos

def estabilidad_de_codigos(larga: pd.DataFrame, columna_codigo: str,
                           columna_nombre: str) -> pd.DataFrame:
    """Revisa si un código apunta siempre a lo mismo a lo largo de los años.

    Se aplicó a los puestos y resultó que no: `cod_puesto` está renumerado. Antes de
    comparar partidos entre elecciones hay que hacer la misma pregunta, porque si
    `cod_partido` también se reasigna, una volatilidad calculada sobre el código mediría
    la reasignación y no el cambio político.
    """
    d = larga[larga[columna_nombre].notna()].copy()
    d["_nombre"] = d[columna_nombre].map(canon)
    g = (d.drop_duplicates([columna_codigo, "_nombre", "anio"])
         .groupby(columna_codigo)["_nombre"].nunique())
    conflictivos = sorted(g[g > 1].index)
    filas = []
    for cod in conflictivos:
        sub = d[d[columna_codigo] == cod].drop_duplicates(["anio", "_nombre"])
        for _, r in sub.sort_values("anio").iterrows():
            filas.append({"codigo": cod, "anio": r["anio"],
                          "nombre": r[columna_nombre]})
    return pd.DataFrame(filas, columns=["codigo", "anio", "nombre"])


# ------------------------------------------------------------- agregados

def agregado_por_eleccion(puesto_eleccion: pd.DataFrame) -> pd.DataFrame:
    """Totales de todo el distrito para cada elección."""
    llave = ["anio", "familia", "corporacion", "es_uninominal"]
    sumas = {
        "puestos": ("id_puesto", "nunique"), "mesas": ("mesas", "sum"),
        "potencial_electoral": ("potencial_electoral", "sum"),
        "votos_depositados": ("votos_depositados", "sum"),
        "votos_validos": ("votos_validos", "sum"),
        "votos_a_candidatos": ("votos_a_candidatos", "sum"),
        "votos_de_lista": ("votos_de_lista", "sum"),
        "votos_blanco": ("votos_blanco", "sum"),
        "votos_nulos": ("votos_nulos", "sum"),
        "votos_no_marcados": ("votos_no_marcados", "sum"),
    }
    disponibles = {k: v for k, v in sumas.items() if v[0] in puesto_eleccion.columns}
    t = puesto_eleccion.groupby(llave, as_index=False).agg(**disponibles)

    # La cobertura del censo decide si el potencial del distrito es interpretable.
    cob = (puesto_eleccion.groupby(llave, as_index=False)
           .agg(puestos_con_potencial=("potencial_electoral", "count")))
    t = t.merge(cob, on=llave, how="left")
    t["cobertura_del_censo"] = (t["puestos_con_potencial"] / t["puestos"]
                                * 100).round(1)
    t["potencial_es_del_distrito_completo"] = t["cobertura_del_censo"] >= 100

    t["participacion"] = (t["votos_depositados"] / t["potencial_electoral"]
                          * 100).round(2)
    t["abstencion"] = (100 - t["participacion"]).round(2)
    t["votos_no_validos"] = t["votos_nulos"] + t["votos_no_marcados"]
    for col, base in (("pct_validos", "votos_depositados"),
                      ("pct_blanco", "votos_depositados"),
                      ("pct_nulos", "votos_depositados"),
                      ("pct_no_marcados", "votos_depositados"),
                      ("pct_no_validos", "votos_depositados")):
        origen = "votos_" + col[4:]
        if origen in t.columns:
            t[col] = (t[origen] / t[base] * 100).round(2)
    return t.sort_values(["anio", "corporacion"]).reset_index(drop=True)


def agregado_por_territorio(puesto_eleccion: pd.DataFrame) -> pd.DataFrame:
    """Totales por territorio y elección. Un territorio sin censo completo se marca."""
    llave = ["anio", "corporacion", "cod_comuna", "territorio", "ambito"]
    t = puesto_eleccion.groupby(llave, as_index=False, dropna=False).agg(
        puestos=("id_puesto", "nunique"),
        puestos_con_potencial=("potencial_electoral", "count"),
        potencial_electoral=("potencial_electoral", "sum"),
        votos_depositados=("votos_depositados", "sum"),
        votos_validos=("votos_validos", "sum"),
        votos_blanco=("votos_blanco", "sum"),
        votos_nulos=("votos_nulos", "sum"),
        votos_no_marcados=("votos_no_marcados", "sum"))
    t["cobertura_del_censo"] = (t["puestos_con_potencial"] / t["puestos"]
                                * 100).round(1)
    t["participacion"] = (t["votos_depositados"] / t["potencial_electoral"]
                          * 100).round(2)
    t["abstencion"] = (100 - t["participacion"]).round(2)
    t["pct_blanco"] = (t["votos_blanco"] / t["votos_depositados"] * 100).round(2)
    t["pct_no_validos"] = ((t["votos_nulos"] + t["votos_no_marcados"])
                           / t["votos_depositados"] * 100).round(2)
    return t.sort_values(["anio", "corporacion", "cod_comuna"]).reset_index(drop=True)


# --------------------------------------------------------- partidos y listas

def partido_por_eleccion(larga: pd.DataFrame) -> pd.DataFrame:
    """Votos de cada partido o lista en cada elección.

    El voto de una lista es la suma del voto preferente por sus candidatos más el voto
    por la lista sin marcar candidato. Las dos cosas se reportan por separado, porque su
    proporción dice si la lista es cerrada o abierta y eso cambia cómo se reparten las
    curules.
    """
    d = larga[larga["tipo_opcion"].isin(["candidato", "lista"])].copy()
    d["votos"] = pd.to_numeric(d["votos"], errors="coerce").fillna(0)
    d["_nombre"] = d["nombre_partido"].map(canon)

    llave = ["anio", "familia", "corporacion", "cod_partido", "_nombre"]
    t = d.groupby(llave, as_index=False).agg(
        nombre_partido=("nombre_partido", "first"),
        votos=("votos", "sum"))
    pref = (d[d["tipo_opcion"] == "candidato"].groupby(llave, as_index=False)
            .agg(votos_preferentes=("votos", "sum"),
                 candidatos_con_voto=("cod_candidato", "nunique")))
    nopref = (d[d["tipo_opcion"] == "lista"].groupby(llave, as_index=False)
              .agg(votos_de_lista=("votos", "sum")))
    t = t.merge(pref, on=llave, how="left").merge(nopref, on=llave, how="left")
    for c in ("votos_preferentes", "votos_de_lista", "candidatos_con_voto"):
        t[c] = t[c].fillna(0).astype(int)

    # **Lo que se observa es la ausencia de voto preferente, no la inscripción de una
    # lista cerrada.** Son cosas distintas aunque casi siempre coincidan: una lista puede
    # ser abierta y simplemente no haber recibido ni un voto preferente en este
    # municipio. Por eso la columna se llama como lo que se midió.
    #
    # En estos datos la coincidencia se verificó: Pacto Histórico, Nuevo Liberalismo,
    # Comunes y Estamos Listas aparecen en Senado 2022 con cero filas de candidato y
    # cientos de filas de voto de lista, que es exactamente lo que produce una lista
    # cerrada de verdad.
    t["sin_voto_preferente_observado"] = ((t["votos_preferentes"] == 0)
                                          & (t["votos_de_lista"] > 0))

    tot = t.groupby(["anio", "corporacion"])["votos"].transform("sum")
    t["pct_sobre_votos_a_listas"] = (t["votos"] / tot * 100).round(3)
    return (t.drop(columns=["_nombre"])
            .sort_values(["anio", "corporacion", "votos"], ascending=[True, True, False])
            .reset_index(drop=True))


def concentracion_por_eleccion(partido: pd.DataFrame) -> pd.DataFrame:
    """Fragmentación y concentración de cada elección.

    **HHI** es la suma de los cuadrados de las proporciones: va de casi 0 (muchas listas
    pequeñas) a 1 (una sola lista se lleva todo).

    **Número efectivo de partidos** (Laakso-Taagepera) es 1 / HHI. Si cinco listas se
    reparten el voto en partes iguales da 5; si una tiene el 90 % y otras cuatro el 2,5 %
    cada una, da 1,2. **No es el número de listas inscritas**: es cuántas pesan de verdad.
    Un valor de 16 con 25 listas significa que el voto está muy repartido.
    """
    filas = []
    for (anio, corp), g in partido.groupby(["anio", "corporacion"]):
        p = g["votos"] / g["votos"].sum()
        hhi = float((p ** 2).sum())
        filas.append({
            "anio": anio, "corporacion": corp,
            "listas_con_votos": int(len(g)),
            "listas_sin_voto_preferente": int(
                g["sin_voto_preferente_observado"].sum())
            if "sin_voto_preferente_observado" in g.columns else 0,
            "votos_a_listas": int(g["votos"].sum()),
            "hhi": round(hhi, 4),
            "numero_efectivo_de_partidos": round(1 / hhi, 2) if hhi else None,
            "pct_de_la_lista_mayor": round(p.max() * 100, 2),
            "pct_de_las_tres_mayores": round(p.nlargest(3).sum() * 100, 2),
        })
    return pd.DataFrame(filas).sort_values(["anio", "corporacion"]).reset_index(drop=True)


def volatilidad(partido: pd.DataFrame) -> pd.DataFrame:
    """Índice de Pedersen entre elecciones consecutivas de la misma corporación.

    Suma de los cambios absolutos en la proporción de cada lista, dividida por dos. Va de
    0 (ninguna lista cambió) a 100 (ninguna lista de una elección obtuvo voto en la otra).

    **Se empareja por nombre, no por código.** `cod_partido` no es estable entre años por
    la misma razón que `cod_puesto`, y una volatilidad calculada sobre códigos mediría la
    reasignación de códigos. Con nombres el riesgo es el contrario —un partido que se
    renombra aparece como nuevo— y por eso la tabla reporta cuántas listas entraron y
    salieron: si esos números son grandes, el índice se está apoyando en cambios de
    nombre y hay que mirarlo con cuidado.
    """
    d = partido.copy()
    d["_n"] = d["nombre_partido"].map(canon)
    filas = []
    for corp, g in d.groupby("corporacion"):
        anios = sorted(set(g["anio"]))
        for a, b in zip(anios, anios[1:]):
            ga = g[g["anio"] == a].groupby("_n", as_index=False)["votos"].sum()
            gb = g[g["anio"] == b].groupby("_n", as_index=False)["votos"].sum()
            ga["p"] = ga["votos"] / ga["votos"].sum() * 100
            gb["p"] = gb["votos"] / gb["votos"].sum() * 100
            j = ga.merge(gb, on="_n", how="outer", suffixes=("_a", "_b"))
            j["p_a"] = j["p_a"].fillna(0)
            j["p_b"] = j["p_b"].fillna(0)
            en_ambas = int(((j["p_a"] > 0) & (j["p_b"] > 0)).sum())
            # Cuánto del voto de cada año está en listas que existen en el otro año. Si
            # es bajo, el índice está midiendo renombres y no cambio de preferencias.
            continuidad = float(
                (j.loc[(j["p_a"] > 0) & (j["p_b"] > 0), ["p_a", "p_b"]].sum().sum())
                / 2) if en_ambas else 0.0
            if en_ambas == 0:
                lectura = ("NO INTERPRETABLE: ninguna lista aparece en las dos "
                           "elecciones, el indice solo refleja el cambio de nombres")
            elif continuidad < 50:
                lectura = ("CON CAUTELA: menos de la mitad del voto esta en listas "
                           "presentes en los dos anios")
            else:
                lectura = "interpretable"
            filas.append({
                "corporacion": corp, "de": a, "a": b,
                "volatilidad_pedersen": round(
                    float((j["p_a"] - j["p_b"]).abs().sum() / 2), 2),
                "listas_en_ambas": en_ambas,
                "listas_que_salieron": int(((j["p_a"] > 0) & (j["p_b"] == 0)).sum()),
                "listas_que_entraron": int(((j["p_a"] == 0) & (j["p_b"] > 0)).sum()),
                "pct_del_voto_en_listas_continuas": round(continuidad, 1),
                "lectura": lectura,
            })
    return pd.DataFrame(filas)


def oferta_electoral(larga: pd.DataFrame) -> pd.DataFrame:
    """Cuántas listas y cuántos candidatos compitieron en cada elección.

    Solo cuenta candidaturas, nunca filas de voto de lista: en esas, la columna
    `candidato` trae el nombre del partido, y contarlas inflaría la oferta.

    Es oferta **con votos**, no oferta inscrita. Un candidato inscrito que no obtuvo ni
    un voto no aparece en los resultados por mesa, así que este conteo es un piso. La
    cifra exacta de inscritos exige el archivo de candidaturas, que aún no se consigue.
    """
    d = larga[larga["tipo_opcion"] == "candidato"].copy()
    d["votos"] = pd.to_numeric(d["votos"], errors="coerce").fillna(0)
    llave = ["anio", "familia", "corporacion", "es_uninominal"]

    # Una candidatura es el par (lista, número de orden). `cod_candidato` por sí solo es
    # el orden dentro de la lista y se repite entre listas: contarlo solo devolvía 17
    # candidatos al Concejo, que es el tamaño de la lista más larga, no la oferta.
    d["_cand"] = (d["cod_partido"].astype(str) + "|" + d["cod_candidato"].astype(str))

    t = d.groupby(llave, as_index=False).agg(
        candidatos_con_al_menos_un_voto=("_cand", "nunique"),
        listas_con_candidatos=("cod_partido", "nunique"))

    por_lista = (d[d["votos"] > 0].drop_duplicates(llave + ["cod_partido", "cod_candidato"])
                 .groupby(llave + ["cod_partido"], as_index=False)
                 .agg(n=("_cand", "nunique")))
    res = (por_lista.groupby(llave, as_index=False)
           .agg(candidatos_por_lista_mediana=("n", "median"),
                candidatos_por_lista_maximo=("n", "max")))
    t = t.merge(res, on=llave, how="left")
    t["nota"] = "oferta con votos; es un piso, no la oferta inscrita"
    return t.sort_values(["anio", "corporacion"]).reset_index(drop=True)


def candidato_por_eleccion(larga: pd.DataFrame,
                           minimo_votos: int = 1) -> pd.DataFrame:
    """Votos de cada candidatura en cada elección.

    Nombrar candidatos es correcto: se presentaron a una elección pública y sus
    resultados son públicos. Lo que nunca entra aquí es un documento de identidad, y la
    ingesta ya los había excluido.
    """
    d = larga[larga["tipo_opcion"] == "candidato"].copy()
    d["votos"] = pd.to_numeric(d["votos"], errors="coerce").fillna(0)
    llave = ["anio", "familia", "corporacion", "cod_partido", "nombre_partido",
             "cod_candidato", "nombre_candidato"]
    t = d.groupby(llave, as_index=False, dropna=False).agg(
        votos=("votos", "sum"),
        puestos_con_voto=("id_puesto", "nunique"))
    t = t[t["votos"] >= minimo_votos]
    tot = t.groupby(["anio", "corporacion"])["votos"].transform("sum")
    t["pct_sobre_votos_a_candidatos"] = (t["votos"] / tot * 100).round(3)
    t["orden_en_la_eleccion"] = (t.groupby(["anio", "corporacion"])["votos"]
                                 .rank(ascending=False, method="min").astype(int))
    return t.sort_values(["anio", "corporacion", "votos"],
                         ascending=[True, True, False]).reset_index(drop=True)


def concentracion_territorial(larga: pd.DataFrame,
                              minimo_votos: int = 200) -> pd.DataFrame:
    """Qué tan concentrado territorialmente está el voto de cada candidatura.

    Dos medidas sobre la distribución de los votos de una candidatura entre los puestos:
    el HHI territorial y el porcentaje que obtuvo en sus tres mejores puestos.

    **Una concentración alta no es una irregularidad.** Un candidato puede tener su base
    en un barrio, haber hecho campaña en una zona o vivir ahí. El indicador describe una
    distribución y nada más.
    """
    d = larga[(larga["tipo_opcion"] == "candidato")].copy()
    d["votos"] = pd.to_numeric(d["votos"], errors="coerce").fillna(0)
    llave = ["anio", "corporacion", "cod_partido", "nombre_partido",
             "cod_candidato", "nombre_candidato"]
    por_puesto = d.groupby(llave + ["id_puesto"], as_index=False, dropna=False)[
        "votos"].sum()

    filas = []
    for clave, g in por_puesto.groupby(llave, dropna=False):
        total = g["votos"].sum()
        if total < minimo_votos:
            continue
        p = g["votos"] / total
        filas.append(dict(zip(llave, clave), **{
            "votos": int(total),
            "puestos_con_voto": int((g["votos"] > 0).sum()),
            "hhi_territorial": round(float((p ** 2).sum()), 4),
            "pct_en_sus_3_mejores_puestos": round(float(p.nlargest(3).sum() * 100), 2),
        }))
    t = pd.DataFrame(filas)
    if len(t):
        t["nota"] = "describe una distribucion; no es indicio de irregularidad"
    return t.sort_values(["anio", "corporacion", "hhi_territorial"],
                         ascending=[True, True, False]).reset_index(drop=True) \
        if len(t) else t


# -------------------------------------------------- matriz para agrupamiento

def apoyo_de_partido_por_puesto(larga: pd.DataFrame, anio: str,
                                corporacion: str) -> pd.DataFrame:
    """Proporción de voto de cada lista en cada puesto, en formato ancho.

    Es la entrada natural de PCA, K-Means o Moran: una fila por puesto y una columna por
    lista, con proporciones que suman 100 en cada fila. Se usan **proporciones y no votos
    absolutos** porque si no, el agrupamiento separaría los puestos por tamaño en lugar
    de por preferencia, que es lo que interesa.
    """
    d = larga[(larga["anio"] == str(anio))
              & (larga["corporacion"] == corporacion)
              & (larga["tipo_opcion"].isin(["candidato", "lista"]))].copy()
    d["votos"] = pd.to_numeric(d["votos"], errors="coerce").fillna(0)
    d["_n"] = d["nombre_partido"].map(canon)
    # Las columnas del índice no pueden llevar nulos: `pivot_table` descartaría esas
    # filas y los puestos sin comuna —los seis rurales de Congreso 2022— saldrían del
    # análisis sin aviso. Se etiquetan, que no es lo mismo que imputarlos.
    for c in ("cod_comuna", "territorio", "ambito"):
        if c in d.columns:
            d[c] = d[c].fillna("(sin dato)")

    piv = d.pivot_table(index=["id_puesto", "puesto", "cod_comuna", "territorio",
                               "ambito"],
                        columns="_n", values="votos", aggfunc="sum", fill_value=0)
    total = piv.sum(axis=1)
    piv = piv.div(total.where(total > 0), axis=0) * 100
    piv["votos_a_listas"] = total
    return piv.round(3).reset_index()


def matriz_por_puesto(puesto_eleccion: pd.DataFrame, anio: str,
                      corporacion: str) -> pd.DataFrame:
    """Variables por puesto para una elección, listas para agrupar o mapear.

    Solo variables **comparables entre puestos**: proporciones y tasas, no totales. Un
    puesto con 4 000 electores y otro con 150 no se pueden comparar por número de votos,
    pero sí por su composición.

    Los puestos marcados se dejan en la tabla con su marca a la vista. Quien agrupe decide
    si excluye la cárcel —cuyo censo es 96 % de hombres y no se parece a ningún otro
    puesto— pero esa decisión queda en el análisis y se escribe, no escondida aquí.
    """
    columnas = ["id_puesto", "puesto", "cod_zona", "cod_comuna", "territorio",
                "ambito", "participacion", "abstencion", "pct_validos",
                "pct_blanco", "pct_nulos", "pct_no_marcados", "pct_no_validos",
                "pct_blanco_sobre_validos", "pct_censo_18_a_30",
                "pct_censo_mas_de_60", "pct_censo_mujeres", "potencial_electoral",
                "votos_depositados", "candidatos_con_voto", "listas_con_voto",
                "lon", "lat", "densidad_votos_km2", "marcas_activas",
                "marca_ambito_especial", "marca_sin_potencial",
                "marca_participacion_imposible"]
    d = puesto_eleccion[(puesto_eleccion["anio"] == str(anio))
                        & (puesto_eleccion["corporacion"] == corporacion)].copy()
    return d[[c for c in columnas if c in d.columns]].reset_index(drop=True)


def panel_de_participacion(puesto_eleccion: pd.DataFrame,
                           panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Participación del mismo puesto a lo largo de los años, en formato ancho.

    Responde la pregunta 2 de los objetivos: ¿hay puestos con participación
    persistentemente alta o baja? Solo incluye puestos con identidad de panel, es decir
    los que se pudo verificar que son el mismo lugar. Un puesto que aparece en un solo
    año no puede decir nada sobre persistencia.
    """
    # La tabla puede traer ya la identidad de panel. Volver a unirla crearía
    # `en_panel_x` y `en_panel_y` y el filtro siguiente fallaría, así que solo se une
    # cuando falta.
    d = puesto_eleccion.copy()
    if "en_panel" not in d.columns or "id_panel" not in d.columns:
        if panel is None:
            raise ValueError(
                "La tabla no trae la identidad de panel y no se pasó la tabla `panel`.")
        ident = panel[["anio", "id_puesto", "id_panel", "en_panel",
                       "en_panel_completo", "anios_presentes"]].drop_duplicates(
            ["anio", "id_puesto"])
        d = d.merge(ident, on=["anio", "id_puesto"], how="left")
    d = d[d["en_panel"].fillna(False) == True]  # noqa: E712

    piv = d.pivot_table(index=["id_panel", "territorio", "ambito"],
                        columns=["corporacion", "anio"], values="participacion",
                        aggfunc="mean")
    piv.columns = ["%s_%s" % (a, b) for a, b in piv.columns]
    etiqueta = (d.sort_values("anio").groupby("id_panel")["puesto"]
                .last().rename("puesto_nombre_mas_reciente"))
    return piv.round(2).join(etiqueta).reset_index()
