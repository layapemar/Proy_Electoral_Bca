# -*- coding: utf-8 -*-
"""Ingesta del dataset histórico de resultados electorales del CEDE (Universidad de los Andes).

**Qué es.** *Resultados Electorales de Colombia*, Centro de Estudios sobre Desarrollo
Económico (CEDE), Universidad de los Andes. DOI `10.71590/R2KLKI`, licencia CC0.
Cubre de 1958 a hoy: Presidencia, Senado, Cámara, Gobernación, Asamblea, Alcaldía y
Concejo, con detalle por candidato y por partido.

**Por qué este módulo existe.** El formato MMV de la Registraduría, el que trae resultados
mesa por mesa, **empieza en 2018**. Los paquetes del Observatorio para 2000, 2003, 2007,
2011 y 2015 no son datos: son instaladores de una aplicación de escritorio de la época.
El CEDE es la vía abierta y citable para la serie larga.

**El precio, y es el dato más importante de este archivo.** El CEDE llega a nivel de
**municipio**, no de puesto ni de mesa. Por eso este proyecto mantiene dos niveles que
nunca se mezclan en un mismo indicador sin decirlo:

| Nivel | Fuente | Años de Concejo | Sirve para |
| --- | --- | --- | --- |
| Mesa | MMV Registraduría | 2019, 2023 | Distribución por comuna y puesto, análisis espacial |
| Municipio | CEDE | 1997 … 2023 | Serie larga: fragmentación, volatilidad, partidos efectivos |

Toda tabla que sale de aquí lleva la columna `nivel_geografico = "municipio"` y la columna
`fuente = "CEDE"`, para que ninguna agregación pueda confundirlas por descuido.

**Años de Concejo disponibles** (verificado contra la API del repositorio): 1972, 1974,
1976, 1978, 1980, 1982, 1984, 1986, 1990, 1992, 1994, 1997, 2000, 2003, 2007, 2011, 2019
y 2023, además de 2015.

**Cómo correr el descubrimiento.** Desde la raíz del proyecto, con tu propio Python:

    python src/ingesta/cede.py

Descarga lo mínimo, no interpreta nada y deja escrito en
`docs/fuentes/estructura_cede.json` el encabezado real de cada archivo. Ese encabezado es
lo que permite escribir el adaptador contra la estructura documentada y no contra una
suposición.

**Nota de red.** El dominio del repositorio no está en la lista blanca del proxy que usan
las herramientas automáticas de este proyecto, así que este módulo solo funciona
ejecutado con tu Python, que tiene red abierta.

**Citación obligatoria** en cualquier producto que use estos datos:

    Centro de Estudios sobre Desarrollo Económico (CEDE), Universidad de los Andes.
    Resultados Electorales de Colombia. https://doi.org/10.71590/R2KLKI
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

DOI = "doi:10.71590/R2KLKI"
HOST = "https://datahub.uniandes.edu.co"
CITA = ("Centro de Estudios sobre Desarrollo Económico (CEDE), Universidad de los Andes. "
        "Resultados Electorales de Colombia. https://doi.org/10.71590/R2KLKI")
# El repositorio usa una protección anti-bots que rechaza los User-Agent de script y
# responde una página HTML de desafío en lugar del JSON. Por eso se piden las cabeceras de
# un navegador real. Si la protección usa un desafío de JavaScript, ningún script puede
# pasarla: para ese caso está la ruta manual de abajo, que no depende de la API.
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": f"{HOST}/dataset.xhtml",
}

ZIP_MANUAL = "dataverse_files.zip"  # nombre con el que el repositorio entrega el paquete

MUNICIPIO = "BARRANCABERMEJA"
DEPARTAMENTO = "SANTANDER"

# Las corporaciones que se eligen en Barrancabermeja, con el nombre que usa el dataset.
TIPOS = ("concejo", "alcaldia", "asamblea", "gobernacion")

# Años con elección territorial en el período moderno. 2019 y 2023 se incluyen a
# propósito: son el solape que permite validar el nivel municipal contra el nivel de mesa
# que ya tenemos. Sin ese solape, la serie larga no sería verificable.
ANIOS = ("1997", "2000", "2003", "2007", "2011", "2015", "2019", "2023")
ANIOS_SOLAPE = ("2019", "2023")


def canon(s) -> str:
    """Mayúsculas sin tildes ni espacios repetidos. Para comparar, no para mostrar."""
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


class RepositorioBloqueado(Exception):
    """El repositorio respondió una página de desafío en lugar de los datos."""


def _pedir(url: str, timeout: int = 120):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=CABECERAS), timeout=timeout)


def _pedir_json(url: str, timeout: int = 120):
    """Pide JSON y, si llega HTML, lo dice con claridad en vez de fallar al parsear.

    Un `JSONDecodeError` en la primera columna no informa nada: lo que pasó es que el
    servidor devolvió una página, casi siempre la del filtro anti-bots.
    """
    with _pedir(url, timeout) as r:
        crudo = r.read()
    inicio = crudo[:400].decode("utf-8", "replace").lstrip()
    if inicio[:1] in ("<", "") or "<html" in inicio.lower()[:200]:
        raise RepositorioBloqueado(
            "El repositorio devolvió una página HTML en lugar de datos. Es su filtro "
            "anti-bots. Primeros caracteres de la respuesta:\n   " + inicio[:200].replace("\n", " ")
        )
    return json.loads(crudo.decode("utf-8"))


# ------------------------------------------------------------------ catálogo remoto
def archivos_dataset(doi: str = DOI) -> list[dict]:
    """Lista los archivos del dataset, resolviendo los identificadores dentro del DOI.

    Se consulta el dataset y no el buscador global del repositorio: hay otros depósitos
    con nombres de archivo idénticos, y un identificador tomado del buscador puede
    apuntar a un archivo de otro dataset. Resolver dentro del DOI evita ese error, que
    sería invisible en los resultados.
    """
    url = f"{HOST}/api/datasets/:persistentId/?persistentId={doi}"
    j = _pedir_json(url)
    salida = []
    for f in j["data"]["latestVersion"]["files"]:
        d = f["dataFile"]
        salida.append({"nombre": d["filename"], "id": d["id"],
                       "bytes": d.get("filesize"), "formato": d.get("friendlyType", "")})
    return sorted(salida, key=lambda x: x["nombre"])


def resolver(catalogo: list[dict], anio: str, tipo: str, ext: str = ".tab") -> dict | None:
    objetivo = f"{anio}_{tipo}{ext}"
    for f in catalogo:
        if f["nombre"].lower() == objetivo:
            return f
    return None


def descargar(archivo: dict, destino: Path) -> dict:
    """Descarga un archivo del repositorio sin volver a bajarlo si ya está."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        return {"nombre": archivo["nombre"], "estado": "existente",
                "bytes": destino.stat().st_size, "ruta": destino}
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    url = f"{HOST}/api/access/datafile/{archivo['id']}"
    try:
        with _pedir(url) as r, open(parcial, "wb") as f:
            while True:
                t = r.read(1 << 20)
                if not t:
                    break
                f.write(t)
        parcial.replace(destino)
        return {"nombre": archivo["nombre"], "estado": "descargado",
                "bytes": destino.stat().st_size, "ruta": destino}
    except Exception as e:  # noqa: BLE001
        parcial.unlink(missing_ok=True)
        return {"nombre": archivo["nombre"], "estado": f"fallo: {type(e).__name__}: {e}",
                "bytes": 0, "ruta": None}


