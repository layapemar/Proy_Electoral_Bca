# -*- coding: utf-8 -*-
"""Pruebas del lector MMV, formato B (catálogos y ancho fijo, estilo 2026).

Se construyen paquetes sintéticos con la estructura documentada y se les plantan trampas.
El formato A (CSV consolidado, los históricos) se prueba contra los archivos reales en
test_lector_csv.py, porque fabricar un CSV de 200 MB no agregaría nada.

No hay red a la Registraduría desde aquí, así que se fabrican paquetes con la misma forma
y se les plantan trampas: huella alterada, ancho de registro cambiado, puesto con votos
ausente de DIVIPOL, candidato sin catálogo. El lector debe detenerse en todas.
"""
from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

# El módulo vive en src/ingesta/. Se sube hasta la raíz del proyecto para importarlo.
RAIZ = next(c for c in (Path(__file__).resolve(), *Path(__file__).resolve().parents)
            if (c / "src").is_dir() and (c / "notebooks").is_dir())
sys.path.insert(0, str(RAIZ))
from src.ingesta import lector_mmv as mmv  # noqa: E402

_TEMP_DIR = tempfile.TemporaryDirectory(prefix="mmv_pruebas_")
TMP = Path(_TEMP_DIR.name)

COD_DEP, COD_MUN = "27", "019"   # código electoral de Barrancabermeja observado en 2026
OTRO_DEP, OTRO_MUN = "27", "001" # otro municipio del mismo departamento, para probar el filtro


def fijo(valores: list[tuple[str, int]]) -> bytes:
    out = b""
    for v, ancho in valores:
        b = str(v).encode("cp1252")
        if len(b) > ancho:
            raise ValueError(f"{v!r} no cabe en {ancho}")
        out += b.ljust(ancho)
    return out


def divipol_bytes(puestos: list[dict]) -> bytes:
    lineas = []
    for p in puestos:
        lineas.append(fijo([
            (p["dep"], 2), (p["mun"], 3), (p["zona"], 2), (p["puesto"], 2),
            (p["departamento"], 12), (p["municipio"], 30), (p["nombre"], 40),
            ("1", 1), (p["ph"], 8), (p["pm"], 8), (p["mesas"], 6),
            (p["cod_comuna"], 2), (p["comuna"], 30),
        ]))
    return b"\r\n".join(lineas)


def candidatos_bytes(cands: list[dict]) -> bytes:
    lineas = []
    for c in cands:
        lineas.append(fijo([
            (c["corp"], 3), ("1", 1), (c["dep"], 2), (c["mun"], 3), ("01", 2),
            (c["partido"], 5), (c["cand"], 3), ("1", 1),
            (c["nombre"], 50), (c["apellido"], 50), (c["cedula"], 15),
            (c["genero"], 1), ("01", 2),
        ]))
    return b"\r\n".join(lineas)


def partidos_bytes(partidos: dict[str, str]) -> bytes:
    lineas = []
    for cod, nombre in partidos.items():
        lineas.append(fijo([(cod, 5), (nombre, 200)]) + b"X")  # byte extra no documentado
    return b"\r\n".join(lineas)


def preconteo_bytes(filas: list[dict]) -> bytes:
    lineas = []
    for f in filas:
        lineas.append(
            f["dep"].zfill(2).encode() + f["mun"].zfill(3).encode()
            + f["zona"].zfill(2).encode() + f["puesto"].zfill(2).encode()
            + f["mesa"].zfill(6).encode() + "00".encode()
            + b"9999" + b"1"
            + f["partido"].zfill(5).encode() + f["cand"].zfill(3).encode()
            + str(f["votos"]).zfill(8).encode()
        )
    return b"\r\n".join(lineas)


def escrutinio_bytes(filas: list[dict]) -> bytes:
    lineas = []
    for f in filas:
        campos = ["9999", f["dep"].zfill(2), f["mun"].zfill(3), "0" + f["zona"].zfill(2),
                  f["puesto"].zfill(2), f["mesa"].zfill(6), "01", f["corp"], "1",
                  f["partido"].zfill(5), f["cand"].zfill(3), str(f["votos"])]
        lineas.append((";".join(campos) + ";").encode("utf-8"))
    return b"\r\n".join(lineas)


def manifiesto_utf16(entradas: dict[str, bytes]) -> bytes:
    partes = []
    for nombre, datos in entradas.items():
        partes.append(f"Filename  : {nombre}\r\nSHA-256   : {mmv.sha256_bytes(datos)}\r\n")
    return "\r\n".join(partes).encode("utf-16")


