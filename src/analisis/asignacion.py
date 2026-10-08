# -*- coding: utf-8 -*-
"""Asignación de curules por cifra repartidora, y medidas de la competencia electoral.

**Qué resuelve.** Las tablas de votos dicen cuánto sacó cada quien. No dicen quién ganó.
Entre una cosa y la otra está la fórmula que la Constitución ordena aplicar, y es la que
explica por qué alguien con más votos que un electo puede quedarse por fuera.

**La regla, artículo 263 de la Constitución** (modificado por el Acto Legislativo 01 de
2009), aplicada a una corporación como el Concejo:

1. **Votos válidos** = votos por listas + votos en blanco. Los nulos y los no marcados
   **no** son válidos y no entran al denominador.
2. **Cuociente electoral** = votos válidos ÷ curules a proveer.
3. **Umbral** = 50 % del cuociente. Una lista por debajo no participa del reparto, por
   muchos votos que tenga.
4. **Cifra repartidora**: se divide la votación de cada lista habilitada entre 1, 2, 3 …
   hasta el número de curules; se ordenan todos esos cocientes de mayor a menor; el que
   ocupa la posición igual al número de curules **es** la cifra repartidora.
5. **Curules de cada lista** = parte entera de (votos de la lista ÷ cifra repartidora).
6. **Dentro de la lista**: si tiene voto preferente, las curules son para quienes más
   votos obtuvieron. Si es **lista cerrada**, el orden es el de inscripción.

**El punto 6 es el que obliga a tener cuidado.** En una lista cerrada todos los votos van
a la lista y ningún candidato tiene votación propia, así que el archivo de resultados
**no permite saber quién se posesiona**: eso está en el formulario de inscripción. Este
módulo detecta esas listas, les asigna la curul al partido y deja el nombre del electo en
blanco, marcado como `lista_cerrada`. Nunca lo inventa.

Verificado contra Barrancabermeja 2023: la fórmula reproduce 16 de las 17 curules con el
nombre exacto del electo. La restante es la del Pacto Histórico, lista cerrada, cuyo electo
figura con cero votos en los reportes oficiales justamente porque la votación fue de lista.
"""
from __future__ import annotations

import math
import unicodedata
import re

import pandas as pd

# Clases de fila que produce el lector MMV.
CLASES_DE_LISTA = ("candidatura", "voto_de_lista_no_preferente")
UMBRAL_CORPORACION = 0.5  # 50 % del cuociente, para corporaciones de más de 4 curules


def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def votos_por_lista(datos: pd.DataFrame) -> pd.DataFrame:
    """Votación de cada lista: los votos a sus candidatos más los votos de lista."""
    d = datos[datos["clase_opcion"].isin(CLASES_DE_LISTA)]
    t = (d.groupby(["cod_partido", "partido"], as_index=False)["votos"].sum()
         .sort_values("votos", ascending=False).reset_index(drop=True))
    # Una lista sin ninguna candidatura con votación propia es una lista cerrada.
    con_preferente = (d[d["clase_opcion"] == "candidatura"]
                      .groupby("cod_partido")["candidato"].nunique())
    t["candidatos_con_voto"] = t["cod_partido"].map(con_preferente).fillna(0).astype(int)
    t["lista_cerrada"] = t["candidatos_con_voto"] == 0
    return t


def desglose_de_votos(datos: pd.DataFrame) -> dict:
    """Separa los votos como los separa la ley: válidos, en blanco, nulos, no marcados."""
    esp = datos[datos["clase_opcion"] == "opcion_especial"].copy()
    esp["etiqueta"] = esp["candidato"].map(canon)
    blanco = int(esp[esp["etiqueta"].str.contains("BLANCO", na=False)]["votos"].sum())
    nulos = int(esp[esp["etiqueta"].str.contains("NULO", na=False)]["votos"].sum())
    no_marcados = int(esp[esp["etiqueta"].str.contains("NO MARCA", na=False)]["votos"].sum())
    a_listas = int(datos[datos["clase_opcion"].isin(CLASES_DE_LISTA)]["votos"].sum())
    otros_especiales = int(esp["votos"].sum()) - blanco - nulos - no_marcados
    return {
        "votos_a_listas": a_listas,
        "votos_en_blanco": blanco,
        "votos_nulos": nulos,
        "votos_no_marcados": no_marcados,
        "otras_opciones_especiales": otros_especiales,
        # El blanco es voto válido; el nulo y el no marcado no lo son.
        "votos_validos": a_listas + blanco,
        "total_depositado": int(datos["votos"].sum()),
    }


def cifra_repartidora(votaciones: list[int], curules: int) -> float:
    """El cociente que ocupa la posición número `curules` entre todos los cocientes."""
    if curules <= 0:
        raise ValueError("El número de curules debe ser positivo.")
    cocientes = sorted((v / k for v in votaciones for k in range(1, curules + 1)),
                       reverse=True)
    if len(cocientes) < curules:
        raise ValueError("No hay suficientes listas para repartir todas las curules.")
    return cocientes[curules - 1]