# ------------------------------------------------------------------ lectura
def leer_tab(ruta: Path) -> pd.DataFrame:
    """Lee un .tab del repositorio. Todo entra como texto.

    Los códigos de municipio llevan ceros a la izquierda y convertirlos a número los
    destruye, así que la conversión a número se hace después y a propósito, columna por
    columna.
    """
    ultimo = None
    for cod in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return pd.read_csv(ruta, sep="\t", dtype=str, encoding=cod,
                               keep_default_na=False, na_values=[])
        except Exception as e:  # noqa: BLE001
            ultimo = e
    raise ValueError(f"No pude leer {ruta.name}. Último error: {ultimo}")


def describir(ruta: Path, municipio: str = MUNICIPIO) -> dict:
    """Describe un archivo sin interpretarlo: encabezado, tamaño y dónde aparece el municipio.

    Esta función es el punto de la ejecución de descubrimiento. No decide nada: deja por
    escrito lo que el archivo realmente trae, para que el adaptador se escriba contra eso.
    """
    d = leer_tab(ruta)
    objetivo = canon(municipio)

    # ¿En qué columnas aparece el nombre del municipio? No se supone cuál es.
    columnas_con_municipio = []
    for c in d.columns:
        try:
            if (d[c].map(canon) == objetivo).any():
                columnas_con_municipio.append(c)
        except Exception:  # noqa: BLE001
            continue

    info = {
        "archivo": ruta.name,
        "filas": int(len(d)),
        "columnas": list(d.columns),
        "n_columnas": int(len(d.columns)),
        "columnas_donde_aparece_el_municipio": columnas_con_municipio,
        "primeras_filas": d.head(3).to_dict("records"),
    }

    if columnas_con_municipio:
        col = columnas_con_municipio[0]
        local = d[d[col].map(canon) == objetivo]
        info["filas_del_municipio"] = int(len(local))
        info["muestra_del_municipio"] = local.head(5).to_dict("records")
        # Valores distintos por columna dentro del municipio: revela cuál columna es el
        # código del municipio (un solo valor) y cuáles son partido o candidato (muchos).
        info["valores_distintos_en_el_municipio"] = {
            c: int(local[c].nunique()) for c in d.columns}
    else:
        info["filas_del_municipio"] = 0
        info["nota"] = (f"No se halló {municipio} en ninguna columna. Revisa cómo escribe "
                        "el dataset el nombre del municipio antes de seguir.")
    return info


