# -*- coding: utf-8 -*-
"""Lectura de los paquetes MMV de la Registraduría Nacional del Estado Civil.

La Registraduría publica sus resultados por mesa como paquetes "MMV" (Modelo de Mesa
Virtual): un ZIP por elección y departamento. Pero **no todos tienen la misma
arquitectura**, y confundirlas es el error que hay que evitar:

**Formato A · CSV consolidado** (territoriales 2019 y 2023, Congreso 2022 y anteriores).
Un único CSV con cabecera explícita donde cada fila es un voto por mesa, corporación,
partido y candidato, con los nombres ya resueltos. No necesita catálogos. Es el formato
de los históricos y el más fácil de usar. Tiene tres variantes observadas:

| Elección | Codificación | Columnas |
| --- | --- | --- |
| Territoriales 2023 | UTF-8 | 18 |
| Territoriales 2019 | UTF-8 | 18 |
| Congreso 2022 | UTF-16 | 21 (agrega circunscripción y CITREP) |

**Formato B · catálogos y archivos de ancho fijo** (presidencia y Congreso 2026). Trae
DIVIPOL, CANDIDATOS y PARTIDOS por separado, más un preconteo de ancho fijo y un
escrutinio delimitado, y un PDF que documenta cada campo. Da más detalle —potencial de
sufragantes, género de los candidatos, preconteo frente a escrutinio— a cambio de ser
más trabajoso.

`detectar_formato()` decide cuál es cada paquete en lugar de suponerlo.

Cuatro reglas gobiernan el código de aquí:

1. **El original no se toca.** Todo se lee desde el ZIP, en memoria.
2. **Si la estructura no coincide con lo esperado, se detiene** con una excepción que
   lleva lo observado (cabecera, anchos, número de campos), para que el cuaderno lo
   registre y el esquema se declare contra la documentación, no contra una suposición.
3. **Los códigos son texto.** `cod_municipio` es `"019"`, no `19`. Convertirlo a número
   pierde el cero y rompe los cruces. Y el código electoral **no** es el código DANE:
   Barrancabermeja es `68081` en el DANE y `27`/`019` en lo electoral.
4. **Las etiquetas salen del archivo, no de un mapa interno.** El código de corporación
   `001` es GOBERNADOR en una territorial y PRESIDENTE en una presidencial; `02` es
   CÁMARA en Congreso 2022. Cuando el archivo trae el nombre, se usa el del archivo.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import pandas as pd

# --------------------------------------------------------------------- esquemas
# Anchos en bytes, tal como los declara el PDF de estructuras del paquete.

DIVIPOL_CAMPOS = [
    ("cod_depto", 2), ("cod_municipio", 3), ("cod_zona", 2), ("cod_puesto", 2),
    ("departamento", 12), ("municipio", 30), ("puesto", 40), ("indicador_puesto", 1),
    ("potencial_hombres", 8), ("potencial_mujeres", 8), ("mesas_declaradas", 6),
    ("cod_comuna_divipol", 2), ("comuna_divipol", 30),
]

CANDIDATOS_CAMPOS = [
    ("cod_corporacion", 3), ("cod_circunscripcion", 1), ("cod_depto", 2),
    ("cod_municipio", 3), ("cod_comuna", 2), ("cod_partido", 5),
    ("cod_candidato", 3), ("tipo_preferente", 1), ("nombre", 50),
    ("apellido", 50), ("cedula", 15), ("genero", 1), ("sorteo", 2),
]

PRECONTEO_CAMPOS = [
    ("cod_depto", 2), ("cod_municipio", 3), ("cod_zona", 2), ("cod_puesto", 2),
    ("mesa", 6), ("cod_jal", 2), ("comunicado", 4), ("cod_circunscripcion", 1),
    ("cod_partido", 5), ("cod_candidato", 3), ("votos", 8),
]

ESCRUTINIO_CAMPOS = [
    "valor_fijo", "cod_depto", "cod_municipio", "cod_zona", "cod_puesto",
    "mesa", "cod_comuna_escrutinio", "cod_corporacion", "cod_circunscripcion",
    "cod_partido", "cod_candidato", "votos",
]

ANCHO_PRECONTEO = sum(a for _, a in PRECONTEO_CAMPOS)   # 38
ANCHO_PARTIDO_NOMBRE = 200                               # 5 de código + 200 de nombre

# Códigos de opción que el paquete no etiqueta: votos en blanco, nulos y no marcados.
# El PDF no les asigna nombre, así que se conservan con su código y se marcan como tales.
OPCIONES_ESPECIALES = {"996", "997", "998"}

# Corporaciones. Las territoriales traen varias en un mismo archivo; separarlas es
# obligatorio porque mezclarlas suma votos de elecciones distintas.
CORPORACIONES = {
    "001": "PRESIDENTE",
    "002": "SENADO",
    "003": "CAMARA",
    "004": "GOBERNACION",
    "005": "ASAMBLEA",
    "006": "ALCALDIA",
    "007": "CONCEJO",
    "008": "JAL",
}

class EstructuraDesconocida(Exception):
    """El archivo no tiene la estructura documentada que se esperaba.

    Lleva lo observado (distribución de anchos, una línea de muestra) para que el cuaderno
    lo registre como diagnóstico en lugar de quedarse con un mensaje suelto. Así el
    siguiente paso es leer el PDF de estructuras de ese paquete y declarar el esquema, no
    adivinarlo.
    """

    def __init__(self, mensaje: str, diagnostico: dict):
        super().__init__(mensaje)
        self.diagnostico = diagnostico


GEOCAMPOS = ["cod_depto", "cod_municipio", "cod_zona", "cod_puesto"]
CLAVE_MESA = GEOCAMPOS + ["mesa"]
CLAVE_VOTO = CLAVE_MESA + ["cod_corporacion", "cod_partido", "cod_candidato"]


# ------------------------------------------------------- formato A · CSV consolidado
# Nombres canónicos. La clave es el nombre de la columna tal como viene en el archivo,
# ya normalizado (mayúsculas, sin tildes). El valor es el nombre con el que vive en el
# proyecto. Una columna que no esté aquí se conserva con su nombre normalizado: no se
# descarta nada.
COLUMNAS_CSV = {
    "CODIGO DEPARTAMENTO": "cod_depto",
    "NOMBRE DEPARTAMENTO": "departamento",
    "CODIGO MUNICIPIO": "cod_municipio",
    "NOMBRE MUNICIPIO": "municipio",
    "CODIGO ZONA": "cod_zona",
    "CODIGO PUESTO": "cod_puesto",
    "NOMBRE PUESTO": "puesto",
    "MESA": "mesa",
    "CODIGO COMUNA": "cod_comuna",
    "NOMBRE COMUNA": "comuna",
    "CODIGO CORPORACION": "cod_corporacion",
    "NOMBRE CORPORACION": "corporacion",
    "CODIGO CIRCUNSCRIPCION": "cod_circunscripcion",
    "NOMBRE CIRCUNSCRIPCION": "circunscripcion",
    "CODIGO CITREP": "cod_citrep",
    "NOMBRE CITREP": "citrep",
    "CODIGO PARTIDO": "cod_partido",
    "NOMBRE PARTIDO": "partido",
    "CODIGO CANDIDATO": "cod_candidato",
    "NOMBRE CANDIDATO": "candidato",
    "TOTAL VOTOS": "votos",
}

# Sin estas columnas el archivo no sirve para nada de lo que hace el proyecto.
COLUMNAS_MINIMAS = ["cod_depto", "cod_municipio", "municipio", "cod_zona", "cod_puesto",
                    "puesto", "mesa", "cod_corporacion", "corporacion", "cod_partido",
                    "cod_candidato", "votos"]

# Llave que identifica una fila de votos sin ambigüedad. El **nombre del puesto** forma
# parte de ella, y no por gusto: en Congreso 2022 el código de puesto viene en '00' para
# varios puestos rurales distintos de la zona 99 (EL LLANITO SEDE A, ESC. LAURELES,
# PUEBLO REGAO...), de modo que 61 puestos reales se colapsan en 56 códigos. Agrupar por
# código sumaría puestos que no son el mismo lugar. En 2019 y 2023 el código sí viene
# completo, pero la llave se mantiene igual en los tres años para que las tablas se puedan
# comparar entre sí.
#
# Ojo: `cod_puesto` **no es numérico**. En 2019 y 2023 la zona 99 usa códigos como 'A1',
# 'A5', 'B2'. Convertirlo a número destruye esas filas.
LLAVE_GEO_CSV = ["cod_zona", "cod_puesto", "puesto"]
LLAVE_MESA_CSV = LLAVE_GEO_CSV + ["mesa"]

# Opciones que no son candidaturas. Se comparan sin ceros a la izquierda porque el
# relleno cambia entre años: '997', '00997'.
CODIGOS_ESPECIALES = {"996", "997", "998"}


def detectar_codificacion(primeros_bytes: bytes) -> str:
    """Decide la codificación por la marca de orden de bytes, no por ensayo y error."""
    if primeros_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    if primeros_bytes[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def detectar_formato(ruta_zip: Path) -> dict:
    """Dice qué arquitectura tiene un paquete, mirando sus miembros.

    Devuelve el formato, el miembro de datos y por qué lo decidió, para que el cuaderno
    pueda registrar la decisión en lugar de que quede implícita en el código.
    """
    with zipfile.ZipFile(ruta_zip) as z:
        nombres = [x for x in z.namelist() if not x.endswith("/")]
        tiene_catalogos = bool(miembros_por_patron(z, r"^DIVIPOL")
                               or miembros_por_patron(z, r"ARCHIVOSBASICOS.*\.zip$"))
        csvs = [x for x in nombres
                if x.lower().endswith(".csv")
                and not PurePosixPath(x).name.upper().startswith("HASH")]

    if tiene_catalogos:
        return {"formato": "catalogos_2026", "miembro": None,
                "razon": "el paquete trae DIVIPOL o un ARCHIVOSBASICOS anidado",
                "miembros": nombres}
    if len(csvs) == 1:
        return {"formato": "csv_consolidado", "miembro": csvs[0],
                "razon": f"un único CSV de datos: {PurePosixPath(csvs[0]).name}",
                "miembros": nombres}
    return {"formato": "desconocido", "miembro": None,
            "razon": f"ni catálogos ni un CSV único; se hallaron {len(csvs)} CSV",
            "miembros": nombres}


def verificar_huella_publicada(ruta_zip: Path, miembro: str) -> dict:
    """Compara el SHA-256 del CSV contra el que la Registraduría publica en el paquete.

    El manifiesto del formato consolidado es un bloque de texto con varias huellas
    (MD5, SHA1, SHA-256...) por archivo. Solo se usa SHA-256.
    """
    with zipfile.ZipFile(ruta_zip) as z:
        manifiestos = miembros_por_patron(z, r"^HASH.*\.txt$")
        if not manifiestos:
            return {"estado": "sin_manifiesto", "sha256": None}
        texto = decodificar_manifiesto(z.read(manifiestos[0]))
        esperado = re.search(r"SHA-?256\s*:\s*([0-9a-fA-F]{64})", texto)
        calculado = sha256_flujo(z.open(miembro))
    if not esperado:
        return {"estado": "manifiesto_sin_sha256", "sha256": calculado}
    coincide = calculado == esperado.group(1).lower()
    return {"estado": "coincide" if coincide else "NO_COINCIDE",
            "sha256": calculado, "sha256_publicado": esperado.group(1).lower(),
            "manifiesto": PurePosixPath(manifiestos[0]).name}


def _clase_opcion(cod_candidato: str, cod_partido: str, nombre_candidato: str) -> str:
    """Clasifica la fila sin alterarla. Lo que no es candidatura se marca, no se borra."""
    if cod_candidato.lstrip("0") in CODIGOS_ESPECIALES or cod_candidato in CODIGOS_ESPECIALES:
        return "opcion_especial"
    if cod_partido.strip("0") == "" and canon(nombre_candidato) in {
            "CANDIDATOS TOTALES", "N/A", ""}:
        return "agregado_sin_candidatura"
    if cod_candidato.strip("0") == "":
        return "voto_de_lista_no_preferente"
    return "candidatura"


def leer_mmv_csv(ruta_zip: Path, miembro: str, municipio: str,
                 departamento: str | None = None, bloque: int = 200_000) -> tuple[pd.DataFrame, dict]:
    """Lee un CSV consolidado y devuelve solo las filas del municipio pedido.

    Lee por bloques porque estos archivos pasan de 200 MB descomprimidos y cargarlos
    enteros no haría falta: del departamento solo interesa un municipio.

    El código del municipio **se descubre** comparando el nombre. Si apareciera con dos
    códigos distintos, se detiene: filtrar por el código equivocado daría una tabla
    plausible y falsa, que es el peor resultado posible.
    """
    import csv as _csv

    with zipfile.ZipFile(ruta_zip) as z, z.open(miembro) as s:
        codificacion = detectar_codificacion(s.read(4))

    objetivo = canon(municipio)
    objetivo_depto = canon(departamento) if departamento else None
    filas, cabecera_vista = [], None
    total = 0
    codigos_municipio: set[str] = set()

    with zipfile.ZipFile(ruta_zip) as z, z.open(miembro) as s:
        flujo = io.TextIOWrapper(s, encoding=codificacion, newline="")
        lector = _csv.DictReader(flujo)
        cabecera_vista = list(lector.fieldnames or [])
        mapa = {c: COLUMNAS_CSV.get(canon(c), canon(c).lower().replace(" ", "_"))
                for c in cabecera_vista}
        faltan = [c for c in COLUMNAS_MINIMAS if c not in mapa.values()]
        if faltan:
            raise EstructuraDesconocida(
                f"El CSV {PurePosixPath(miembro).name} no trae las columnas "
                f"{faltan}. Hay que revisar la cabecera real antes de interpretarlo.",
                {"archivo": PurePosixPath(miembro).name,
                 "codificacion": codificacion,
                 "columnas_faltantes": faltan,
                 "cabecera_observada": cabecera_vista},
            )

        for cruda in lector:
            total += 1
            if canon(cruda.get("Nombre Municipio")) != objetivo:
                continue
            fila = {mapa[k]: (v if v is not None else "") for k, v in cruda.items()
                    if k in mapa}
            if objetivo_depto and canon(fila.get("departamento")) != objetivo_depto:
                continue
            codigos_municipio.add(fila["cod_municipio"])
            filas.append(fila)

    if not filas:
        raise AssertionError(
            f"{PurePosixPath(miembro).name} no contiene ninguna fila de {municipio}. "
            "Revisa el nombre: en estos archivos viene en mayúsculas y sin tildes."
        )
    if len(codigos_municipio) != 1:
        raise AssertionError(
            f"{municipio} aparece con más de un código de municipio en "
            f"{PurePosixPath(miembro).name}: {sorted(codigos_municipio)}. "
            "Hay que desambiguar antes de filtrar."
        )

    datos = pd.DataFrame(filas)
    datos["votos"] = pd.to_numeric(datos["votos"], errors="coerce").fillna(0).astype(int)
    for c in datos.columns:
        if c != "votos":
            datos[c] = datos[c].astype(str).str.strip()

    datos["clase_opcion"] = [
        _clase_opcion(r["cod_candidato"], r["cod_partido"], r.get("candidato", ""))
        for r in datos.to_dict("records")
    ]

    # El nombre de comuna de 2019 trae el código pegado al principio ('01COMUNA 1 NORTE').
    # No se corrige el original: se añade una versión limpia solo cuando el prefijo
    # coincide exactamente con el código, y queda registrado que se hizo.
    pegado = datos.apply(
        lambda r: bool(r.get("cod_comuna")) and str(r.get("comuna", "")).startswith(str(r["cod_comuna"])),
        axis=1) if "comuna" in datos.columns else pd.Series(False, index=datos.index)
    datos["comuna_normalizada"] = datos.get("comuna", "")
    if pegado.any():
        datos.loc[pegado, "comuna_normalizada"] = [
            str(r["comuna"])[len(str(r["cod_comuna"])):].strip()
            for r in datos.loc[pegado].to_dict("records")
        ]

    # Identificador estable del puesto. Se construye con el nombre además del código,
    # porque el código solo no identifica el lugar en todos los años (ver LLAVE_GEO_CSV).
    # Es determinista: el mismo puesto da el mismo identificador en cada corrida.
    datos["id_puesto"] = [
        hashlib.sha256("|".join([r["cod_zona"], r["cod_puesto"], canon(r["puesto"])])
                       .encode("utf-8")).hexdigest()[:12]
        for r in datos.to_dict("records")
    ]

    datos["archivo_origen"] = PurePosixPath(miembro).name
    # El paquete consolidado no declara si es preconteo o escrutinio. Son los resultados
    # oficiales publicados, es decir posteriores al escrutinio, pero no se afirma que
    # coincidan fila por fila con el archivo de escrutinio de un paquete 2026.
    datos["tipo_resultado"] = "resultado_publicado"

    resumen = {
        "archivo": PurePosixPath(miembro).name,
        "codificacion": codificacion,
        "columnas": len(cabecera_vista),
        "registros_departamento": total,
        "registros_municipio": len(datos),
        "cod_municipio": codigos_municipio.pop(),
        "mesas": int(datos[LLAVE_MESA_CSV].drop_duplicates().shape[0]),
        "puestos": int(datos[LLAVE_GEO_CSV].drop_duplicates().shape[0]),
        "codigos_de_puesto": int(datos[["cod_zona", "cod_puesto"]].drop_duplicates().shape[0]),
        "votos": int(datos["votos"].sum()),
        "corporaciones": sorted(datos["corporacion"].unique()),
        "comunas_con_codigo_pegado": int(pegado.sum()),
        "clases_opcion": datos["clase_opcion"].value_counts().to_dict(),
    }
    return datos, resumen


def controles_csv(datos: pd.DataFrame, etiqueta: str) -> pd.DataFrame:
    """Controles de una tabla del formato consolidado.

    Importante: este formato **no trae el censo electoral**, así que no se puede controlar
    que los votos no superen el potencial de sufragantes. Ese control queda explícitamente
    declarado como no evaluable, en lugar de omitirse en silencio.
    """
    filas = []

    def chequeo(nombre, valor, esperado, pasa, criticidad="Media"):
        filas.append({"tabla": etiqueta, "control": nombre, "valor": valor,
                      "esperado": esperado, "criticidad": criticidad, "pasa": pasa})

    if datos.empty:
        chequeo("tabla no vacía", 0, "> 0 filas", False, "Alta")
        return pd.DataFrame(filas)

    llave = LLAVE_MESA_CSV + ["cod_corporacion", "cod_partido", "cod_candidato"]
    for opcional in ("cod_circunscripcion", "cod_citrep"):
        if opcional in datos.columns:
            llave.append(opcional)
    llave = [c for c in llave if c in datos.columns]
    dup = int(datos.duplicated(llave).sum())
    chequeo("llave puesto/mesa/corporación/partido/candidato única", dup, "0 duplicados",
            dup == 0, "Alta")

    # Un código de puesto que apunta a varios puestos distintos no invalida los datos,
    # pero obliga a agrupar por id_puesto y no por código. Se avisa con el número exacto.
    por_codigo = datos[["cod_zona", "cod_puesto"]].drop_duplicates().shape[0]
    por_nombre = datos[LLAVE_GEO_CSV].drop_duplicates().shape[0]
    chequeo("el código de puesto identifica un solo puesto",
            f"{por_codigo} códigos para {por_nombre} puestos",
            "mismo número; si no, agrupar por id_puesto",
            por_codigo == por_nombre, "Media")

    neg = int((datos["votos"] < 0).sum())
    chequeo("votos no negativos", neg, "0 registros", neg == 0, "Alta")

    corp_vacia = int((datos["corporacion"].str.strip() == "").sum())
    chequeo("toda fila tiene corporación", corp_vacia, "0 registros", corp_vacia == 0, "Alta")

    sin_clasificar = int((datos["clase_opcion"] == "").sum())
    chequeo("toda fila queda clasificada", sin_clasificar, "0 registros",
            sin_clasificar == 0, "Alta")

    mesas = int(datos[LLAVE_MESA_CSV].drop_duplicates().shape[0])
    chequeo("mesas distintas", mesas, "informativo", True, "Baja")
    chequeo("puestos distintos", por_nombre, "informativo", True, "Baja")

    chequeo("votos no superan el potencial de sufragantes", "no evaluable",
            "requiere el censo electoral, que este formato no incluye", None, "Alta")

    return pd.DataFrame(filas)


# --------------------------------------------------------------------- utilidades
def canon(s) -> str:
    """Mayúsculas sin tildes ni espacios repetidos. Para comparar, no para mostrar."""
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(ruta: Path, bloque: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for t in iter(lambda: f.read(bloque), b""):
            h.update(t)
    return h.hexdigest()


def sha256_flujo(flujo, bloque: int = 1 << 20) -> str:
    """Huella de un flujo por bloques, sin cargarlo en memoria.

    Se hace a mano en lugar de con `hashlib.file_digest`, que solo existe desde
    Python 3.11: el proyecto debe correr también en 3.10.
    """
    h = hashlib.sha256()
    with flujo as f:
        for t in iter(lambda: f.read(bloque), b""):
            h.update(t)
    return h.hexdigest()


def miembros_por_nombre(z: zipfile.ZipFile, nombre: str) -> list[str]:
    """Miembros cuyo nombre final coincide, sin depender de la jerarquía de carpetas."""
    return [x for x in z.namelist() if PurePosixPath(x).name.lower() == nombre.lower()]


def miembros_por_patron(z: zipfile.ZipFile, patron: str) -> list[str]:
    rx = re.compile(patron, re.IGNORECASE)
    return [x for x in z.namelist() if rx.search(PurePosixPath(x).name)]


def leer_hashes_publicados(texto: str) -> dict[str, str]:
    """Lee los SHA-256 que la Registraduría publica dentro del paquete.

    Los manifiestos vienen en UTF-16 y con dos formas: una sola huella, o una lista de
    pares nombre/huella. Se cubren ambas.
    """
    pares = re.findall(r"Filename\s*:\s*([^\r\n]+?)\s*[\r\n].*?SHA-256\s*:\s*([0-9a-fA-F]{64})",
                       texto, flags=re.DOTALL)
    if pares:
        return {n.strip(): h.lower() for n, h in pares}
    suelta = re.search(r"SHA-256\s*:\s*([0-9a-fA-F]{64})", texto)
    return {"__unico__": suelta.group(1).lower()} if suelta else {}


def decodificar_manifiesto(datos: bytes) -> str:
    for cod in ("utf-16", "utf-16-le", "utf-8-sig", "cp1252"):
        try:
            texto = datos.decode(cod)
            if "SHA-256" in texto:
                return texto
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", "replace")


# --------------------------------------------------------------------- ancho fijo
def leer_ancho_fijo(datos: bytes, campos: list[tuple[str, int]], nombre: str,
                    codificacion: str = "cp1252") -> pd.DataFrame:
    """Lee un archivo de ancho fijo validando cada registro contra el esquema declarado.

    Si un registro no mide lo que debe, se detiene e informa el número de línea y la
    distribución de anchos observados: eso convierte un cambio silencioso de formato en
    un error visible, que es exactamente lo que se quiere.
    """
    ancho = sum(a for _, a in campos)
    lineas = datos.splitlines()
    anchos = Counter(len(l) for l in lineas)
    if set(anchos) != {ancho}:
        raise ValueError(
            f"{nombre}: se esperaban registros de {ancho} bytes. "
            f"Anchos observados: {dict(sorted(anchos.items()))}. "
            "Revisa el PDF de estructuras de este paquete antes de seguir."
        )
    filas = []
    for linea in lineas:
        cursor, fila = 0, {}
        for campo, largo in campos:
            fila[campo] = linea[cursor:cursor + largo].decode(codificacion).strip()
            cursor += largo
        filas.append(fila)
    return pd.DataFrame(filas, columns=[c for c, _ in campos])


def anchos_observados(datos: bytes, max_lineas: int = 200_000) -> dict[int, int]:
    """Distribución de anchos de registro. Sirve para diagnosticar antes de interpretar."""
    c = Counter()
    for i, linea in enumerate(datos.splitlines()):
        if i >= max_lineas:
            break
        c[len(linea)] += 1
    return dict(sorted(c.items()))


# --------------------------------------------------------------------- catálogos
class CatalogosMMV:
    """DIVIPOL, CANDIDATOS y PARTIDOS de un paquete, ya validados y cruzados.

    `codigo_municipio` no se recibe como parámetro: se **descubre** buscando el municipio
    por nombre dentro de DIVIPOL. El código electoral no es el código DANE y cambia entre
    paquetes, así que suponerlo es la vía más rápida a un resultado equivocado.
    """

    def __init__(self, divipol: pd.DataFrame, candidatos: pd.DataFrame,
                 partidos: dict[str, str], huellas: dict[str, str],
                 verificacion: list[dict]):
        self.divipol = divipol
        self.candidatos = candidatos
        self.partidos = partidos
        self.huellas = huellas
        self.verificacion = verificacion

        if divipol.duplicated(GEOCAMPOS).any():
            raise AssertionError("DIVIPOL trae puestos duplicados en depto/municipio/zona/puesto")

    # -------------------------------------------------- localización
    def localizar(self, municipio: str, departamento: str | None = None) -> dict:
        """Encuentra el código electoral del municipio y devuelve su catálogo de puestos."""
        d = self.divipol
        sel = d["municipio"].map(canon) == canon(municipio)
        if departamento:
            sel &= d["departamento"].map(canon) == canon(departamento)
        local = d.loc[sel].copy()
        if local.empty:
            cercanos = sorted({m for m in d["municipio"].map(canon).unique()
                               if canon(municipio)[:5] in m})[:10]
            raise AssertionError(
                f"DIVIPOL no contiene {municipio!r}"
                + (f" en {departamento}" if departamento else "")
                + (f". Nombres parecidos en el paquete: {cercanos}" if cercanos else "")
            )
        codigos = local[["cod_depto", "cod_municipio"]].drop_duplicates()
        if len(codigos) != 1:
            raise AssertionError(
                f"{municipio} aparece con más de un código en DIVIPOL: "
                f"{codigos.to_dict('records')}. Hay que desambiguar antes de filtrar."
            )
        cod_depto, cod_municipio = codigos.iloc[0].tolist()
        puestos = {tuple(r[c] for c in GEOCAMPOS): r for r in local.to_dict("records")}
        return {
            "cod_depto": cod_depto,
            "cod_municipio": cod_municipio,
            "puestos": puestos,
            "divipol_local": local,
            "n_puestos": len(local),
            "mesas_declaradas": int(pd.to_numeric(local["mesas_declaradas"],
                                                  errors="coerce").fillna(0).sum()),
            "potencial": int(pd.to_numeric(local["potencial_hombres"], errors="coerce").fillna(0).sum()
                             + pd.to_numeric(local["potencial_mujeres"], errors="coerce").fillna(0).sum()),
        }

    # -------------------------------------------------- candidaturas
    def indice_candidaturas(self) -> dict[tuple[str, str, str, str, str], dict]:
        """Candidaturas indexadas por corporación, territorio, partido y número de tarjetón.

        La llave necesita las cinco partes. La corporación, porque el candidato 001 del
        partido X al Concejo y el 001 del mismo partido a la Asamblea son personas
        distintas. Y el territorio, porque en un paquete departamental el candidato 001
        del partido X al Concejo de Barrancabermeja y el 001 del mismo partido al Concejo
        de Bucaramanga también lo son. Ignorar cualquiera de las dos mezcla personas.
        """
        idx = {}
        for r in self.candidatos.to_dict("records"):
            k = (r.get("cod_corporacion", ""), r.get("cod_depto", ""),
                 r.get("cod_municipio", ""), r["cod_partido"], r["cod_candidato"])
            if k in idx:
                raise AssertionError(
                    f"CANDIDATOS trae dos veces la misma candidatura: {k}. "
                    "El paquete es inconsistente; no se sigue."
                )
            idx[k] = r
        return idx

    def corporaciones_presentes(self) -> pd.DataFrame:
        if "cod_corporacion" not in self.candidatos.columns:
            return pd.DataFrame(columns=["cod_corporacion", "corporacion", "candidaturas"])
        t = (self.candidatos.groupby("cod_corporacion").size()
             .rename("candidaturas").reset_index())
        t["corporacion"] = t["cod_corporacion"].map(lambda c: CORPORACIONES.get(c, f"SIN_ETIQUETA_{c}"))
        return t[["cod_corporacion", "corporacion", "candidaturas"]]


def abrir_catalogos(ruta_zip: Path, verificar_huellas: bool = True) -> CatalogosMMV:
    """Extrae y valida DIVIPOL, CANDIDATOS y PARTIDOS de un paquete MMV.

    Los catálogos pueden venir directamente en el ZIP o dentro de un ARCHIVOSBASICOS
    anidado; se buscan en ambos lugares.
    """
    verificacion: list[dict] = []
    huellas: dict[str, str] = {}
    fuentes: list[tuple[str, zipfile.ZipFile]] = []
    abiertos: list[zipfile.ZipFile] = []

    z = zipfile.ZipFile(ruta_zip)
    abiertos.append(z)
    fuentes.append(("raiz", z))

    for nombre in miembros_por_patron(z, r"ARCHIVOSBASICOS.*\.zip$"):
        zz = zipfile.ZipFile(io.BytesIO(z.read(nombre)))
        abiertos.append(zz)
        fuentes.append((PurePosixPath(nombre).name, zz))

    def buscar(patron: str) -> tuple[str, zipfile.ZipFile, str] | None:
        for etiqueta, archivo in fuentes:
            hits = miembros_por_patron(archivo, patron)
            if len(hits) == 1:
                return etiqueta, archivo, hits[0]
            if len(hits) > 1:
                raise ValueError(f"{patron} aparece {len(hits)} veces en {etiqueta}: {hits}")
        return None

    try:
        ubic_div = buscar(r"^DIVIPOL")
        ubic_can = buscar(r"^CANDIDATOS")
        ubic_par = buscar(r"^PARTIDOS")
        faltan = [n for n, u in (("DIVIPOL", ubic_div), ("CANDIDATOS", ubic_can),
                                 ("PARTIDOS", ubic_par)) if u is None]
        if faltan:
            raise FileNotFoundError(
                f"El paquete {ruta_zip.name} no trae {', '.join(faltan)}. "
                f"Miembros disponibles: {[PurePosixPath(m).name for m in z.namelist()][:30]}"
            )

        # Huellas oficiales, cuando el paquete las publica.
        if verificar_huellas:
            for etiqueta, archivo in fuentes:
                for man in miembros_por_patron(archivo, r"^HASH.*\.txt$"):
                    publicadas = leer_hashes_publicados(decodificar_manifiesto(archivo.read(man)))
                    for nombre_decl, esperado in publicadas.items():
                        if nombre_decl == "__unico__":
                            continue
                        hits = miembros_por_nombre(archivo, nombre_decl)
                        if len(hits) != 1:
                            verificacion.append({"archivo": nombre_decl, "estado": "no_localizado",
                                                 "manifiesto": man})
                            continue
                        calculado = sha256_bytes(archivo.read(hits[0]))
                        coincide = calculado == esperado
                        huellas[nombre_decl] = calculado
                        verificacion.append({
                            "archivo": nombre_decl,
                            "estado": "coincide" if coincide else "NO_COINCIDE",
                            "manifiesto": man,
                            "sha256": calculado,
                        })
                        if not coincide:
                            raise AssertionError(
                                f"El SHA-256 de {nombre_decl} no coincide con el manifiesto "
                                f"oficial del paquete. No se sigue con un archivo alterado."
                            )

        divipol = leer_ancho_fijo(ubic_div[1].read(ubic_div[2]), DIVIPOL_CAMPOS, "DIVIPOL")
        candidatos = leer_ancho_fijo(ubic_can[1].read(ubic_can[2]), CANDIDATOS_CAMPOS, "CANDIDATOS")

        crudo = ubic_par[1].read(ubic_par[2]).splitlines()
        largos = Counter(len(x) for x in crudo)
        # El paquete piloto trae 206 bytes: 5 de código, 200 de nombre y un byte extra
        # no documentado. Se interpretan solo los campos descritos.
        if not largos or min(largos) < 5 + 1:
            raise ValueError(f"PARTIDOS con registros demasiado cortos: {dict(largos)}")
        partidos = {x[:5].decode("cp1252"): x[5:5 + ANCHO_PARTIDO_NOMBRE].decode("cp1252").strip()
                    for x in crudo}
        if len(partidos) != len(crudo):
            raise AssertionError("PARTIDOS trae códigos duplicados")

        cat = CatalogosMMV(divipol, candidatos, partidos, huellas, verificacion)
        cat.anchos_partidos = dict(sorted(largos.items()))
        cat.ubicaciones = {"DIVIPOL": ubic_div[2], "CANDIDATOS": ubic_can[2],
                           "PARTIDOS": ubic_par[2]}
        return cat
    finally:
        for a in abiertos:
            a.close()


# --------------------------------------------------------------------- votos
def _validar_numericos(fila: dict, tipo: str, numero: int) -> None:
    for campo in ("cod_depto", "cod_municipio", "mesa", "cod_partido", "cod_candidato", "votos"):
        if campo in fila and not fila[campo].isdigit():
            raise ValueError(f"{tipo}, registro {numero}: {campo}={fila[campo]!r} no es numérico")


def _normalizar_zona(zona: str, tipo: str, numero: int) -> str:
    """El escrutinio declara la zona en 3 posiciones y DIVIPOL en 2."""
    if len(zona) == 2:
        return zona
    if len(zona) == 3 and zona.startswith("0"):
        return zona[1:]
    raise ValueError(f"{tipo}, registro {numero}: zona {zona!r} sin equivalencia con DIVIPOL")


def leer_votos(ruta_zip: Path, miembro: str, tipo: str, cod_depto: str, cod_municipio: str,
               corporacion_fija: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Lee un archivo de votos y devuelve solo las filas del municipio pedido.

    `tipo` es `"preconteo"` (ancho fijo) o `"escrutinio"` (delimitado por `;`).
    El preconteo no trae corporación: en un paquete de una sola corporación se pasa en
    `corporacion_fija`; en uno territorial, el preconteo se queda sin ella y se marca
    así, en lugar de inventarla.
    """
    registros, total, descartes = [], 0, Counter()
    with zipfile.ZipFile(ruta_zip) as z:
        with z.open(miembro) as stream:
            for total, linea in enumerate(stream, start=1):
                reg = linea.rstrip(b"\r\n")
                if not reg:
                    descartes["linea_vacia"] += 1
                    continue
                if tipo == "preconteo":
                    if len(reg) != ANCHO_PRECONTEO:
                        # No se recorta ni se rellena: se devuelve lo observado para que
                        # el esquema se declare contra el PDF del paquete.
                        with zipfile.ZipFile(ruta_zip) as z2:
                            muestra = z2.read(miembro)[:200_000]
                        raise EstructuraDesconocida(
                            f"El preconteo de este paquete no usa el ancho documentado de "
                            f"{ANCHO_PRECONTEO} bytes (el registro {total} mide {len(reg)}). "
                            "Es de esperarse en una territorial: ese archivo incluye la "
                            "corporación, que el de presidencia no necesita. Hay que leer el "
                            "PDF de estructuras del paquete y declarar el esquema.",
                            {
                                "archivo": PurePosixPath(miembro).name,
                                "tipo": tipo,
                                "ancho_esperado": ANCHO_PRECONTEO,
                                "anchos_observados": anchos_observados(muestra),
                                "primeras_lineas": [
                                    l.decode("latin-1", "replace")
                                    for l in muestra.splitlines()[:3]
                                ],
                            },
                        )
                    fila, cursor = {}, 0
                    for campo, largo in PRECONTEO_CAMPOS:
                        fila[campo] = reg[cursor:cursor + largo].decode("ascii")
                        cursor += largo
                    fila["cod_corporacion"] = corporacion_fija or ""
                else:
                    campos = reg.decode("utf-8", "strict").split(";")
                    if len(campos) == len(ESCRUTINIO_CAMPOS) + 1 and campos[-1] == "":
                        campos = campos[:-1]
                    if len(campos) != len(ESCRUTINIO_CAMPOS):
                        raise EstructuraDesconocida(
                            f"El escrutinio de este paquete trae {len(campos)} campos en el "
                            f"registro {total}, no los {len(ESCRUTINIO_CAMPOS)} documentados. "
                            "Hay que leer el PDF de estructuras del paquete y declarar el "
                            "esquema antes de interpretarlo.",
                            {
                                "archivo": PurePosixPath(miembro).name,
                                "tipo": tipo,
                                "campos_esperados": len(ESCRUTINIO_CAMPOS),
                                "campos_observados": len(campos),
                                "primera_linea": reg[:300].decode("latin-1", "replace"),
                            },
                        )
                    fila = dict(zip(ESCRUTINIO_CAMPOS, campos))

                if (fila["cod_depto"], fila["cod_municipio"]) != (cod_depto, cod_municipio):
                    continue
                _validar_numericos(fila, tipo, total)
                fila["cod_zona"] = _normalizar_zona(fila["cod_zona"], tipo, total)
                fila["cod_partido"] = fila["cod_partido"].zfill(5)
                fila["cod_candidato"] = fila["cod_candidato"].zfill(3)
                fila["votos"] = int(fila["votos"])
                fila["tipo_resultado"] = tipo
                fila["archivo_origen"] = PurePosixPath(miembro).name
                registros.append(fila)

    datos = pd.DataFrame(registros)
    resumen = {
        "archivo": PurePosixPath(miembro).name,
        "tipo_resultado": tipo,
        "registros_paquete": total,
        "registros_municipio": len(datos),
        "votos_municipio": int(datos["votos"].sum()) if len(datos) else 0,
        "mesas_municipio": int(datos[CLAVE_MESA].drop_duplicates().shape[0]) if len(datos) else 0,
        "descartes": dict(descartes),
    }
    return datos, resumen