def asignar_curules(datos: pd.DataFrame, curules: int) -> dict:
    """Aplica la fórmula completa y devuelve el reparto con todo su rastro.

    Devuelve un diccionario con el desglose de votos, el umbral, la cifra repartidora, la
    tabla de listas con sus curules y la tabla de electos. Todo queda a la vista para que
    el resultado se pueda auditar paso a paso, que es la única forma de defenderlo.
    """
    desglose = desglose_de_votos(datos)
    listas = votos_por_lista(datos)
    validos = desglose["votos_validos"]
    cuociente = validos / curules
    umbral = cuociente * UMBRAL_CORPORACION

    listas["supera_umbral"] = listas["votos"] >= umbral
    habilitadas = listas[listas["supera_umbral"]].copy()

    # Si ninguna lista alcanza el umbral, el reparto se hace entre todas.
    umbral_aplicado = True
    if habilitadas.empty:
        habilitadas = listas.copy()
        umbral_aplicado = False

    cifra = cifra_repartidora(habilitadas["votos"].tolist(), curules)
    habilitadas["curules"] = (habilitadas["votos"] / cifra).apply(math.floor)

    listas = listas.merge(habilitadas[["cod_partido", "curules"]], on="cod_partido",
                          how="left")
    listas["curules"] = listas["curules"].fillna(0).astype(int)

    electos = _electos(datos, listas)

    return {
        "curules_a_proveer": curules,
        **desglose,
        "cuociente_electoral": cuociente,
        "umbral": umbral,
        "umbral_aplicado": umbral_aplicado,
        "cifra_repartidora": cifra,
        "listas": listas,
        "electos": electos,
        "curules_asignadas": int(listas["curules"].sum()),
        "curules_sin_nombre": int((electos["clase"] == "lista_cerrada").sum())
        if len(electos) else 0,
    }


def _electos(datos: pd.DataFrame, listas: pd.DataFrame) -> pd.DataFrame:
    """Reparte las curules de cada lista entre sus candidatos.

    En lista con voto preferente, por votación. En lista cerrada, se deja el nombre vacío:
    el orden de inscripción no está en el archivo de resultados y no se adivina.
    """
    cand = (datos[datos["clase_opcion"] == "candidatura"]
            .groupby(["cod_partido", "cod_candidato", "candidato"], as_index=False)["votos"]
            .sum())
    filas = []
    for r in listas[listas["curules"] > 0].to_dict("records"):
        if r["lista_cerrada"]:
            for puesto in range(1, r["curules"] + 1):
                filas.append({
                    "cod_partido": r["cod_partido"], "partido": r["partido"],
                    "orden_en_la_lista": puesto, "cod_candidato": "", "candidato": "",
                    "votos": 0, "clase": "lista_cerrada",
                })
            continue
        sub = (cand[cand["cod_partido"] == r["cod_partido"]]
               .sort_values(["votos", "cod_candidato"], ascending=[False, True])
               .head(r["curules"]))
        for puesto, c in enumerate(sub.to_dict("records"), start=1):
            filas.append({
                "cod_partido": r["cod_partido"], "partido": r["partido"],
                "orden_en_la_lista": puesto, "cod_candidato": c["cod_candidato"],
                "candidato": c["candidato"], "votos": int(c["votos"]),
                "clase": "voto_preferente",
            })
    if not filas:
        return pd.DataFrame(columns=["cod_partido", "partido", "orden_en_la_lista",
                                     "cod_candidato", "candidato", "votos", "clase"])
    return (pd.DataFrame(filas).sort_values(["votos", "partido"], ascending=[False, True])
            .reset_index(drop=True))


# --------------------------------------------------------------- lo que cuesta entrar
def umbral_real_de_entrada(resultado: dict, datos: pd.DataFrame) -> dict:
    """Con cuántos votos entró el último electo, y quiénes sacaron más y no entraron.

    Esta es la pregunta que la gente hace y que la cifra repartidora responde de forma
    poco intuitiva: lo que elige no es la votación personal, sino la de la lista.
    """
    electos = resultado["electos"]
    con_nombre = electos[electos["clase"] == "voto_preferente"]
    if con_nombre.empty:
        return {"sin_datos": True}

    ultimo = int(con_nombre["votos"].min())
    primero = int(con_nombre["votos"].max())

    cand = (datos[datos["clase_opcion"] == "candidatura"]
            .groupby(["cod_partido", "partido", "cod_candidato", "candidato"],
                     as_index=False)["votos"].sum())
    electos_ids = set(zip(electos["cod_partido"], electos["cod_candidato"]))
    no_electos = cand[~cand.apply(
        lambda r: (r["cod_partido"], r["cod_candidato"]) in electos_ids, axis=1)]
    mejores_perdedores = (no_electos[no_electos["votos"] > ultimo]
                          .sort_values("votos", ascending=False))

    return {
        "votos_del_primer_electo": primero,
        "votos_del_ultimo_electo": ultimo,
        "no_electos_con_mas_votos_que_el_ultimo_electo": int(len(mejores_perdedores)),
        "tabla_mejores_perdedores": mejores_perdedores,
        "sin_datos": False,
    }