# --------------------------------------------------------------- paquete sintético
PUESTOS = [
    {"dep": COD_DEP, "mun": COD_MUN, "zona": "00", "puesto": "01", "departamento": "SANTANDER",
     "municipio": "BARRANCABERMEJA", "nombre": "COLEGIO DIEGO HERNANDEZ", "ph": "1200",
     "pm": "1300", "mesas": "5", "cod_comuna": "01", "comuna": "COMUNA 1"},
    {"dep": COD_DEP, "mun": COD_MUN, "zona": "01", "puesto": "02", "departamento": "SANTANDER",
     "municipio": "BARRANCABERMEJA", "nombre": "INSTITUTO EL CAMPIN", "ph": "900",
     "pm": "950", "mesas": "4", "cod_comuna": "04", "comuna": "COMUNA 4"},
    {"dep": COD_DEP, "mun": COD_MUN, "zona": "02", "puesto": "01", "departamento": "SANTANDER",
     "municipio": "BARRANCABERMEJA", "nombre": "CORREGIMIENTO EL LLANITO", "ph": "300",
     "pm": "310", "mesas": "2", "cod_comuna": "99", "comuna": "ZONA RURAL"},
    {"dep": OTRO_DEP, "mun": OTRO_MUN, "zona": "00", "puesto": "01", "departamento": "SANTANDER",
     "municipio": "BUCARAMANGA", "nombre": "COLEGIO SANTANDER", "ph": "5000",
     "pm": "5200", "mesas": "20", "cod_comuna": "01", "comuna": "COMUNA 1"},
]

PARTIDOS = {"00000": "VOTOS SIN PARTIDO", "00001": "PARTIDO A", "00002": "PARTIDO B",
            "00003": "MOVIMIENTO C"}

CANDIDATOS = [
    # ALCALDIA (006): un candidato por partido
    {"corp": "006", "dep": COD_DEP, "mun": COD_MUN, "partido": "00001", "cand": "001",
     "nombre": "ANA LUCIA", "apellido": "GOMEZ TORRES", "cedula": "63512345", "genero": "F"},
    {"corp": "006", "dep": COD_DEP, "mun": COD_MUN, "partido": "00002", "cand": "001",
     "nombre": "JORGE ENRIQUE", "apellido": "RUEDA PINZON", "cedula": "91234567", "genero": "M"},
    # CONCEJO (007): lista con voto preferente
    {"corp": "007", "dep": COD_DEP, "mun": COD_MUN, "partido": "00001", "cand": "001",
     "nombre": "MARIA DEL PILAR", "apellido": "SANCHEZ ORTIZ", "cedula": "37123456", "genero": "F"},
    {"corp": "007", "dep": COD_DEP, "mun": COD_MUN, "partido": "00001", "cand": "002",
     "nombre": "CARLOS ANDRES", "apellido": "VILLA MORENO", "cedula": "13987654", "genero": "M"},
    {"corp": "007", "dep": COD_DEP, "mun": COD_MUN, "partido": "00003", "cand": "001",
     "nombre": "LUZ MARINA", "apellido": "CASTRO DIAZ", "cedula": "28456789", "genero": "F"},
    # Otro municipio: debe quedar fuera del filtro
    {"corp": "007", "dep": OTRO_DEP, "mun": OTRO_MUN, "partido": "00001", "cand": "001",
     "nombre": "PEDRO", "apellido": "NAVAS", "cedula": "77777777", "genero": "M"},
]

VOTOS = []
for zona, puesto, mesa in [("00", "01", "1"), ("00", "01", "2"), ("01", "02", "1"),
                           ("02", "01", "1")]:
    for corp, partido, cand, votos in [
        ("006", "00001", "001", 120), ("006", "00002", "001", 95),
        ("007", "00001", "001", 60), ("007", "00001", "002", 45),
        ("007", "00003", "001", 80),
        ("007", "00000", "997", 12),   # voto en blanco: opción especial sin etiqueta
    ]:
        VOTOS.append({"dep": COD_DEP, "mun": COD_MUN, "zona": zona, "puesto": puesto,
                      "mesa": mesa, "corp": corp, "partido": partido, "cand": cand,
                      "votos": votos})
# Mesa del otro municipio
VOTOS.append({"dep": OTRO_DEP, "mun": OTRO_MUN, "zona": "00", "puesto": "01", "mesa": "1",
              "corp": "007", "partido": "00001", "cand": "001", "votos": 400})


