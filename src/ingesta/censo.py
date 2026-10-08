# -*- coding: utf-8 -*-
"""Censo electoral por puesto de votación · Registraduría Nacional del Estado Civil.

**Por qué importa.** El censo es el **denominador**. Sin él no existe la participación ni
la abstención, que son la mitad de lo que cualquiera espera de un análisis electoral. Y sin
él tampoco se puede controlar que los votos de una mesa no superen su potencial.

**Dónde está.** La consulta pública de censos históricos no sirve los datos por formulario:
los trae embebidos, y cada año es **un archivo JSON de descarga directa**:

    https://www.registraduria.gov.co/IMG/json/{AÑO}_datos_censo-electoral-min.json

Verificado para 2018, 2019, 2022, 2023, 2024, 2025 y 2026. Son archivos nacionales, por
puesto de votación, de entre 0,4 y 26 MB.

**Qué trae cada registro**, que es más de lo que se necesitaba:

| Campo | |
| --- | --- |
| anio, tipo_eleccion | |
| cod_depto, departamento, cod_mun, municipio | el código es el **electoral**, no el DANE |
| zona, cod_puesto, puesto_votacion | la granularidad que pide el proyecto |
| potencial_electoral | el denominador |
| sexo | hombres, mujeres, otros |
| rango_etario | 18-20, 21-25 … más de 60, sin fecha de nacimiento, extranjero |

Los rangos etarios por puesto abren además el objetivo de variables demográficas sin
depender del censo de población, y sin salir de la fuente electoral.

**Cuidado con el año.** El censo que se usa para medir la participación de una elección es
el de **esa** elección. Mezclar años produce tasas que parecen razonables y están mal. Por
eso cada archivo conserva su columna `anio` y su `tipo_eleccion`, y nada se fusiona aquí.

**Cómo correr:**

    python src/ingesta/censo.py

Descarga los años que necesita el corpus, deja los JSON originales intactos en
`datos/brutos/registraduria/censo/` y escribe la tabla del municipio en
`datos/procesados/censo/`.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

PLANTILLA = "https://www.registraduria.gov.co/IMG/json/{anio}_datos_censo-electoral-min.json"

PAGINA_CONSULTA = ("https://www.registraduria.gov.co/-Consulta-los-censos-historicos-"
                   "utilizados-para-los-procesos-electorales-desde-.html")

# El sitio responde 403 a las peticiones que no parecen venir de un navegador. Lo que
# marca la diferencia es el `Referer`: la página de consulta desde la que el navegador
# real pide el JSON.
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": PAGINA_CONSULTA,
    "Connection": "keep-alive",
}

MUNICIPIO = "BARRANCABERMEJA"
DEPARTAMENTO = "SANTANDER"

# Los años que necesita el corpus actual de votos: territoriales 2019 y 2023, Congreso 2022.
# 2018 y 2026 se incluyen porque el proyecto ya tiene esas elecciones presidenciales.
ANIOS = ("2018", "2019", "2022", "2023", "2026")

RANGOS = ["18-20", "21-25", "26-30", "31-35", "36-40", "41-45", "46-50", "51-55",
          "56-60", "mas de 60", "sin fecha de nacimiento", "extranjero"]

OPCIONES_CSV = {"index": False, "float_format": "%.6f", "lineterminator": "\n",
                "encoding": "utf-8-sig"}


def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def id_puesto(cod_zona: str, cod_puesto: str, nombre: str) -> str:
    """Mismo identificador que usa el lector de votos, para que las dos tablas crucen.

    Se construye con el nombre además del código porque el código de puesto no identifica
    el puesto en todos los años. Es determinista.
    """
    import hashlib
    clave = "|".join([str(cod_zona), str(cod_puesto), canon(nombre)])
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------- descarga
class DescargaFallida(Exception):
    pass


def descargar(anio: str, destino: Path) -> dict:
    """Baja el JSON del año y lo deja intacto. Si ya está, no lo vuelve a bajar."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        return {"anio": anio, "estado": "existente", "bytes": destino.stat().st_size,
                "ruta": destino}
    url = PLANTILLA.format(anio=anio)
    parcial = destino.with_suffix(destino.suffix + ".parcial")

    def _con_requests() -> bool:
        """Segundo intento con `requests`, que negocia la conexión de otra manera."""
        try:
            import requests
        except ImportError:
            return False
        try:
            with requests.get(url, headers=CABECERAS, timeout=180, stream=True) as r:
                if r.status_code != 200:
                    return False
                with open(parcial, "wb") as f:
                    for t in r.iter_content(1 << 20):
                        f.write(t)
            return True
        except Exception:  # noqa: BLE001
            parcial.unlink(missing_ok=True)
            return False

    try:
        pet = urllib.request.Request(url, headers=CABECERAS)
        with urllib.request.urlopen(pet, timeout=180) as r, open(parcial, "wb") as f:
            primero = True
            while True:
                t = r.read(1 << 20)
                if not t:
                    break
                if primero:
                    inicio = t[:200].decode("utf-8", "replace").lstrip()
                    if not inicio.startswith(("[", "{")):
                        parcial.unlink(missing_ok=True)
                        return {"anio": anio, "estado": "respuesta_no_es_json",
                                "bytes": 0, "ruta": None,
                                "detalle": inicio[:120].replace("\n", " ")}
                    primero = False
                f.write(t)
        parcial.replace(destino)
        return {"anio": anio, "estado": "descargado", "bytes": destino.stat().st_size,
                "ruta": destino}
    except Exception as e:  # noqa: BLE001
        parcial.unlink(missing_ok=True)
        # Un 403 suele ser el filtro del sitio, no un problema del archivo. Se reintenta
        # con otra librería antes de darlo por perdido.
        if _con_requests() and parcial.exists() and parcial.stat().st_size > 0:
            parcial.replace(destino)
            return {"anio": anio, "estado": "descargado_segundo_intento",
                    "bytes": destino.stat().st_size, "ruta": destino}
        parcial.unlink(missing_ok=True)
        return {"anio": anio, "estado": f"fallo: {type(e).__name__}: {e}",
                "bytes": 0, "ruta": None,
                "ruta_manual": (f"Abre {url} en el navegador: descarga el JSON. "
                                f"Guárdalo como {destino.name} en {destino.parent.name}/ "
                                "y vuelve a ejecutar.")}