def votos_sin_representacion(resultado: dict) -> dict:
    """Cuántos votos fueron a listas que no obtuvieron ninguna curul."""
    listas = resultado["listas"]
    sin_curul = listas[listas["curules"] == 0]
    validos = resultado["votos_validos"]
    perdidos = int(sin_curul["votos"].sum())
    return {
        "listas_sin_curul": int(len(sin_curul)),
        "votos_en_listas_sin_curul": perdidos,
        "porcentaje_sobre_validos": round(perdidos / validos * 100, 2) if validos else 0.0,
        "tabla": sin_curul.sort_values("votos", ascending=False),
    }


# --------------------------------------------------------------- forma de la competencia
def indicadores_competencia(resultado: dict) -> dict:
    """Medidas estándar de fragmentación y concentración, sobre votos y sobre curules.

    - **Número efectivo de partidos** (Laakso y Taagepera): cuántos partidos *pesan* de
      verdad, que casi nunca es cuántos se presentaron.
    - **HHI**: concentración, de 0 a 1. Más alto, más concentrado.
    - **Desproporcionalidad de Gallagher**: cuánto se aparta el reparto de curules del
      reparto de votos. Es la medida usual para evaluar un sistema electoral.
    """
    listas = resultado["listas"]
    v = listas["votos"].astype(float)
    total_v = v.sum()
    pv = (v / total_v) if total_v else v * 0

    c = listas["curules"].astype(float)
    total_c = c.sum()
    pc = (c / total_c) if total_c else c * 0

    def nep(p):
        s = float((p ** 2).sum())
        return round(1 / s, 2) if s else 0.0

    gallagher = round(math.sqrt(float(((pv - pc) ** 2).sum()) / 2) * 100, 2)

    return {
        "listas_inscritas_con_votos": int(len(listas)),
        "listas_que_superaron_el_umbral": int(listas["supera_umbral"].sum()),
        "listas_con_al_menos_una_curul": int((listas["curules"] > 0).sum()),
        "numero_efectivo_de_partidos_por_votos": nep(pv),
        "numero_efectivo_de_partidos_por_curules": nep(pc),
        "hhi_votos": round(float((pv ** 2).sum()), 4),
        "hhi_curules": round(float((pc ** 2).sum()), 4),
        "desproporcionalidad_gallagher": gallagher,
    }


def comparar_con_lista_oficial(resultado: dict, nombres_oficiales: list[str]) -> dict:
    """Contrasta los electos calculados contra una lista oficial de nombres.

    La comparación se hace por apellidos y nombres normalizados, no por cadena exacta:
    las fuentes escriben los nombres de formas distintas. Lo que no coincide se reporta en
    las dos direcciones, para que cada diferencia tenga que explicarse.
    """
    def clave(n):
        return " ".join(sorted(t for t in canon(n).split() if len(t) > 2))

    calc = resultado["electos"]
    con_nombre = calc[calc["clase"] == "voto_preferente"]
    mapa_calc = {clave(n): n for n in con_nombre["candidato"]}
    mapa_ofi = {clave(n): n for n in nombres_oficiales}

    def parecido(a, b):
        ta, tb = set(a.split()), set(b.split())
        return len(ta & tb) / max(len(ta | tb), 1)

    coinciden, solo_calc = [], []
    usados = set()
    for k, nombre in mapa_calc.items():
        mejor, puntaje = None, 0.0
        for ko, no in mapa_ofi.items():
            if ko in usados:
                continue
            p = parecido(k, ko)
            if p > puntaje:
                mejor, puntaje = ko, p
        if mejor is not None and puntaje >= 0.5:
            coinciden.append((nombre, mapa_ofi[mejor]))
            usados.add(mejor)
        else:
            solo_calc.append(nombre)
    solo_oficial = [n for k, n in mapa_ofi.items() if k not in usados]

    return {
        "curules_calculadas": int(len(calc)),
        "curules_con_nombre": int(len(con_nombre)),
        "curules_sin_nombre_por_lista_cerrada": int(len(calc) - len(con_nombre)),
        "nombres_oficiales": len(nombres_oficiales),
        "coinciden": len(coinciden),
        "tabla_coincidencias": coinciden,
        "solo_en_el_calculo": solo_calc,
        "solo_en_la_lista_oficial": solo_oficial,
    }