def armar_paquete(ruta: Path, *, divipol=None, candidatos=None, votos=None,
                  romper_huella=False, romper_ancho=False) -> Path:
    divipol = divipol if divipol is not None else PUESTOS
    candidatos = candidatos if candidatos is not None else CANDIDATOS
    votos = votos if votos is not None else VOTOS

    d_div = divipol_bytes(divipol)
    d_can = candidatos_bytes(candidatos)
    d_par = partidos_bytes(PARTIDOS)
    if romper_ancho:
        d_div = d_div + b"\r\nRECORTADO"

    basicos = io.BytesIO()
    nombres = {"DIVIPOL_TERR2023.TXT": d_div, "CANDIDATOS_TERR2023.TXT": d_can,
               "PARTIDOS_TERR2023.TXT": d_par}
    declarados = dict(nombres)
    if romper_huella:
        declarados["DIVIPOL_TERR2023.TXT"] = d_div + b"alterado"
    with zipfile.ZipFile(basicos, "w", zipfile.ZIP_DEFLATED) as zb:
        for n, d in nombres.items():
            zb.writestr(n, d)
        zb.writestr("HASH.txt", manifiesto_utf16(declarados))

    pre = preconteo_bytes(votos)
    esc = escrutinio_bytes(votos)

    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ARCHIVOSBASICOS_AUDITORES_TERRITORIALES_2023_V1.zip", basicos.getvalue())
        z.writestr("PRE_MMV_9999_PRECONTEO.txt", pre)
        z.writestr("_ficheros_MMV_4_MMV_9999_ESCRUTINIO.csv", esc)
        z.writestr("Estructuras Basicas (1808).pdf", b"%PDF-1.4 marcador de prueba")
        z.writestr("HASH_PRE_MMV_9999_PRECONTEO.txt",
                   manifiesto_utf16({"PRE_MMV_9999_PRECONTEO.txt": pre}))
    return ruta


# =============================================================== PRUEBAS
fallas = []


def prueba(nombre):
    def deco(fn):
        try:
            fn()
            print(f"  OK   {nombre}")
        except AssertionError as e:
            fallas.append((nombre, str(e)))
            print(f"  FALLA {nombre}: {e}")
        except Exception as e:  # noqa: BLE001
            fallas.append((nombre, f"{type(e).__name__}: {e}"))
            print(f"  ERROR {nombre}: {type(e).__name__}: {e}")
        return fn
    return deco


print("\n=== 1. Lectura de un paquete territorial correcto")
ZIP_OK = armar_paquete(TMP / "MMV_TERRITORIALES2023_SANTANDER.zip")
cat = mmv.abrir_catalogos(ZIP_OK)
local = cat.localizar("Barrancabermeja", "Santander")


@prueba("descubre el código electoral sin que se le diga")
def _():
    assert (local["cod_depto"], local["cod_municipio"]) == (COD_DEP, COD_MUN), local


@prueba("cuenta puestos, mesas declaradas y potencial del municipio")
def _():
    assert local["n_puestos"] == 3, local["n_puestos"]
    assert local["mesas_declaradas"] == 11, local["mesas_declaradas"]
    assert local["potencial"] == 1200 + 1300 + 900 + 950 + 300 + 310, local["potencial"]


@prueba("verifica las huellas oficiales del paquete")
def _():
    # Tres catálogos básicos más el archivo de preconteo, cada uno con su manifiesto.
    coincide = {v["archivo"] for v in cat.verificacion if v["estado"] == "coincide"}
    assert coincide == {"DIVIPOL_TERR2023.TXT", "CANDIDATOS_TERR2023.TXT",
                        "PARTIDOS_TERR2023.TXT", "PRE_MMV_9999_PRECONTEO.txt"}, coincide
    assert all(v["estado"] == "coincide" for v in cat.verificacion), cat.verificacion


@prueba("detecta las corporaciones presentes")
def _():
    t = cat.corporaciones_presentes()
    assert set(t["corporacion"]) == {"ALCALDIA", "CONCEJO"}, t.to_dict("records")


print("\n=== 2. Votos del municipio, preconteo y escrutinio")
pre, res_pre = mmv.leer_votos(ZIP_OK, "PRE_MMV_9999_PRECONTEO.txt", "preconteo", COD_DEP, COD_MUN)
esc, res_esc = mmv.leer_votos(ZIP_OK, "_ficheros_MMV_4_MMV_9999_ESCRUTINIO.csv", "escrutinio",
                              COD_DEP, COD_MUN)


@prueba("el filtro deja fuera los demás municipios del departamento")
def _():
    assert res_esc["registros_paquete"] == len(VOTOS), res_esc
    assert res_esc["registros_municipio"] == len(VOTOS) - 1, res_esc