def enriquecer(datos: pd.DataFrame, cat: CatalogosMMV, local: dict) -> tuple[pd.DataFrame, dict]:
    """Agrega puesto, comuna, partido y candidato. Nunca escribe la cédula.

    Lo que no se puede etiquetar no se descarta ni se adivina: se marca en
    `clase_opcion` y queda contado en el informe. Un voto sin etiqueta sigue siendo un
    voto y debe cuadrar en los totales.
    """
    if datos.empty:
        return datos, {"sin_etiqueta": 0}

    idx = cat.indice_candidaturas()
    dep, mun = local["cod_depto"], local["cod_municipio"]

    # Las candidaturas a Gobernación y Asamblea son departamentales: en CANDIDATOS su
    # municipio viene en ceros o vacío, aunque los votos lleguen desde cada municipio.
    MUN_DEPARTAMENTAL = {"", "000", "00", "0"}

    municipales: dict[tuple[str, str, str], dict] = {}   # (corp, partido, cand)
    departamentales: dict[tuple[str, str, str], dict] = {}
    for (corp, d, m, part, cand), r in idx.items():
        if d != dep:
            continue
        if m == mun:
            municipales[(corp, part, cand)] = r
        elif m in MUN_DEPARTAMENTAL:
            departamentales[(corp, part, cand)] = r

    # Para el preconteo, que no declara corporación.
    sin_corp: dict[tuple[str, str], list[tuple[str, dict, str]]] = {}
    for tabla, ambito in ((municipales, "municipal"), (departamentales, "departamental")):
        for (corp, part, cand), r in tabla.items():
            sin_corp.setdefault((part, cand), []).append((corp, r, ambito))

    filas, conteo = [], Counter()
    for fila in datos.to_dict("records"):
        geo = tuple(fila[c] for c in GEOCAMPOS)
        puesto = local["puestos"].get(geo)
        if puesto is None:
            raise AssertionError(
                f"{fila['tipo_resultado']}: el puesto {geo} tiene votos pero no está en "
                "DIVIPOL. Es un problema del paquete, no del filtro; revísalo antes de seguir."
            )

        corp = fila.get("cod_corporacion", "")
        llave = (corp, fila["cod_partido"], fila["cod_candidato"])
        registro_cand, ambito = None, ""
        if corp:
            if llave in municipales:
                registro_cand, ambito = municipales[llave], "municipal"
            elif llave in departamentales:
                registro_cand, ambito = departamentales[llave], "departamental"
                conteo["candidatura_departamental"] += 1
        else:
            posibles = sin_corp.get((fila["cod_partido"], fila["cod_candidato"]), [])
            if len(posibles) == 1:
                corp, registro_cand, ambito = posibles[0]
                conteo["corporacion_inferida_unica"] += 1
            elif len(posibles) > 1:
                # Varias corporaciones comparten partido y número de tarjetón: no se
                # elige una. Queda sin corporación y el control lo marca.
                conteo["corporacion_ambigua"] += 1

        if registro_cand is not None:
            nombre = f"{registro_cand.get('nombre','')} {registro_cand.get('apellido','')}".strip()
            partido = cat.partidos.get(registro_cand["cod_partido"], "")
            genero = registro_cand.get("genero", "")
            clase = "candidatura_catalogada"
            conteo["catalogadas"] += 1
        elif fila["cod_candidato"] in OPCIONES_ESPECIALES:
            nombre, partido, genero = "", cat.partidos.get(fila["cod_partido"], ""), ""
            clase = "opcion_especial_sin_etiqueta"
            conteo["opciones_especiales"] += 1
        else:
            nombre, partido, genero = "", cat.partidos.get(fila["cod_partido"], ""), ""
            clase = "sin_equivalencia_en_catalogo"
            conteo["sin_etiqueta"] += 1

        filas.append({
            "tipo_resultado": fila["tipo_resultado"],
            "cod_depto": fila["cod_depto"], "departamento": puesto["departamento"],
            "cod_municipio": fila["cod_municipio"], "municipio": puesto["municipio"],
            "cod_zona": fila["cod_zona"], "cod_puesto": fila["cod_puesto"],
            "puesto": puesto["puesto"], "mesa": fila["mesa"],
            "cod_comuna_divipol": puesto.get("cod_comuna_divipol", ""),
            "comuna_divipol": puesto.get("comuna_divipol", ""),
            "cod_comuna_escrutinio": fila.get("cod_comuna_escrutinio", ""),
            "cod_corporacion": corp,
            "corporacion": CORPORACIONES.get(corp, f"SIN_ETIQUETA_{corp}" if corp else "SIN_CORPORACION"),
            "cod_circunscripcion": fila.get("cod_circunscripcion", ""),
            "cod_partido": fila["cod_partido"], "partido": partido,
            "cod_candidato": fila["cod_candidato"], "candidato": nombre,
            "genero_candidato": genero,
            "ambito_candidatura": ambito,
            "clase_opcion": clase,
            "votos": fila["votos"],
            "archivo_origen": fila["archivo_origen"],
        })

    salida = pd.DataFrame(filas)
    # La cédula se lee para cruzar catálogos, pero no viaja a ninguna tabla escrita.
    assert "cedula" not in salida.columns, "La cédula no debe salir del módulo"
    return salida, dict(conteo)