# --------------------------------------------------------------------- lectura
COLUMNAS_MINIMAS = ["anio", "cod_depto", "departamento", "cod_mun", "municipio",
                    "zona", "cod_puesto", "puesto_votacion", "potencial_electoral"]


class EstructuraDesconocida(Exception):
    def __init__(self, mensaje: str, diagnostico: dict):
        super().__init__(mensaje)
        self.diagnostico = diagnostico


def aplanar(registros: list[dict]) -> pd.DataFrame:
    """Convierte los campos anidados `sexo` y `rango_etario` en columnas.

    Lo que no esté entre los rangos documentados se conserva con su nombre, en lugar de
    descartarse: un rango nuevo en un año futuro no debe desaparecer en silencio.
    """
    filas = []
    for r in registros:
        fila = {k: v for k, v in r.items() if k not in ("sexo", "rango_etario")}
        for k, v in (r.get("sexo") or {}).items():
            fila[f"sexo_{canon(k).lower().replace(' ', '_')}"] = v
        for k, v in (r.get("rango_etario") or {}).items():
            fila[f"edad_{canon(k).lower().replace(' ', '_').replace('-', '_')}"] = v
        filas.append(fila)
    return pd.DataFrame(filas)


def leer_municipio(ruta_json: Path, municipio: str = MUNICIPIO,
                   departamento: str | None = DEPARTAMENTO) -> tuple[pd.DataFrame, dict]:
    """Lee el JSON nacional y devuelve solo las filas del municipio pedido.

    El código del municipio se **descubre** por el nombre y se verifica que sea único,
    igual que en el lector de votos. Suponerlo es la vía rápida a una tabla equivocada.
    """
    datos = json.loads(ruta_json.read_text(encoding="utf-8"))
    registros = datos if isinstance(datos, list) else datos.get("data", [])
    if not registros:
        raise EstructuraDesconocida(
            f"{ruta_json.name} no contiene registros.",
            {"archivo": ruta_json.name, "tipo": type(datos).__name__})

    faltan = [c for c in COLUMNAS_MINIMAS if c not in registros[0]]
    if faltan:
        raise EstructuraDesconocida(
            f"{ruta_json.name} no trae los campos {faltan}.",
            {"archivo": ruta_json.name, "campos_faltantes": faltan,
             "campos_observados": sorted(registros[0].keys())})

    objetivo = canon(municipio)
    objetivo_depto = canon(departamento) if departamento else None
    locales = [r for r in registros
               if canon(r.get("municipio")) == objetivo
               and (objetivo_depto is None or canon(r.get("departamento")) == objetivo_depto)]
    if not locales:
        raise AssertionError(
            f"{ruta_json.name} no contiene {municipio}. Revisa cómo escribe el archivo el "
            "nombre del municipio.")

    d = aplanar(locales)
    for c in ("cod_depto", "cod_mun", "zona", "cod_puesto"):
        if c in d.columns:
            d[c] = d[c].astype(str)

    codigos = set(d["cod_mun"].unique())
    if len(codigos) != 1:
        raise AssertionError(
            f"{municipio} aparece con más de un código en {ruta_json.name}: "
            f"{sorted(codigos)}. Hay que desambiguar antes de filtrar.")

    d["id_puesto"] = [id_puesto(r["zona"], r["cod_puesto"], r["puesto_votacion"])
                      for r in d.to_dict("records")]
    d["archivo_origen"] = ruta_json.name
    d["nivel_geografico"] = "puesto"
    d["fuente"] = "Registraduria_censo_historico"

    # El resumen va SIEMPRE por tipo de elección. Un año puede traer dos (Congreso y
    # Presidencia), cada una con su propio censo y sus propios puestos. Sumarlas daría un
    # potencial del doble y, con él, una participación de la mitad de la real.
    tipos = sorted(set(d.get("tipo_eleccion", pd.Series(dtype=str))))
    por_tipo = []
    for te in tipos:
        sub = d[d["tipo_eleccion"] == te]
        fila = {
            "tipo_eleccion": te,
            "puestos": int(sub["id_puesto"].nunique()),
            "potencial": int(sub["potencial_electoral"].sum()),
        }
        if "sexo_hombres" in sub.columns:
            fila["hombres"] = int(sub["sexo_hombres"].sum())
            fila["mujeres"] = int(sub["sexo_mujeres"].sum())
        por_tipo.append(fila)

    resumen = {
        "archivo": ruta_json.name,
        "registros_nacionales": len(registros),
        "registros_municipio": len(d),
        "cod_depto": d["cod_depto"].iloc[0],
        "cod_mun": d["cod_mun"].iloc[0],
        "tipos_de_eleccion": tipos,
        "elecciones_en_el_archivo": len(tipos),
        "por_tipo_de_eleccion": por_tipo,
        "puestos": int(d["id_puesto"].nunique()),
    }
    return d, resumen