@prueba("escrutinio normaliza la zona de 3 a 2 posiciones")
def _():
    assert set(esc["cod_zona"].unique()) <= {"00", "01", "02"}, esc["cod_zona"].unique()


pre_e, inf_pre = mmv.enriquecer(pre, cat, local)
esc_e, inf_esc = mmv.enriquecer(esc, cat, local)


@prueba("el escrutinio trae corporación propia y queda separada")
def _():
    g = esc_e.groupby("corporacion")["votos"].sum().to_dict()
    assert set(g) == {"ALCALDIA", "CONCEJO"}, g
    assert g["ALCALDIA"] == (120 + 95) * 4, g
    assert g["CONCEJO"] == (60 + 45 + 80 + 12) * 4, g


@prueba("el preconteo sin corporación la infiere solo cuando es inequívoca, y lo informa")
def _():
    assert inf_pre.get("corporacion_inferida_unica", 0) > 0, inf_pre
    # partido 00001 candidato 001 existe en ALCALDIA y en CONCEJO: debe quedar ambiguo
    assert inf_pre.get("corporacion_ambigua", 0) > 0, inf_pre


@prueba("las opciones especiales se marcan, no se descartan")
def _():
    esp = esc_e[esc_e["clase_opcion"] == "opcion_especial_sin_etiqueta"]
    assert len(esp) == 4, len(esp)
    assert int(esp["votos"].sum()) == 48, int(esp["votos"].sum())


@prueba("ningún voto se pierde al enriquecer")
def _():
    assert int(esc_e["votos"].sum()) == int(esc["votos"].sum()), "totales distintos"


@prueba("la cédula no aparece en ninguna tabla escrita")
def _():
    assert "cedula" not in esc_e.columns
    assert not any("cedula" in c for c in esc_e.columns), esc_e.columns.tolist()
    textos = esc_e.astype(str).agg(" ".join, axis=1).str.cat(sep=" ")
    for c in CANDIDATOS:
        assert c["cedula"] not in textos, f"se filtró la cédula {c['cedula']}"


@prueba("nombres de candidatos y partidos quedan resueltos")
def _():
    conc = esc_e[(esc_e["corporacion"] == "CONCEJO") &
                 (esc_e["clase_opcion"] == "candidatura_catalogada")]
    assert "MARIA DEL PILAR SANCHEZ ORTIZ" in set(conc["candidato"]), set(conc["candidato"])
    assert "MOVIMIENTO C" in set(conc["partido"]), set(conc["partido"])


@prueba("el género del candidato viaja para medir la oferta electoral")
def _():
    conc = esc_e[esc_e["clase_opcion"] == "candidatura_catalogada"]
    assert set(conc["genero_candidato"]) == {"F", "M"}, set(conc["genero_candidato"])


print("\n=== 3. Controles")
ctl = mmv.controles(esc_e, local, "escrutinio_2023")


@prueba("todos los controles pasan con un paquete correcto")
def _():
    malos = ctl[~ctl["pasa"]]
    assert malos.empty, malos.to_dict("records")


@prueba("el control de duplicados detecta una llave repetida")
def _():
    sucio = pd.concat([esc_e, esc_e.head(1)], ignore_index=True)
    c = mmv.controles(sucio, local, "sucia")
    fila = c[c["control"].str.startswith("llave mesa")].iloc[0]
    assert not fila["pasa"] and fila["criticidad"] == "Alta", fila.to_dict()


@prueba("el control de potencial detecta votos imposibles")
def _():
    imposible = esc_e.copy()
    imposible.loc[imposible.index[0], "votos"] = 10_000_000
    c = mmv.controles(imposible, local, "imposible")
    fila = c[c["control"].str.contains("potencial")].iloc[0]
    assert not fila["pasa"], fila.to_dict()


print("\n=== 4. Preconteo contra escrutinio: se comparan, no se fusionan")


@prueba("sin diferencias cuando los dos conteos coinciden")
def _():
    t = mmv.comparar_preconteo_escrutinio(pre_e, esc_e)
    assert int(t["diferencia"].abs().sum()) == 0, t.head().to_dict("records")


@prueba("la diferencia se localiza en la mesa exacta")
def _():
    modificado = esc_e.copy()
    modificado.loc[modificado.index[0], "votos"] += 7
    t = mmv.comparar_preconteo_escrutinio(pre_e, modificado)
    assert int(t.iloc[0]["diferencia"]) == 7, t.head(2).to_dict("records")
    assert int(t["diferencia"].abs().sum()) == 7, "se contaminaron otras mesas"