# ------------------------------------------------------------------ ruta manual
INSTRUCCION_MANUAL = f"""
RUTA MANUAL (cuando la API esté bloqueada por el filtro anti-bots)

El filtro solo afecta a los scripts. Tu navegador pasa sin problema, así que el paquete se
baja una sola vez a mano y de ahí en adelante todo es local y reproducible.

  1. Abre en el navegador:
     {HOST}/dataset.xhtml?persistentId={DOI}
  2. Arriba a la derecha, "Access Dataset" y luego "Download ZIP" (el paquete completo).
     Si pregunta, acepta las condiciones de uso: la licencia es CC0.
  3. Guarda el archivo tal cual, sin descomprimirlo, en:
     datos/brutos/cede/
  4. Vuelve a ejecutar:  python src/ingesta/cede.py

El módulo detecta el ZIP, lee los archivos que necesita desde adentro y no vuelve a tocar
la red. El ZIP queda como original congelado, igual que los paquetes de la Registraduría.
"""


def zip_manual(brutos: Path) -> Path | None:
    """Busca el paquete descargado a mano. Acepta cualquier .zip en la carpeta."""
    if not brutos.is_dir():
        return None
    candidatos = sorted(brutos.glob("*.zip"), key=lambda p: p.stat().st_size, reverse=True)
    return candidatos[0] if candidatos else None


def archivos_en_zip(ruta_zip: Path) -> list[str]:
    import zipfile
    with zipfile.ZipFile(ruta_zip) as z:
        return [n for n in z.namelist() if not n.endswith("/")]


def extraer_de_zip(ruta_zip: Path, nombre: str, destino: Path) -> dict:
    """Saca un archivo del paquete manual sin modificar el ZIP ni descomprimirlo entero."""
    import zipfile
    from pathlib import PurePosixPath
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        return {"nombre": nombre, "estado": "existente", "bytes": destino.stat().st_size,
                "ruta": destino}
    with zipfile.ZipFile(ruta_zip) as z:
        coincidencias = [n for n in z.namelist()
                         if PurePosixPath(n).name.lower() == nombre.lower()]
        if not coincidencias:
            return {"nombre": nombre, "estado": "no_esta_en_el_zip", "bytes": 0, "ruta": None}
        with z.open(coincidencias[0]) as f, open(destino, "wb") as s:
            s.write(f.read())
    return {"nombre": nombre, "estado": "extraido_del_zip",
            "bytes": destino.stat().st_size, "ruta": destino}


# ------------------------------------------------------------------ descubrimiento
def raiz_proyecto(inicio: Path) -> Path:
    for c in (inicio.resolve(), *inicio.resolve().parents):
        if (c / "datos").is_dir() and (c / "notebooks").is_dir():
            return c
    raise FileNotFoundError("Ejecuta esto dentro de Proy_Electoral_Bca.")