def controles(d: pd.DataFrame, etiqueta: str) -> pd.DataFrame:
    """Controles del censo de un año."""
    filas = []

    def chequeo(nombre, valor, esperado, pasa, criticidad="Media"):
        filas.append({"tabla": etiqueta, "control": nombre, "valor": valor,
                      "esperado": esperado, "criticidad": criticidad, "pasa": pasa})

    if d.empty:
        chequeo("tabla no vacía", 0, "> 0 filas", False, "Alta")
        return pd.DataFrame(filas)

    dup = int(d.duplicated(["tipo_eleccion", "id_puesto"]).sum()) \
        if "tipo_eleccion" in d.columns else int(d.duplicated(["id_puesto"]).sum())
    chequeo("un registro por puesto y tipo de elección", dup, "0 duplicados",
            dup == 0, "Alta")

    neg = int((d["potencial_electoral"] < 0).sum())
    chequeo("potencial no negativo", neg, "0 registros", neg == 0, "Alta")

    if "sexo_hombres" in d.columns:
        suma = d["sexo_hombres"] + d["sexo_mujeres"] + d.get("sexo_otros", 0)
        desajuste = int((suma != d["potencial_electoral"]).sum())
        chequeo("hombres + mujeres + otros cuadra con el potencial", desajuste,
                "0 registros", desajuste == 0, "Alta")

    cols_edad = [c for c in d.columns if c.startswith("edad_")]
    if cols_edad:
        suma_edad = d[cols_edad].sum(axis=1)
        desajuste = int((suma_edad != d["potencial_electoral"]).sum())
        chequeo("los rangos etarios cuadran con el potencial", desajuste,
                "0 registros", desajuste == 0, "Media")

    return pd.DataFrame(filas)