print("\n=== 5. Trampas: el lector debe detenerse")


@prueba("huella oficial alterada detiene la lectura")
def _():
    z = armar_paquete(TMP / "huella_mala.zip", romper_huella=True)
    try:
        mmv.abrir_catalogos(z)
    except AssertionError as e:
        assert "SHA-256" in str(e), str(e)
        return
    raise AssertionError("aceptó un paquete con huella alterada")


@prueba("ancho de registro inesperado detiene la lectura e informa lo observado")
def _():
    z = armar_paquete(TMP / "ancho_malo.zip", romper_ancho=True)
    try:
        mmv.abrir_catalogos(z, verificar_huellas=False)
    except ValueError as e:
        assert "Anchos observados" in str(e), str(e)
        return
    raise AssertionError("aceptó un DIVIPOL con registros de otro ancho")


@prueba("votos en un puesto ausente de DIVIPOL detienen la lectura")
def _():
    sin_puesto = [p for p in PUESTOS if not (p["mun"] == COD_MUN and p["zona"] == "02")]
    z = armar_paquete(TMP / "sin_puesto.zip", divipol=sin_puesto)
    c = mmv.abrir_catalogos(z)
    l = c.localizar("Barrancabermeja", "Santander")
    d, _ = mmv.leer_votos(z, "_ficheros_MMV_4_MMV_9999_ESCRUTINIO.csv", "escrutinio",
                          COD_DEP, COD_MUN)
    try:
        mmv.enriquecer(d, c, l)
    except AssertionError as e:
        assert "no está en" in str(e) or "DIVIPOL" in str(e), str(e)
        return
    raise AssertionError("aceptó votos de un puesto que no existe en DIVIPOL")


@prueba("candidato sin catálogo se marca y se cuenta, no se descarta")
def _():
    faltante = [c for c in CANDIDATOS if not (c["corp"] == "007" and c["partido"] == "00003")]
    z = armar_paquete(TMP / "sin_candidato.zip", candidatos=faltante)
    c = mmv.abrir_catalogos(z)
    l = c.localizar("Barrancabermeja", "Santander")
    d, _ = mmv.leer_votos(z, "_ficheros_MMV_4_MMV_9999_ESCRUTINIO.csv", "escrutinio",
                          COD_DEP, COD_MUN)
    e, inf = mmv.enriquecer(d, c, l)
    assert inf["sin_etiqueta"] == 4, inf
    assert int(e["votos"].sum()) == int(d["votos"].sum()), "se perdieron votos"
    ctl2 = mmv.controles(e, l, "x")
    fila = ctl2[ctl2["control"].str.contains("sin equivalencia")].iloc[0]
    assert not fila["pasa"] and fila["criticidad"] == "Alta", fila.to_dict()


@prueba("municipio que no está en el paquete da un mensaje útil")
def _():
    try:
        cat.localizar("Puerto Wilches", "Santander")
    except AssertionError as e:
        assert "no contiene" in str(e), str(e)
        return
    raise AssertionError("no avisó que el municipio no está")


print("\n=== 6. Determinismo")


@prueba("dos lecturas del mismo paquete dan tablas idénticas")
def _():
    a, _ = mmv.leer_votos(ZIP_OK, "_ficheros_MMV_4_MMV_9999_ESCRUTINIO.csv", "escrutinio",
                          COD_DEP, COD_MUN)
    b, _ = mmv.leer_votos(ZIP_OK, "_ficheros_MMV_4_MMV_9999_ESCRUTINIO.csv", "escrutinio",
                          COD_DEP, COD_MUN)
    ae, _ = mmv.enriquecer(a, cat, local)
    be, _ = mmv.enriquecer(b, cat, local)
    ca = ae.to_csv(index=False, lineterminator="\n").encode("utf-8")
    cb = be.to_csv(index=False, lineterminator="\n").encode("utf-8")
    assert mmv.sha256_bytes(ca) == mmv.sha256_bytes(cb), "las dos corridas difieren"


print("\n" + "=" * 70)
if fallas:
    print(f"{len(fallas)} prueba(s) sin pasar:")
    for n, m in fallas:
        print(f"  - {n}: {m}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
print("\nMuestra de la tabla final (escrutinio, Concejo):")
cols = ["corporacion", "cod_zona", "cod_puesto", "mesa", "partido", "candidato",
        "clase_opcion", "votos"]
print(esc_e[esc_e["corporacion"] == "CONCEJO"][cols].head(8).to_string(index=False))