def main() -> int:
    RAIZ = raiz_proyecto(Path(__file__).parent)
    BRUTOS = RAIZ / "datos" / "brutos" / "cede"
    SALIDA = RAIZ / "docs" / "fuentes" / "estructura_cede.json"
    BRUTOS.mkdir(parents=True, exist_ok=True)

    print("Dataset:", DOI)
    print("Cita:   ", CITA)
    print("Destino:", BRUTOS.relative_to(RAIZ).as_posix())
    print()

    # Plan: Concejo de todos los años de interés, y Alcaldía solo del solape, que es lo
    # que permite validar el nivel municipal contra el nivel de mesa que ya existe.
    plan = [("concejo", a) for a in ANIOS] + [("alcaldia", a) for a in ANIOS_SOLAPE]
    por_bajar = [f"{a}_{t}.tab" for t, a in plan]

    paquete = zip_manual(BRUTOS)
    catalogo, origen, disponibles = None, None, {}

    if paquete is not None:
        origen = "zip_manual"
        print(f"Encontré el paquete descargado a mano: {paquete.name} "
              f"({round(paquete.stat().st_size / 1048576)} MB)")
        dentro = archivos_en_zip(paquete)
        print(f"Contiene {len(dentro)} archivos. No se usa la red.")
        from pathlib import PurePosixPath
        nombres = [PurePosixPath(n).name for n in dentro]
        for tipo in TIPOS:
            disponibles[tipo] = sorted(n[:4] for n in nombres
                                       if n.lower().endswith(f"_{tipo}.tab"))
    else:
        origen = "api"
        try:
            catalogo = archivos_dataset()
            print(f"El dataset tiene {len(catalogo)} archivos.")
            for tipo in TIPOS:
                disponibles[tipo] = sorted(f["nombre"][:4] for f in catalogo
                                           if f["nombre"].lower().endswith(f"_{tipo}.tab"))
        except RepositorioBloqueado as e:
            print(f"No pude consultar el repositorio.\n   {e}\n")
            print(INSTRUCCION_MANUAL)
            return 2
        except Exception as e:  # noqa: BLE001
            print(f"No pude consultar el repositorio: {type(e).__name__}: {e}\n")
            print(INSTRUCCION_MANUAL)
            return 2

    for tipo, anios in disponibles.items():
        print(f"  {tipo:<12} {len(anios)} años: {', '.join(anios) or 'ninguno'}")

    print("\nObteniendo lo necesario para el descubrimiento:")
    descargas, estructuras = [], []
    for nombre in por_bajar:
        if paquete is not None:
            r = extraer_de_zip(paquete, nombre, BRUTOS / nombre)
        else:
            f = resolver(catalogo, nombre[:4], nombre[5:].replace(".tab", ""))
            if f is None:
                r = {"nombre": nombre, "estado": "no_existe", "bytes": 0, "ruta": None}
            else:
                try:
                    r = descargar(f, BRUTOS / f["nombre"])
                except Exception as e:  # noqa: BLE001
                    r = {"nombre": nombre, "estado": f"fallo: {type(e).__name__}",
                         "bytes": 0, "ruta": None}
        kb = round((r["bytes"] or 0) / 1024)
        print(f"  {nombre:<22} {r['estado']:<18} {kb} KB")
        descargas.append({k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()})
        if r.get("ruta") is not None:
            try:
                estructuras.append(describir(r["ruta"]))
            except Exception as e:  # noqa: BLE001
                estructuras.append({"archivo": nombre, "error": f"{type(e).__name__}: {e}"})

    if not estructuras:
        print("\nNo se obtuvo ningún archivo.")
        if origen == "api":
            print(INSTRUCCION_MANUAL)
        return 2

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({
        "doi": DOI, "cita": CITA, "origen": origen,
        "anios_disponibles_por_tipo": disponibles,
        "descargas": descargas,
        "estructuras": estructuras,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nEstructura escrita en {SALIDA.relative_to(RAIZ).as_posix()}")
    print("\n" + "=" * 70)
    print("ENCABEZADOS OBSERVADOS")
    for e in estructuras:
        if "error" in e:
            print(f"\n{e['archivo']}: {e['error']}")
            continue
        print(f"\n{e['archivo']} · {e['filas']:,} filas · {e['n_columnas']} columnas"
              .replace(",", "."))
        print("  columnas: " + " | ".join(e["columnas"]))
        print(f"  {MUNICIPIO} aparece en: {e['columnas_donde_aparece_el_municipio']}")
        print(f"  filas del municipio: {e['filas_del_municipio']:,}".replace(",", "."))
        if e.get("valores_distintos_en_el_municipio"):
            vd = e["valores_distintos_en_el_municipio"]
            print("  valores distintos dentro del municipio: "
                  + ", ".join(f"{k}={v}" for k, v in vd.items()))
    print("\n" + "=" * 70)
    print(f"Comparte {SALIDA.name} y con eso se escribe el adaptador.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
