# -*- coding: utf-8 -*-
"""Pruebas del lector MMV, formato A: el CSV consolidado de los históricos.

Estas pruebas corren **contra los archivos reales** descargados en `datos/brutos/`. No se
fabrica un CSV sintético porque el valor está justamente en comprobar que lo que la
Registraduría publicó se lee bien: codificaciones distintas por año, códigos de puesto
alfanuméricos, códigos de comuna pegados al nombre, y la llave que de verdad identifica
una fila.

Si falta un paquete, su prueba se salta y lo dice, en lugar de fallar.

    python tests/test_lector_csv.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = next(c for c in (Path(__file__).resolve(), *Path(__file__).resolve().parents)
            if (c / "src").is_dir() and (c / "notebooks").is_dir())
sys.path.insert(0, str(RAIZ))
from src.ingesta import lector_mmv as mmv  # noqa: E402

PAQUETES = {
    "2023": RAIZ / "datos/brutos/registraduria/2023/MMV_TERRITORIALES2023_SANTANDER.zip",
    "2019": RAIZ / "datos/brutos/registraduria/2019/MMV_TERRITORIALES2019_SANTANDER.zip",
    "2022": RAIZ / "datos/brutos/congreso/2022/MMV_CONGRESO_2022_SANTANDER.zip",
}

MUNICIPIO, DEPARTAMENTO = "Barrancabermeja", "Santander"

fallas, saltadas = [], []


def prueba(nombre):
    def deco(fn):
        try:
            fn()
            print(f"  OK   {nombre}")
        except FileNotFoundError as e:
            saltadas.append((nombre, str(e)))
            print(f"  SALTA {nombre}: {e}")
        except AssertionError as e:
            fallas.append((nombre, str(e)))
            print(f"  FALLA {nombre}: {e}")
        except Exception as e:  # noqa: BLE001
            fallas.append((nombre, f"{type(e).__name__}: {e}"))
            print(f"  ERROR {nombre}: {type(e).__name__}: {e}")
        return fn
    return deco


def cargar(anio: str):
    z = PAQUETES[anio]
    if not z.is_file():
        raise FileNotFoundError(f"falta {z.name}; ejecuta el cuaderno 01 con red")
    det = mmv.detectar_formato(z)
    d, r = mmv.leer_mmv_csv(z, det["miembro"], MUNICIPIO, DEPARTAMENTO)
    return d, r, det


CACHE: dict[str, tuple] = {}


def obtener(anio: str):
    if anio not in CACHE:
        CACHE[anio] = cargar(anio)
    return CACHE[anio]


print("=== 1. Detección de formato y codificación")


@prueba("los tres paquetes se reconocen como CSV consolidado")
def _():
    for anio in PAQUETES:
        if not PAQUETES[anio].is_file():
            continue
        det = mmv.detectar_formato(PAQUETES[anio])
        assert det["formato"] == "csv_consolidado", (anio, det)


@prueba("la codificación se detecta por la marca de bytes: 2023 en UTF-8, 2022 en UTF-16")
def _():
    _, r23, _ = obtener("2023")
    _, r22, _ = obtener("2022")
    assert r23["codificacion"].startswith("utf-8"), r23["codificacion"]
    assert r22["codificacion"] == "utf-16", r22["codificacion"]


@prueba("el número de columnas difiere entre años y ambos se leen")
def _():
    _, r23, _ = obtener("2023")
    _, r22, _ = obtener("2022")
    assert r23["columnas"] == 18, r23["columnas"]
    assert r22["columnas"] == 21, r22["columnas"]


print("\n=== 2. Huellas publicadas por la Registraduría")


@prueba("el SHA-256 de cada CSV coincide con el manifiesto del paquete")
def _():
    for anio in PAQUETES:
        if not PAQUETES[anio].is_file():
            continue
        det = mmv.detectar_formato(PAQUETES[anio])
        h = mmv.verificar_huella_publicada(PAQUETES[anio], det["miembro"])
        assert h["estado"] == "coincide", (anio, h)


print("\n=== 3. Descubrimiento del municipio")


@prueba("el código electoral de Barrancabermeja se descubre y es 019 en los tres años")
def _():
    for anio in PAQUETES:
        if not PAQUETES[anio].is_file():
            continue
        _, r, _ = obtener(anio)
        assert r["cod_municipio"] == "019", (anio, r["cod_municipio"])


@prueba("el código electoral no se confunde con el DANE")
def _():
    _, r, _ = obtener("2023")
    assert r["cod_municipio"] != "68081"
    assert r["cod_municipio"] != "081"


@prueba("un municipio que no está en el paquete da un mensaje útil")
def _():
    z = PAQUETES["2023"]
    if not z.is_file():
        raise FileNotFoundError("falta el paquete de 2023")
    det = mmv.detectar_formato(z)
    try:
        mmv.leer_mmv_csv(z, det["miembro"], "Ciudad Inexistente", DEPARTAMENTO)
    except AssertionError as e:
        assert "no contiene" in str(e), str(e)
        return
    raise AssertionError("no avisó que el municipio no está en el archivo")


print("\n=== 4. La llave que identifica una fila")


@prueba("el código de puesto NO basta en 2022, y con el nombre sí")
def _():
    d, _, _ = obtener("2022")
    base = ["cod_zona", "cod_puesto", "mesa", "cod_corporacion", "cod_partido",
            "cod_candidato", "cod_circunscripcion", "cod_citrep"]
    sin_nombre = int(d.duplicated(base).sum())
    con_nombre = int(d.duplicated(base + ["puesto"]).sum())
    assert sin_nombre > 0, "se esperaban colisiones de código de puesto en 2022"
    assert con_nombre == 0, f"quedan {con_nombre} duplicados incluso con el nombre"


@prueba("en 2019 y 2023 la llave completa también es única")
def _():
    for anio in ("2019", "2023"):
        if not PAQUETES[anio].is_file():
            continue
        d, _, _ = obtener(anio)
        llave = mmv.LLAVE_MESA_CSV + ["cod_corporacion", "cod_partido", "cod_candidato"]
        dup = int(d.duplicated([c for c in llave if c in d.columns]).sum())
        assert dup == 0, (anio, dup)


@prueba("id_puesto es determinista y distingue puestos con el mismo código")
def _():
    d, _, _ = obtener("2022")
    pares = d[["cod_zona", "cod_puesto", "puesto", "id_puesto"]].drop_duplicates()
    # un id por puesto real
    assert pares["id_puesto"].nunique() == pares[mmv.LLAVE_GEO_CSV].drop_duplicates().shape[0]
    # y nunca dos puestos distintos con el mismo id
    assert pares.groupby("id_puesto")["puesto"].nunique().max() == 1


@prueba("el código de puesto es alfanumérico en la zona rural: no se puede volver número")
def _():
    d, _, _ = obtener("2023")
    rural = d[d["cod_zona"] == "99"]["cod_puesto"].unique()
    letras = [c for c in rural if not c.isdigit()]
    assert letras, f"se esperaban códigos con letra en la zona 99; se vieron {sorted(rural)}"


print("\n=== 5. Nada se pierde y nada se duplica")


@prueba("el voto de lista no es la suma de los candidatos: son votos distintos")
def _():
    d, _, _ = obtener("2023")
    conc = d[d["corporacion"] == "CONCEJO"]
    cand = conc[conc["clase_opcion"] == "candidatura"]
    assert len(cand), "sin candidaturas en Concejo 2023"
    fila = cand.iloc[0]
    grupo = conc[(conc["cod_zona"] == fila["cod_zona"])
                 & (conc["cod_puesto"] == fila["cod_puesto"])
                 & (conc["puesto"] == fila["puesto"])
                 & (conc["mesa"] == fila["mesa"])
                 & (conc["cod_partido"] == fila["cod_partido"])]
    lista = grupo[grupo["clase_opcion"] == "voto_de_lista_no_preferente"]["votos"].sum()
    suma = grupo[grupo["clase_opcion"] == "candidatura"]["votos"].sum()
    if len(grupo[grupo["clase_opcion"] == "voto_de_lista_no_preferente"]):
        assert lista != suma, (
            "la fila de lista coincide con la suma de candidatos: podría ser un total y "
            "entonces sumarla duplicaría votos. Hay que revisarlo antes de seguir."
        )


@prueba("toda fila queda clasificada y las clases suman el total")
def _():
    for anio in PAQUETES:
        if not PAQUETES[anio].is_file():
            continue
        d, _, _ = obtener(anio)
        assert (d["clase_opcion"] != "").all(), anio
        assert int(d.groupby("clase_opcion")["votos"].sum().sum()) == int(d["votos"].sum())


@prueba("los votos en blanco, nulos y no marcados se conservan por separado")
def _():
    d, _, _ = obtener("2023")
    esp = d[d["clase_opcion"] == "opcion_especial"]
    codigos = {c.lstrip("0") for c in esp["cod_candidato"].unique()}
    assert codigos == {"996", "997", "998"}, codigos


@prueba("ninguna corporación queda vacía ni se mezcla con otra")
def _():
    d, r, _ = obtener("2023")
    assert set(r["corporaciones"]) == {"ALCALDE", "ASAMBLEA", "CONCEJO", "GOBERNADOR", "JAL"}, \
        r["corporaciones"]
    assert (d["corporacion"].str.strip() != "").all()
    # cada corporación tiene su propio universo de candidatos
    por_corp = d[d["clase_opcion"] == "candidatura"].groupby("corporacion")["candidato"].nunique()
    assert (por_corp > 0).all(), por_corp.to_dict()


print("\n=== 6. El original no se altera")


@prueba("el nombre de comuna original se conserva aunque traiga el código pegado")
def _():
    d, r, _ = obtener("2022")
    if not r["comunas_con_codigo_pegado"]:
        return
    pegadas = d[d["comuna"] != d["comuna_normalizada"]]
    assert len(pegadas), "se declaró que había comunas pegadas pero no se ven"
    fila = pegadas.iloc[0]
    assert str(fila["comuna"]).startswith(str(fila["cod_comuna"])), fila.to_dict()
    assert not str(fila["comuna_normalizada"]).startswith(str(fila["cod_comuna"])), fila.to_dict()


@prueba("la cédula no aparece: este formato no la publica y no se inventa")
def _():
    d, _, _ = obtener("2023")
    assert not any("cedula" in c or "documento" in c for c in d.columns), d.columns.tolist()


print("\n=== 7. Determinismo")


@prueba("dos lecturas del mismo paquete dan la misma tabla")
def _():
    z = PAQUETES["2022"]
    if not z.is_file():
        raise FileNotFoundError("falta el paquete de 2022")
    det = mmv.detectar_formato(z)
    a, _ = mmv.leer_mmv_csv(z, det["miembro"], MUNICIPIO, DEPARTAMENTO)
    b, _ = mmv.leer_mmv_csv(z, det["miembro"], MUNICIPIO, DEPARTAMENTO)
    ha = mmv.sha256_bytes(a.to_csv(index=False, lineterminator="\n").encode("utf-8"))
    hb = mmv.sha256_bytes(b.to_csv(index=False, lineterminator="\n").encode("utf-8"))
    assert ha == hb, "las dos corridas difieren"


print("\n=== 8. Controles")


@prueba("los controles pasan, y el del censo se declara no evaluable")
def _():
    d, _, _ = obtener("2023")
    conc = d[d["corporacion"] == "CONCEJO"]
    ctl = mmv.controles_csv(conc, "concejo_2023")
    altos = ctl[(ctl["criticidad"] == "Alta") & (ctl["pasa"] == False)]  # noqa: E712
    assert altos.empty, altos.to_dict("records")
    censo = ctl[ctl["control"].str.contains("potencial")]
    assert len(censo) == 1 and pd.isna(censo.iloc[0]["pasa"]), censo.to_dict("records")


print("\n" + "=" * 70)
if saltadas:
    print(f"{len(saltadas)} prueba(s) saltadas por falta de archivos.")
if fallas:
    print(f"{len(fallas)} prueba(s) sin pasar:")
    for n, m in fallas:
        print(f"  - {n}: {m}")
    sys.exit(1)
print("Todas las pruebas ejecutables pasaron.")
