# -*- coding: utf-8 -*-
"""Financiación de campañas · Consejo Nacional Electoral (Cuentas Claras).

**Dónde está.** El CNE publica los reportes como CSV de descarga directa, sin formulario:

    https://www.cne.gov.co/images/data/{Ingresos|Gastos}_Candidatos_{Corporacion}_{Año}.csv

Verificado en octubre de 2026: existen `Ingresos` de Concejo, Alcaldía y Asamblea 2023, y
`Gastos` de Concejo y Asamblea 2023. El módulo descubre cuáles existen en lugar de
suponerlo, porque el CNE va publicando y la lista cambia.

---

## Tres advertencias que condicionan todo lo que se haga con estos datos

**1. El archivo trae datos personales que este proyecto no publica.** Cada fila incluye la
cédula del candidato y, cuando el aportante es persona natural, **su nombre y su cédula**.
Las reglas del proyecto son explícitas: los financiadores personas naturales no son figuras
públicas, se agregan siempre y nunca se nombran; y ningún producto lleva documentos de
identidad.

Por eso este módulo **descarta esos campos en el momento de leer**, antes de que lleguen a
ninguna tabla. En su lugar deja `aportante_id`, un identificador derivado que permite contar
aportantes distintos y detectar que el mismo aportante financió a varias campañas, **sin
poder volver atrás hasta la persona**. El original queda intacto en `datos/brutos/cne/`, que
no se versiona ni se publica.

**2. El archivo no dice el municipio.** La columna existe pero viene vacía en las 5.386
filas de Concejo 2023: solo hay departamento. Aislar Barrancabermeja obliga a **cruzar por
nombre** contra las candidaturas que ya tiene el proyecto. Eso es una **hipótesis de
identidad, no un hecho**, y como tal se declara: el cruce deja su puntaje, los casos dudosos
van a una lista de revisión y nada se fusiona en silencio.

**3. Lo reportado no es lo gastado, y además casi nadie reportó.** De ~100.000 candidaturas
a concejos en el país, el archivo de ingresos de Concejo 2023 tiene 5.386 filas. La mayoría
de las campañas no registró ingresos por este canal. Cualquier cifra que salga de aquí
describe **lo que se reportó**, que es un subconjunto pequeño y no aleatorio de lo que
ocurrió. Toda salida de este módulo lleva esa frase escrita al lado.

---

**Cómo correr:**

    python src/ingesta/cne.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

try:
    # El sitio del CNE no envía el certificado intermedio (Sectigo DV R36) en el
    # handshake TLS. Navegadores y Windows lo resuelven solos (AIA chasing); el
    # verificador de OpenSSL que usa Python por defecto, no. `truststore` delega la
    # verificación al almacén de confianza del sistema operativo y evita el fallo
    # "unable to get local issuer certificate" sin desactivar la verificación.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

HOST = "https://www.cne.gov.co"
PLANTILLA = HOST + "/images/data/{tipo}_Candidatos_{corporacion}_{anio}.csv"

CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "es-CO,es;q=0.9",
}

TIPOS = ("Ingresos", "Gastos")
CORPORACIONES = ("Concejo", "Alcaldia", "Asamblea", "Gobernacion", "JAL")
ANIOS = ("2023", "2019")

DEPARTAMENTO = "SANTANDER"
MUNICIPIO = "BARRANCABERMEJA"

ADVERTENCIA = ("Lo reportado no es lo gastado. Además, la mayoría de las campañas no "
               "registró movimientos en este sistema, así que estas cifras describen un "
               "subconjunto pequeño y no aleatorio del dinero que circuló.")

# Campos que NO pueden sobrevivir a la lectura. Se eliminan antes de construir la tabla.
CAMPOS_PROHIBIDOS = [
    "CAN_IDENTIFICACION",      # cédula del candidato
    "ING_IDENTIFICACION",      # cédula del aportante
    "GAS_IDENTIFICACION",      # cédula del proveedor, en el archivo de gastos
    "NOMBRE_PERSONA",          # nombre del aportante persona natural
    "NOMBRE_PROVEEDOR",
    "CAN_TIPO_IDENTIFICACION",
    "TID_NOMBRE",
]

OPCIONES_CSV = {"index": False, "float_format": "%.6f", "lineterminator": "\n",
                "encoding": "utf-8-sig"}


def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def tokens(s) -> set[str]:
    particulas = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "DA", "DI", "VAN", "VON"}
    return {t for t in re.sub(r"[^A-ZÑ ]", " ", canon(s)).split()
            if len(t) > 2 and t not in particulas}


def parecido(a, b) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def seudonimo(*partes) -> str:
    """Identificador derivado y estable, que no permite volver a la persona.

    Se usa para contar aportantes distintos y ver si uno financió varias campañas. No es
    reversible y no se publica junto a ningún nombre.
    """
    crudo = "|".join(canon(p) for p in partes if p)
    return hashlib.sha256(("cne-aportante|" + crudo).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ descubrimiento
def descubrir(timeout: int = 60) -> list[dict]:
    """Prueba las combinaciones y devuelve las que existen, con su tamaño.

    Usa GET con Range en vez de HEAD: el WAF del CNE devuelve 403 ante cualquier
    HEAD, sin importar las cabeceras, pero sí deja pasar un GET parcial de 1 byte.
    """
    cabeceras_rango = {**CABECERAS, "Range": "bytes=0-0"}
    hallados = []
    for tipo in TIPOS:
        for corp in CORPORACIONES:
            for anio in ANIOS:
                url = PLANTILLA.format(tipo=tipo, corporacion=corp, anio=anio)
                try:
                    pet = urllib.request.Request(url, headers=cabeceras_rango, method="GET")
                    with urllib.request.urlopen(pet, timeout=timeout) as r:
                        if r.status in (200, 206):
                            total = r.headers.get("Content-Range", "")
                            total_bytes = (int(total.split("/")[-1])
                                           if "/" in total
                                           else int(r.headers.get("Content-Length") or 0))
                            hallados.append({
                                "tipo": tipo, "corporacion": corp, "anio": anio,
                                "url": url, "bytes": total_bytes})
                except Exception:  # noqa: BLE001
                    continue
    return hallados


def descargar(fuente: dict, destino: Path) -> dict:
    destino.parent.mkdir(parents=True, exist_ok=True)
    nombre = f"{fuente['tipo']}_{fuente['corporacion']}_{fuente['anio']}"
    if destino.exists() and destino.stat().st_size > 0:
        return {"archivo": nombre, "estado": "existente",
                "bytes": destino.stat().st_size, "ruta": destino}
    parcial = destino.with_suffix(".parcial")
    try:
        pet = urllib.request.Request(fuente["url"], headers=CABECERAS)
        with urllib.request.urlopen(pet, timeout=300) as r, open(parcial, "wb") as f:
            while True:
                t = r.read(1 << 20)
                if not t:
                    break
                f.write(t)
        parcial.replace(destino)
        return {"archivo": nombre, "estado": "descargado",
                "bytes": destino.stat().st_size, "ruta": destino}
    except Exception as e:  # noqa: BLE001
        parcial.unlink(missing_ok=True)
        return {"archivo": nombre, "estado": f"fallo: {type(e).__name__}: {e}",
                "bytes": 0, "ruta": None}


# ------------------------------------------------------------------ lectura segura
def leer_sin_datos_personales(ruta: Path) -> tuple[pd.DataFrame, dict]:
    """Lee el CSV y elimina los campos personales en el acto.

    El seudónimo del aportante se calcula **antes** de borrar los campos, porque después
    ya no estarían; y una vez calculado, los originales desaparecen de la tabla.
    """
    d = None
    ultimo = None
    for cod in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            d = pd.read_csv(ruta, sep=";", dtype=str, encoding=cod,
                            keep_default_na=False, na_values=[])
            break
        except Exception as e:  # noqa: BLE001
            ultimo = e
    if d is None:
        raise ValueError(f"No pude leer {ruta.name}. Último error: {ultimo}")

    columnas_originales = list(d.columns)

    col_nombre = next((c for c in ("NOMBRE_PERSONA", "NOMBRE_PROVEEDOR")
                       if c in d.columns), None)
    col_doc = next((c for c in ("ING_IDENTIFICACION", "GAS_IDENTIFICACION")
                    if c in d.columns), None)
    if col_nombre or col_doc:
        d["aportante_id"] = [
            seudonimo(r.get(col_nombre, ""), r.get(col_doc, ""))
            for r in d.to_dict("records")
        ]

    eliminadas = [c for c in CAMPOS_PROHIBIDOS if c in d.columns]
    d = d.drop(columns=eliminadas)

    # Comprobación dura: ningún campo personal puede sobrevivir.
    sospechosas = [c for c in d.columns
                   if re.search(r"IDENTIFIC|CEDULA|DOCUMENT|NOMBRE_PERSONA|PROVEEDOR",
                                c, re.I)]
    if sospechosas:
        raise AssertionError(
            f"Quedaron columnas con datos personales en {ruta.name}: {sospechosas}. "
            "No se continúa.")

    for c in d.columns:
        if c.endswith("_VALOR") or c.endswith("_VALOR_PIGNORACION"):
            d[c] = pd.to_numeric(d[c].str.replace(r"[^\d\-]", "", regex=True),
                                 errors="coerce").fillna(0).astype("int64")

    resumen = {
        "archivo": ruta.name,
        "filas": int(len(d)),
        "columnas_originales": len(columnas_originales),
        "columnas_eliminadas_por_privacidad": eliminadas,
        "tiene_municipio": bool(
            "MUN_NOMBRE" in d.columns
            and (d["MUN_NOMBRE"].str.strip().replace("-", "") != "").any()),
    }
    if "DEP_NOMBRE" in d.columns:
        resumen["departamentos"] = int(d["DEP_NOMBRE"].nunique())
    return d, resumen


# ------------------------------------------------------------------ cruce por nombre
def cruzar_con_candidaturas(cne: pd.DataFrame, candidaturas: pd.DataFrame,
                            umbral: float = 0.6) -> dict:
    """Asocia filas del CNE a las candidaturas del municipio, **por nombre**.

    El archivo del CNE no trae municipio, así que este cruce es la única vía. Y es una
    **hipótesis**: dos personas pueden llamarse igual, y una misma persona puede aparecer
    escrita de formas distintas. Por eso devuelve tres cosas separadas y no una sola tabla:
    lo que cruza con holgura, lo dudoso que hay que revisar a mano, y lo que no cruzó.
    """
    if "DEP_NOMBRE" in cne.columns:
        cne = cne[cne["DEP_NOMBRE"].map(canon) == canon(DEPARTAMENTO)].copy()

    col_cand = next((c for c in ("NOMBRE_CANDIDATO", "CANDIDATO") if c in cne.columns), None)
    if col_cand is None:
        raise AssertionError("El archivo del CNE no trae el nombre del candidato.")

    locales = candidaturas["candidato"].dropna().unique().tolist()
    seguros, dudosos, sin_cruce = [], [], []
    cache: dict[str, tuple] = {}

    for nombre in cne[col_cand].unique():
        if nombre in cache:
            continue
        mejor, puntaje = None, 0.0
        for loc in locales:
            p = parecido(nombre, loc)
            if p > puntaje:
                mejor, puntaje = loc, p
        cache[nombre] = (mejor, puntaje)
        fila = {"nombre_en_cne": nombre, "candidatura_del_municipio": mejor,
                "puntaje": round(puntaje, 3)}
        if puntaje >= 0.85:
            seguros.append(fila)
        elif puntaje >= umbral:
            dudosos.append(fila)
        else:
            sin_cruce.append(fila)

    cne["candidatura_del_municipio"] = cne[col_cand].map(lambda n: cache.get(n, (None, 0))[0])
    cne["puntaje_cruce"] = cne[col_cand].map(lambda n: round(cache.get(n, (None, 0))[1], 3))
    cne["cruce"] = pd.cut(cne["puntaje_cruce"], bins=[-0.01, umbral, 0.85, 1.0],
                          labels=["sin_cruce", "dudoso", "seguro"])

    return {
        "tabla": cne,
        "seguros": pd.DataFrame(seguros),
        "dudosos_para_revisar": pd.DataFrame(dudosos),
        "sin_cruce": pd.DataFrame(sin_cruce),
        "umbral": umbral,
        "advertencia": ("El cruce es por nombre y es una hipótesis, no un hecho. Los "
                        "dudosos se revisan a mano antes de usarlos."),
    }


def agregar_sin_nombrar(cne: pd.DataFrame) -> pd.DataFrame:
    """Resumen por candidatura, sin nombrar a ningún aportante.

    Es la única forma en que la financiación puede salir a un producto público: agregada.
    """
    col_valor = next((c for c in cne.columns if c.endswith("_VALOR")), None)
    if col_valor is None:
        raise AssertionError("No encuentro la columna de valor en el archivo del CNE.")

    g = cne.groupby(["candidatura_del_municipio", "ORG_NOMBRE"], dropna=True)
    t = g.agg(
        movimientos=(col_valor, "size"),
        valor_total=(col_valor, "sum"),
        aportantes_distintos=("aportante_id", "nunique"),
    ).reset_index()
    if "TPE_NOMBRE" in cne.columns:
        naturales = (cne[cne["TPE_NOMBRE"].map(canon) == "PERSONA NATURAL"]
                     .groupby("candidatura_del_municipio")[col_valor].sum())
        juridicas = (cne[cne["TPE_NOMBRE"].map(canon) == "PERSONA JURIDICA"]
                     .groupby("candidatura_del_municipio")[col_valor].sum())
        t["de_personas_naturales"] = t["candidatura_del_municipio"].map(naturales).fillna(0).astype("int64")
        t["de_personas_juridicas"] = t["candidatura_del_municipio"].map(juridicas).fillna(0).astype("int64")
    t["advertencia"] = ADVERTENCIA
    return t.sort_values("valor_total", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ ejecución
def raiz_proyecto(inicio: Path) -> Path:
    for c in (inicio.resolve(), *inicio.resolve().parents):
        if (c / "datos").is_dir() and (c / "notebooks").is_dir():
            return c
    raise FileNotFoundError("Ejecuta esto dentro de Proy_Electoral_Bca.")


def main() -> int:
    RAIZ = raiz_proyecto(Path(__file__).parent)
    BRUTOS = RAIZ / "datos" / "brutos" / "cne"
    SALIDA = RAIZ / "datos" / "procesados" / "financiacion"
    SALIDA.mkdir(parents=True, exist_ok=True)

    print("Financiación de campañas · CNE")
    print(ADVERTENCIA)
    print()

    print("Buscando qué archivos publica el CNE…")
    fuentes = descubrir()
    if not fuentes:
        print("No encontré ningún archivo. Revisa la conexión y vuelve a ejecutar.")
        return 1
    for f in fuentes:
        print(f"  {f['tipo']:<9} {f['corporacion']:<12} {f['anio']}  "
              f"{round(f['bytes'] / 1048576, 1)} MB")

    # Candidaturas del municipio, que ya produjo el cuaderno 01.
    votos = sorted((RAIZ / "datos" / "procesados" / "votos").rglob("*concejo*"))
    votos = [p for p in votos if p.suffix == ".csv"]
    candidaturas = pd.DataFrame()
    if votos:
        d = pd.read_csv(votos[-1], dtype=str)
        candidaturas = (d[d["clase_opcion"] == "candidatura"][["candidato", "partido"]]
                        .drop_duplicates())
        print(f"\nCandidaturas del municipio disponibles para el cruce: {len(candidaturas)}")
    else:
        print("\nNo hay tablas de Concejo todavía: el cruce por nombre se omite. "
              "Ejecuta primero el cuaderno 01.")

    descargas, resumenes = [], []
    for f in fuentes:
        nombre = f"{f['tipo']}_{f['corporacion']}_{f['anio']}.csv"
        r = descargar(f, BRUTOS / nombre)
        descargas.append({k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()})
        print(f"\n  {nombre}: {r['estado']}")
        if r["ruta"] is None:
            continue
        d, res = leer_sin_datos_personales(r["ruta"])
        res.update({"tipo": f["tipo"], "corporacion": f["corporacion"], "anio": f["anio"]})
        resumenes.append(res)
        print(f"     {res['filas']:,} filas · eliminadas por privacidad: "
              f"{res['columnas_eliminadas_por_privacidad']}".replace(",", "."))
        print(f"     ¿el archivo trae municipio?: {'sí' if res['tiene_municipio'] else 'NO'}")

        if len(candidaturas) and f["corporacion"] == "Concejo":
            cruce = cruzar_con_candidaturas(d, candidaturas)
            t = cruce["tabla"]
            seguros = t[t["cruce"] == "seguro"]
            print(f"     cruce por nombre: {len(cruce['seguros'])} seguros · "
                  f"{len(cruce['dudosos_para_revisar'])} dudosos · "
                  f"{len(cruce['sin_cruce'])} sin cruce")
            if len(seguros):
                agregado = agregar_sin_nombrar(seguros)
                agregado.to_csv(SALIDA / f"financiacion_{f['tipo'].lower()}_concejo_"
                                         f"{f['anio']}.csv", **OPCIONES_CSV)
                print(f"     escrito el agregado de {len(agregado)} candidaturas")
            cruce["dudosos_para_revisar"].to_csv(
                SALIDA / f"revisar_cruce_{f['tipo'].lower()}_{f['anio']}.csv", **OPCIONES_CSV)

    (RAIZ / "docs" / "fuentes" / "estado_cne.json").write_text(json.dumps({
        "plantilla_url": PLANTILLA,
        "archivos_publicados": fuentes,
        "descargas": descargas,
        "resumenes": resumenes,
        "advertencia": ADVERTENCIA,
        "privacidad": ("Las cédulas y los nombres de aportantes personas naturales se "
                       "eliminan al leer. Solo sobrevive un identificador derivado no "
                       "reversible, para contar aportantes distintos sin nombrarlos."),
        "limitacion_municipio": ("Los archivos del CNE no traen municipio. Aislar "
                                 "Barrancabermeja exige cruzar por nombre, que es una "
                                 "hipótesis y se revisa a mano."),
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nEscrito en {SALIDA.relative_to(RAIZ).as_posix()}")
    print("\nRecuerda: toda cifra que salga de aquí lleva escrita la advertencia, y los")
    print("financiadores personas naturales se publican siempre agregados, nunca con nombre.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