# --------------------------------------------------------------------- controles
def controles(datos: pd.DataFrame, local: dict, etiqueta: str) -> pd.DataFrame:
    """Controles mínimos de una tabla de votos ya enriquecida."""
    filas = []

    def chequeo(nombre, valor, esperado, pasa, criticidad="Media"):
        filas.append({"tabla": etiqueta, "control": nombre, "valor": valor,
                      "esperado": esperado, "criticidad": criticidad, "pasa": bool(pasa)})

    if datos.empty:
        chequeo("tabla no vacía", 0, "> 0 filas", False, "Alta")
        return pd.DataFrame(filas)

    dup = int(datos.duplicated(CLAVE_VOTO).sum())
    chequeo("llave mesa/corporación/partido/candidato única", dup, "0 duplicados", dup == 0, "Alta")

    neg = int((datos["votos"] < 0).sum())
    chequeo("votos no negativos", neg, "0 registros", neg == 0, "Alta")

    mesas = int(datos[CLAVE_MESA].drop_duplicates().shape[0])
    chequeo("mesas con votos vs mesas declaradas en DIVIPOL",
            f"{mesas} / {local['mesas_declaradas']}",
            "mesas con votos <= declaradas",
            mesas <= local["mesas_declaradas"], "Alta")

    puestos = int(datos[GEOCAMPOS].drop_duplicates().shape[0])
    chequeo("puestos cubiertos", f"{puestos} / {local['n_puestos']}",
            "informativo", True, "Baja")

    sin_etiqueta = int((datos["clase_opcion"] == "sin_equivalencia_en_catalogo").sum())
    chequeo("opciones sin equivalencia en el catálogo", sin_etiqueta, "0 registros",
            sin_etiqueta == 0, "Alta")

    sin_corp = int((datos["cod_corporacion"] == "").sum())
    chequeo("registros sin corporación asignada", sin_corp, "0 registros", sin_corp == 0, "Media")

    total = int(datos["votos"].sum())
    chequeo("votos totales vs potencial de sufragantes", f"{total} / {local['potencial']}",
            "votos <= potencial", total <= local["potencial"], "Alta")

    return pd.DataFrame(filas)


def comparar_preconteo_escrutinio(pre: pd.DataFrame, esc: pd.DataFrame) -> pd.DataFrame:
    """Compara los dos conteos **sin fusionarlos**.

    El preconteo es un informe de la jornada y el escrutinio es el resultado jurídico.
    Que difieran es normal y no es indicio de nada por sí mismo: el escrutinio corrige
    errores de transcripción y resuelve reclamaciones. Se comparan para documentar la
    diferencia, nunca para reemplazar un conteo con el otro.
    """
    if pre.empty or esc.empty:
        return pd.DataFrame(columns=CLAVE_MESA + ["votos_preconteo", "votos_escrutinio", "diferencia"])
    a = pre.groupby(CLAVE_MESA, as_index=False)["votos"].sum().rename(columns={"votos": "votos_preconteo"})
    b = esc.groupby(CLAVE_MESA, as_index=False)["votos"].sum().rename(columns={"votos": "votos_escrutinio"})
    t = a.merge(b, on=CLAVE_MESA, how="outer").fillna({"votos_preconteo": 0, "votos_escrutinio": 0})
    t["diferencia"] = t["votos_escrutinio"].astype(int) - t["votos_preconteo"].astype(int)
    return t.sort_values("diferencia", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
