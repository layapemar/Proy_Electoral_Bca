# -*- coding: utf-8 -*-
"""Participación y abstención: el cruce entre los votos y el censo electoral.

**La idea es simple y la ejecución no.** Participación es votos sobre potencial. El
problema está en que los dos números vienen de archivos distintos de la misma entidad, y
esos archivos no siempre escriben igual el nombre de un puesto de votación.

Caso real, Barrancabermeja 2023: de 67 puestos, 66 cruzan por identificador. El que falla
es el mismo lugar escrito de dos formas —`COL EL CASTILLO SEDE D  EL PALMAR` en los
resultados y `COL EL CASTILLO SEDE DEL PALMAR` en el censo—, una diferencia de un espacio.
Por código de zona y puesto cruzan los 67.

Por eso el cruce se hace en dos pasos y **cada paso queda registrado**: primero por
`id_puesto`, que incluye el nombre; lo que sobra, por zona y código, y solo cuando esa
pareja es inequívoca en las dos tablas. Nada se empareja a la fuerza y el informe dice
cuántas filas usaron cada vía.

**Qué se cuenta como participación.** Todos los votos depositados para esa corporación:
los de candidatos, los de lista, y también los blancos, nulos y no marcados. Una tarjeta no
marcada la depositó alguien que fue a votar. Los votos **válidos** son otra cosa y se
reportan aparte.

**Una elección, un censo.** Un año puede traer dos elecciones (Congreso y Presidencia), cada
una con su propio censo. El cruce exige que coincidan año y elección; mezclarlos daría un
potencial del doble y una participación de la mitad.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Qué elección de los resultados corresponde a qué `tipo_eleccion` del censo.
EQUIVALENCIAS = {
    "ALCALDE": "AUTORIDADES TERRITORIALES",
    "CONCEJO": "AUTORIDADES TERRITORIALES",
    "ASAMBLEA": "AUTORIDADES TERRITORIALES",
    "GOBERNADOR": "AUTORIDADES TERRITORIALES",
    "JAL": "AUTORIDADES TERRITORIALES",
    "SENADO": "CONGRESO DE LA REPUBLICA",
    "CAMARA": "CONGRESO DE LA REPUBLICA",
    "PRESIDENTE": "PRESIDENTE DE LA REPUBLICA",
}


def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def censo_de_la_eleccion(censo: pd.DataFrame, corporacion: str) -> tuple[pd.DataFrame, str]:
    """Selecciona del censo la elección que corresponde a esa corporación."""
    objetivo = EQUIVALENCIAS.get(canon(corporacion))
    if objetivo is None:
        raise AssertionError(
            f"No sé qué censo corresponde a la corporación {corporacion!r}. "
            "Declara la equivalencia antes de calcular participación.")
    sel = censo[censo["tipo_eleccion"].map(canon) == objetivo]
    if sel.empty:
        disponibles = sorted(set(censo["tipo_eleccion"]))
        raise AssertionError(
            f"El censo no trae {objetivo!r}, que es lo que necesita {corporacion}. "
            f"Tipos disponibles: {disponibles}")
    return sel.copy(), objetivo


def cruzar(votos: pd.DataFrame, censo: pd.DataFrame) -> dict:
    """Une votos y censo por puesto, en dos pasos, dejando el rastro de cada uno."""
    v = (votos.groupby(["cod_zona", "cod_puesto", "puesto", "id_puesto"], as_index=False)
         .agg(votos_depositados=("votos", "sum")))

    validos = (votos[votos["clase_opcion"] != "opcion_especial"]
               .groupby("id_puesto", as_index=False)["votos"].sum()
               .rename(columns={"votos": "votos_validos"}))
    v = v.merge(validos, on="id_puesto", how="left")
    v["votos_validos"] = v["votos_validos"].fillna(0).astype(int)

    c = censo.rename(columns={"zona": "cod_zona", "puesto_votacion": "puesto_censo"})
    cols_c = ["cod_zona", "cod_puesto", "puesto_censo", "id_puesto", "potencial_electoral"]
    cols_c += [x for x in c.columns if x.startswith(("sexo_", "edad_"))]
    c = c[[x for x in cols_c if x in c.columns]].copy()
    c["potencial_electoral"] = pd.to_numeric(c["potencial_electoral"], errors="coerce")

    # Paso 1: por identificador de puesto, que incluye el nombre.
    paso1 = v.merge(c.rename(columns={"cod_zona": "_z", "cod_puesto": "_p"}),
                    on="id_puesto", how="left", suffixes=("", "_censo"))
    paso1["via_del_cruce"] = paso1["potencial_electoral"].notna().map(
        {True: "id_puesto", False: ""})

    sin_cruce = paso1[paso1["potencial_electoral"].isna()].copy()
    resueltos = paso1[paso1["potencial_electoral"].notna()].copy()

    # Paso 2: lo que quedó, por zona y código, y solo si es inequívoco en las dos tablas.
    rescatados = pd.DataFrame()
    ambiguos = pd.DataFrame()
    if len(sin_cruce):
        usados = set(resueltos["id_puesto"])
        libre = c[~c["id_puesto"].isin(usados)]
        conteo_c = libre.groupby(["cod_zona", "cod_puesto"]).size()
        conteo_v = sin_cruce.groupby(["cod_zona", "cod_puesto"]).size()
        unicos = {k for k, n in conteo_c.items() if n == 1 and conteo_v.get(k, 0) == 1}

        clave = sin_cruce.apply(lambda r: (r["cod_zona"], r["cod_puesto"]), axis=1)
        mascara = clave.isin(unicos)

        # Se conservan solo las columnas que vienen de los votos; las del censo llegaron
        # vacías en el paso 1 y se vuelven a traer en el merge. `cod_zona` y `cod_puesto`
        # son la llave del rescate, así que no se pueden soltar.
        columnas_de_votos = ["cod_zona", "cod_puesto", "puesto", "id_puesto",
                             "votos_depositados", "votos_validos"]
        candidatos = sin_cruce.loc[mascara, [x for x in columnas_de_votos
                                             if x in sin_cruce.columns]].copy()
        if len(candidatos):
            rescatados = candidatos.merge(
                libre.drop(columns=["id_puesto"]), on=["cod_zona", "cod_puesto"], how="left")
            rescatados["via_del_cruce"] = "zona_y_codigo"
        ambiguos = sin_cruce[~mascara]

    tabla = pd.concat([x for x in (resueltos, rescatados) if len(x)], ignore_index=True)
    tabla = tabla.drop(columns=[x for x in ("_z", "_p") if x in tabla.columns])

    tabla["participacion"] = (tabla["votos_depositados"]
                              / tabla["potencial_electoral"] * 100).round(2)
    tabla["abstencion"] = (100 - tabla["participacion"]).round(2)

    return {
        "tabla": tabla.sort_values(["cod_zona", "cod_puesto"]).reset_index(drop=True),
        "puestos_en_votos": int(len(v)),
        "puestos_en_censo": int(len(c)),
        "cruzaron_por_id_puesto": int((tabla["via_del_cruce"] == "id_puesto").sum()),
        "cruzaron_por_zona_y_codigo": int((tabla["via_del_cruce"] == "zona_y_codigo").sum()),
        "sin_cruce": ambiguos[["cod_zona", "cod_puesto", "puesto"]] if len(ambiguos)
                     else pd.DataFrame(columns=["cod_zona", "cod_puesto", "puesto"]),
    }


def resumen_municipal(cruce: dict) -> dict:
    """Los totales del municipio para esa corporación."""
    t = cruce["tabla"]
    pot = int(t["potencial_electoral"].sum())
    dep = int(t["votos_depositados"].sum())
    val = int(t["votos_validos"].sum())
    # La cobertura va en la tabla principal, no escondida en los controles. Si un puesto
    # no cruzó, su potencial y sus votos faltan en los dos lados: la tasa sigue siendo
    # interpretable, pero el potencial que aparece NO es el del municipio, y hay que verlo.
    en_votos = cruce["puestos_en_votos"]
    cobertura = round(len(t) / en_votos * 100, 1) if en_votos else 0.0

    return {
        "puestos_cruzados": int(len(t)),
        "puestos_en_votos": int(en_votos),
        "cobertura_de_puestos": cobertura,
        "cobertura_completa": bool(len(t) == en_votos),
        "potencial_electoral": pot,
        "votos_depositados": dep,
        "votos_validos": val,
        "participacion": round(dep / pot * 100, 2) if pot else 0.0,
        "abstencion": round(100 - dep / pot * 100, 2) if pot else 0.0,
        "votos_no_validos": dep - val,
        "pct_no_validos_sobre_depositados": round((dep - val) / dep * 100, 2) if dep else 0.0,
    }


def controles(cruce: dict, etiqueta: str) -> pd.DataFrame:
    """Controles del cruce. Lo que no cuadra bloquea, no se suaviza."""
    t = cruce["tabla"]
    filas = []

    def chequeo(nombre, valor, esperado, pasa, criticidad="Media"):
        filas.append({"tabla": etiqueta, "control": nombre, "valor": valor,
                      "esperado": esperado, "criticidad": criticidad, "pasa": pasa})

    chequeo("todos los puestos de votos encontraron su censo",
            f"{len(t)} de {cruce['puestos_en_votos']}", "iguales",
            len(t) == cruce["puestos_en_votos"], "Alta")

    if len(t):
        imposible = int((t["votos_depositados"] > t["potencial_electoral"]).sum())
        chequeo("ningún puesto tiene más votos que su potencial", imposible,
                "0 puestos", imposible == 0, "Alta")

        sin_pot = int((t["potencial_electoral"].fillna(0) <= 0).sum())
        chequeo("todo puesto tiene potencial mayor que cero", sin_pot, "0 puestos",
                sin_pot == 0, "Alta")

        fuera = int(((t["participacion"] < 5) | (t["participacion"] > 100)).sum())
        chequeo("participación dentro de un rango creíble", fuera,
                "0 puestos fuera de 5 a 100 %", fuera == 0, "Media")

        chequeo("puestos rescatados por zona y código",
                cruce["cruzaron_por_zona_y_codigo"],
                "informativo: se emparejaron por código porque el nombre difiere",
                True, "Baja")
    return pd.DataFrame(filas)


def perfil_etario(cruce: dict) -> pd.DataFrame:
    """Relaciona el perfil de edad de cada puesto con su participación.

    **Esto no dice que los jóvenes voten menos.** Dice que los puestos cuyo censo es más
    joven registran menos participación, que es una afirmación sobre puestos, no sobre
    personas. Confundir las dos cosas es la falacia ecológica, y la metodología del
    proyecto la prohíbe de forma explícita.
    """
    t = cruce["tabla"]
    cols = [c for c in t.columns if c.startswith("edad_")]
    if not cols or t.empty:
        return pd.DataFrame()

    jovenes = [c for c in cols if any(k in c for k in ("18_20", "21_25", "26_30"))]
    mayores = [c for c in cols if "mas_de_60" in c]
    if not jovenes or not mayores:
        return pd.DataFrame()

    d = t.copy()
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["pct_censo_18_a_30"] = (d[jovenes].sum(axis=1) / d["potencial_electoral"] * 100).round(2)
    d["pct_censo_mas_de_60"] = (d[mayores].sum(axis=1) / d["potencial_electoral"] * 100).round(2)
    return d[["cod_zona", "cod_puesto", "puesto", "potencial_electoral",
              "votos_depositados", "participacion",
              "pct_censo_18_a_30", "pct_censo_mas_de_60"]]