# --------------------------------------------------------------------- ejecución
def raiz_proyecto(inicio: Path) -> Path:
    for c in (inicio.resolve(), *inicio.resolve().parents):
        if (c / "datos").is_dir() and (c / "notebooks").is_dir():
            return c
    raise FileNotFoundError("Ejecuta esto dentro de Proy_Electoral_Bca.")


def main() -> int:
    RAIZ = raiz_proyecto(Path(__file__).parent)
    BRUTOS = RAIZ / "datos" / "brutos" / "registraduria" / "censo"
    SALIDA = RAIZ / "datos" / "procesados" / "censo"
    DOCS = RAIZ / "docs" / "fuentes"
    SALIDA.mkdir(parents=True, exist_ok=True)

    print("Censo electoral por puesto · Registraduría")
    print("Destino de los originales:", BRUTOS.relative_to(RAIZ).as_posix())
    print()

    descargas, resumenes, controles_todos, tablas = [], [], [], []
    for anio in ANIOS:
        destino = BRUTOS / f"{anio}_censo_electoral.json"
        r = descargar(anio, destino)
        descargas.append({k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()})
        mb = round((r["bytes"] or 0) / 1048576, 1)
        print(f"  {anio}  {r['estado']:<22} {mb} MB")
        if r["ruta"] is None:
            continue
        try:
            d, res = leer_municipio(r["ruta"])
        except Exception as e:  # noqa: BLE001
            print(f"        no se pudo leer: {type(e).__name__}: {e}")
            continue
        res["anio"] = anio
        resumenes.append(res)
        tablas.append(d)
        controles_todos.append(controles(d, f"censo_{anio}"))
        ruta = SALIDA / f"censo_{anio}_barrancabermeja.csv"
        d.to_csv(ruta, **OPCIONES_CSV)

    if not resumenes:
        print("\nNo se obtuvo ningún año. Revisa la conexión y vuelve a ejecutar.")
        return 1

    print("\nPotencial electoral por año y elección:")
    detalle = []
    for r in resumenes:
        for pt in r["por_tipo_de_eleccion"]:
            detalle.append({"anio": r["anio"], **pt})
    tabla = pd.DataFrame(detalle)
    print(tabla.to_string(index=False))
    multiples = [r["anio"] for r in resumenes if r["elecciones_en_el_archivo"] > 1]
    if multiples:
        print(f"\nOjo: {', '.join(multiples)} traen más de una elección en el mismo año, "
              "cada una\ncon su propio censo. Para calcular participación se usa el "
              "potencial de LA elección\nque se está midiendo, nunca la suma de las dos.")

    ctl = pd.concat(controles_todos, ignore_index=True)
    fallidos = ctl[ctl["pasa"] == False]  # noqa: E712
    print(f"\nControles: {len(ctl)} evaluados, {len(fallidos)} sin pasar")
    if len(fallidos):
        print(fallidos[["tabla", "control", "valor", "esperado", "criticidad"]]
              .to_string(index=False))

    todo = pd.concat(tablas, ignore_index=True)
    todo.to_csv(SALIDA / "censo_barrancabermeja_todos_los_anios.csv", **OPCIONES_CSV)
    ctl.to_csv(SALIDA / "controles_censo.csv", **OPCIONES_CSV)

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "estado_censo.json").write_text(json.dumps({
        "plantilla_url": PLANTILLA,
        "anios": list(ANIOS),
        "descargas": descargas,
        "resumen": resumenes,
        "controles_fallidos": int(len(fallidos)),
        "advertencia": "El censo de una elección es el de ESE año. No se mezclan años "
                       "para calcular participación.",
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nEscrito en {SALIDA.relative_to(RAIZ).as_posix()}")
    print("Siguiente paso: cruzar por id_puesto contra las tablas de votos para calcular "
          "participación y abstención.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
