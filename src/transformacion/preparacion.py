# -*- coding: utf-8 -*-
"""Preprocesamiento: de las tablas de ingesta a los datasets analíticos.

Este módulo toma lo que dejó la ingesta y produce las tablas con las que se va a
analizar. No descubre datos nuevos: resuelve los problemas que impedirían usar los que ya
hay. Son cuatro, y conviene saber cuáles antes de leer el código.

**1. Los códigos no tienen el mismo ancho entre años.** `cod_candidato` viene con 3
dígitos en Congreso 2022 y con 5 en las territoriales; `cod_partido` con 4 y con 5;
`mesa` con 4 y con 1 o 2. Un `groupby` o un `merge` entre años sobre esas columnas
partiría cada grupo en dos sin avisar. Todos los códigos se rellenan a un ancho fijo.

**2. Hay texto centinela que pandas convierte en nulo en silencio.** Las tablas de 2019
traen la cadena `NULL` y las de 2022 `N/A` en la columna de comuna, y `N/A` en la de
partido para los votos en blanco y nulos. `pd.read_csv` con sus opciones por omisión los
vuelve `NaN`, y entonces un conteo de nulos reporta datos faltantes donde hay un valor.
Aquí se leen como texto y se convierten a nulo **explícitamente**, dejando constancia.

**3. `cod_puesto` NO identifica el mismo lugar entre años.** Esto es lo importante. Entre
2019 y 2023 hay 14 puestos renumerados: la zona 01 puesto 04 era `COL. INTECOBA - D` en
2019 y en 2023 es `INSTITUTO ANTONIO NARIÑO`, mientras el Intecoba pasó al puesto 05.
Un panel construido sobre ese código compararía lugares distintos y produciría una
volatilidad territorial que sería un artefacto de la llave.

Se verificó por tres vías. El rastreo de nombres: en 16 de 26 pares el nombre de 2019
aparece en 2023 con otro código y similitud 1,00. El emparejamiento: 49 puestos existen
en los dos años y solo 35 conservan el código, mientras los 49 conservan la **zona**. Y
el censo, que es otra fuente: donde el nombre coincide el potencial electoral cambia una
mediana de +0,6 % entre 2019 y 2023, lo esperable para el mismo lugar; donde el nombre
difiere cambia +17,1 %, con extremos de −86,6 % y +847,2 %.

Por eso la identidad de panel se construye emparejando **nombres dentro de la zona**, y
los puestos que no emparejan quedan declarados como tales en vez de forzarse.

**4. La zona 98 es la cárcel, no un consolidado.** Tiene `cod_comuna = '00'` y la columna
de comuna dice `NULL` en 2019, `N/A` en 2022 y `NACIONAL` en 2023. No es una fila de
totales: es un puesto de votación real con censo propio, 149 electores y entre 56 y 109
votos. Se conserva, marcado como ámbito especial. La zona 99 agrupa los puestos rurales.

**Lo que este módulo no hace.** No imputa. Un potencial que falta queda vacío; una comuna
que falta queda vacía. Los valores extremos se marcan en una columna, nunca se borran ni
se recortan. Y ningún documento de identidad entra a ninguna tabla: la ingesta ya los
excluyó y aquí no se vuelven a pedir.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- configuración

# Ancho al que se rellena cada código. Es el máximo observado en las fuentes: rellenar
# al máximo nunca pierde información, mientras recortar al mínimo sí podría.
ANCHOS = {
    "cod_depto": 2, "cod_municipio": 3, "cod_zona": 2, "cod_puesto": 2,
    "mesa": 4, "cod_corporacion": 3, "cod_partido": 5, "cod_candidato": 5,
    "cod_circunscripcion": 2, "cod_comuna": 2,
}

# Texto que las fuentes usan para decir "no hay valor". Se convierte a nulo de forma
# explícita y se cuenta, en vez de dejar que el lector de CSV lo haga por su cuenta.
CENTINELAS = {"NULL", "N/A", "NA", "NAN", "NONE", "SIN DATO", "#N/A", "NULO", "-"}

# Las tres opciones que no son una candidatura. Verificado idéntico en las 12 tablas.
OPCIONES_ESPECIALES = {
    "00996": ("blanco", "VOTOS EN BLANCO"),
    "00997": ("nulo", "VOTOS NULOS"),
    "00998": ("no_marcado", "VOTOS NO MARCADOS"),
}

# Nombre canónico de cada territorio. Las fuentes escriben el mismo corregimiento de
# varias formas —`CORREG.`, `CORRE.`, `CORREG`— y a veces con el código pegado delante.
TERRITORIOS = {
    "01": ("COMUNA 1", "urbano"),
    "02": ("COMUNA 2", "urbano"),
    "03": ("COMUNA 3", "urbano"),
    "04": ("COMUNA 4", "urbano"),
    "05": ("COMUNA 5", "urbano"),
    "06": ("COMUNA 6", "urbano"),
    "07": ("COMUNA 7", "urbano"),
    "08": ("CORREGIMIENTO EL CENTRO", "rural"),
    "09": ("CORREGIMIENTO EL LLANITO", "rural"),
    "10": ("CORREGIMIENTO LA FORTUNA AUTOPISTA", "rural"),
    "11": ("CORREGIMIENTO MESETA DE SAN RAFAEL", "rural"),
    "12": ("CORREGIMIENTO SAN RAFAEL DE CHUCURI", "rural"),
    "13": ("CORREGIMIENTO CIENAGA DEL OPON", "rural"),
    "00": ("CARCEL", "especial"),
}

ZONA_CARCEL = "98"
ZONA_RURAL = "99"

# Qué censo corresponde a qué corporación. Igual que en `src/analisis/participacion.py`:
# un año puede traer dos elecciones y cada una tiene su propio potencial.
CENSO_DE = {
    "ALCALDE": "AUTORIDADES TERRITORIALES", "CONCEJO": "AUTORIDADES TERRITORIALES",
    "ASAMBLEA": "AUTORIDADES TERRITORIALES", "GOBERNADOR": "AUTORIDADES TERRITORIALES",
    "JAL": "AUTORIDADES TERRITORIALES", "SENADO": "CONGRESO DE LA REPUBLICA",
    "CAMARA": "CONGRESO DE LA REPUBLICA", "PRESIDENTE": "PRESIDENTE DE LA REPUBLICA",
}

# Corporaciones uninominales: no hay listas ni voto de lista, y la cifra repartidora no
# aplica. Separarlas evita calcular indicadores de lista donde no existen.
UNINOMINALES = {"ALCALDE", "GOBERNADOR", "PRESIDENTE"}

ABREVIATURAS = {
    "COL": "COLEGIO", "COLE": "COLEGIO", "ESC": "ESCUELA", "ESCU": "ESCUELA",
    "INST": "INSTITUTO", "INS": "INSTITUTO", "INSTIT": "INSTITUTO",
    "IE": "INSTITUCION EDUCATIVA", "SD": "SEDE", "SED": "SEDE",
    "HDEZ": "HERNANDEZ", "TEC": "TECNICO", "TECN": "TECNICO",
    "SEM": "SEMINARIO", "EDUC": "EDUCATIVO", "CTRO": "CENTRO",
    "NTRA": "NUESTRA", "NTRO": "NUESTRO", "SRA": "SENORA", "STA": "SANTA",
    "STO": "SANTO", "NAL": "NACIONAL", "MPAL": "MUNICIPAL",
    "DPTAL": "DEPARTAMENTAL", "UNIV": "UNIVERSIDAD", "AGROP": "AGROPECUARIO",
    "RESTR": "RESTREPO", "CONC": "CONCENTRACION", "POLIDEP": "POLIDEPORTIVO",
    "MEGACOL": "MEGACOLEGIO", "CGTO": "CORREGIMIENTO", "CORREG": "CORREGIMIENTO",
    "CORRE": "CORREGIMIENTO",
}

VACIAS = {"DE", "DEL", "LA", "EL", "LOS", "LAS", "Y", "SEDE", "COLEGIO", "ESCUELA",
          "INSTITUCION", "EDUCATIVA", "EDUCATIVO", "INSTITUTO", "CENTRO", "PUESTO",
          "VOTACION", "CORREGIMIENTO"}

UMBRAL_PANEL = 0.6


class DatosInconsistentes(Exception):
    """Algo que no se puede arreglar sin decidir por la fuente. Detiene el proceso."""


# ------------------------------------------------------------------- nombres

def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Za-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip().upper()


def expandir(nombre) -> str:
    """Desarma abreviaturas para poder comparar nombres escritos de formas distintas.

    Primero pega las letras sueltas consecutivas, porque `I.E.` queda como `I E` al
    quitar los puntos y se perdería `INSTITUCION EDUCATIVA`. Después traduce palabra por
    palabra.
    """
    t = canon(nombre)
    t = re.sub(r"\b([A-Z])(?:\s+([A-Z])\b)+",
               lambda m: m.group(0).replace(" ", ""), t)
    return " ".join(ABREVIATURAS.get(p, p) for p in t.split())


def _tokens_de(expandido: str) -> set:
    out = {p for p in expandido.split() if p not in VACIAS and len(p) > 2}
    for letra in re.findall(r"\bSEDE\s+([A-Z0-9])\b", expandido):
        out.add("SEDE" + letra)
    return out


def tokens(nombre) -> set:
    """Palabras que de verdad distinguen un puesto de otro.

    `COLEGIO`, `SEDE` o `ESCUELA` aparecen en casi todos los nombres y no distinguen
    nada. La letra de la sede sí: `SEDE A` y `SEDE B` del mismo colegio son dos puestos.
    """
    return _tokens_de(expandir(nombre))


def _emparejan(x: str, y: str) -> bool:
    """Si dos palabras se refieren a lo mismo pese a estar escritas distinto.

    Dos casos reales de estas tablas. Palabras pegadas: `TECINDUSTRIAL` contiene
    `INDUSTRIAL`. Y palabras cortadas: la fuente trunca el nombre del puesto y deja
    `PAL` donde iba `PALMAR`.

    Los mínimos de longitud evitan los falsos positivos obvios: `SAN` no debe emparejar
    con `SANTA`, ni `COL` con `COLOMBIA`.
    """
    if x == y:
        return True
    corto, largo = sorted((x, y), key=len)
    if len(corto) >= 4 and largo.startswith(corto):
        return True
    if len(corto) >= 6 and corto in largo:
        return True
    return False


def _parecido_de_tokens(ta: set, tb: set) -> float:
    if not ta or not tb:
        return 0.0
    libres = set(tb)
    comunes = 0
    for x in sorted(ta):
        for y in sorted(libres):
            if _emparejan(x, y):
                comunes += 1
                libres.discard(y)
                break
    if not comunes:
        return 0.0
    return comunes / (len(ta) + len(tb) - comunes)


def similitud(a, b) -> float:
    """Parecido de 0 a 1 entre dos nombres, contando solo palabras distintivas.

    Además del parecido directo se prueba una variante **truncada**: las fuentes cortan
    el nombre del puesto a un largo fijo, de modo que `COL EL CASTILLO SEDE D (EL PAL` y
    `COL EL CASTILLO SEDE D  EL PALMAR` son el mismo lugar con el nombre cortado. Para
    compararlos se recortan los dos al largo del más corto. La variante solo se considera
    cuando el nombre corto ya tiene veinte caracteres, para no emparejar fragmentos.
    """
    ea, eb = expandir(a), expandir(b)
    directo = _parecido_de_tokens(_tokens_de(ea), _tokens_de(eb))

    n = min(len(ea), len(eb))
    if n >= 20 and abs(len(ea) - len(eb)) >= 2:
        truncado = _parecido_de_tokens(_tokens_de(ea[:n]), _tokens_de(eb[:n]))
        return max(directo, truncado)
    return directo


def huella(*partes) -> str:
    """Identificador corto y determinista. No contiene datos personales."""
    semilla = "|".join(str(p) for p in partes)
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------- lectura

def leer_csv(ruta) -> pd.DataFrame:
    """Lee un CSV del proyecto sin que el lector invente nulos.

    `keep_default_na=False` es la parte importante: sin eso, `pd.read_csv` convierte la
    cadena `NULL` y la cadena `N/A` en `NaN`, y esas dos cadenas **son valores** en estas
    tablas. Quedan como texto y la conversión a nulo se hace aparte, contándola.
    """
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""])


def normalizar_centinelas(datos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convierte el texto centinela en nulo de verdad y deja el recuento."""
    d = datos.copy()
    filas = []
    for c in d.columns:
        # No se compara `dtype` contra `object`: en pandas 3 una columna de texto puede
        # llegar con dtype `str` y la comparación la dejaría fuera, de modo que el
        # detector quedaría inerte sin fallar. Se pregunta por la capacidad, no por el tipo.
        if not (pd.api.types.is_object_dtype(d[c])
                or pd.api.types.is_string_dtype(d[c])):
            continue
        v = d[c].astype(str).str.strip().str.upper()
        # `& d[c].notna()` importa: `astype(str)` convierte un nulo real en la cadena
        # `'nan'`, que está en la lista de centinelas. Sin este filtro el informe diría
        # que hay 1 683 celdas con el texto `nan` donde en realidad no había nada.
        m = v.isin(CENTINELAS) & d[c].notna()
        n = int(m.sum())
        if n:
            filas.append({"columna": c, "texto_centinela": ", ".join(
                sorted(set(d.loc[m, c].astype(str)))), "filas": n})
            d.loc[m, c] = None
    return d, pd.DataFrame(filas, columns=["columna", "texto_centinela", "filas"])


def normalizar_codigos(datos: pd.DataFrame) -> pd.DataFrame:
    """Rellena cada código al ancho fijo declarado en `ANCHOS`.

    Sin esto, `'996'` de Congreso y `'00996'` de las territoriales serían dos valores
    distintos para la misma opción, y cualquier agrupación entre años quedaría partida.
    """
    d = datos.copy()
    for c, ancho in ANCHOS.items():
        if c in d.columns:
            s = d[c].astype(str).str.strip()
            s = s.where(d[c].notna(), None)
            d[c] = s.str.zfill(ancho).where(s.notna(), None)
    return d


# ------------------------------------------------------------------ territorio

def clasificar_territorio(cod_zona, cod_comuna) -> tuple[str, str, str]:
    """Devuelve (territorio, ambito, origen_del_ambito) para un puesto.

    La zona resuelve casos que la comuna no. En Congreso 2022 seis puestos rurales
    llegaron sin `cod_comuna`, pero todos están en la zona 99, que es la zona rural en
    los tres años. De ahí se puede afirmar el **ámbito** rural sin inventar *cuál*
    corregimiento: el territorio queda vacío y el ámbito queda lleno, y la columna
    `origen_del_ambito` dice de dónde salió cada uno.
    """
    z = str(cod_zona) if cod_zona is not None and pd.notna(cod_zona) else ""
    c = str(cod_comuna) if cod_comuna is not None and pd.notna(cod_comuna) else ""

    if z == ZONA_CARCEL:
        return ("CARCEL", "especial", "zona 98 es la carcel")
    if c in TERRITORIOS and c != "00":
        nombre, ambito = TERRITORIOS[c]
        return (nombre, ambito, "cod_comuna")
    if c == "00":
        return ("CARCEL", "especial", "cod_comuna 00")
    if z == ZONA_RURAL:
        return ("", "rural", "zona 99 es rural; falta el corregimiento")
    return ("", "sin_dato", "sin cod_comuna y sin zona que lo resuelva")


def tabla_de_territorios(puestos: pd.DataFrame,
                         areas: pd.DataFrame | None = None) -> pd.DataFrame:
    """Dimensión de territorios: nombre canónico, ámbito, puestos y área."""
    filas = []
    for cod, (nombre, ambito) in sorted(TERRITORIOS.items()):
        sub = puestos[puestos["territorio"] == nombre]
        filas.append({
            "cod_comuna": cod, "territorio": nombre, "ambito": ambito,
            "puestos_observados": int(sub["id_puesto"].nunique()) if len(sub) else 0,
        })
    t = pd.DataFrame(filas)
    if areas is not None and len(areas):
        t = t.merge(areas, on="cod_comuna", how="left")
    return t


# ------------------------------------------------------- opciones de la tarjeta

def marcar_opciones(datos: pd.DataFrame) -> pd.DataFrame:
    """Añade `tipo_opcion`, que dice qué es cada fila de la tarjeta electoral.

    Cinco valores: `candidato`, `lista` (voto por el partido sin marcar candidato),
    `blanco`, `nulo` y `no_marcado`. Hace falta porque la columna `clase_opcion` que
    traía la ingesta agrupa los tres últimos en `opcion_especial`, y los tres se cuentan
    de forma distinta: el blanco **es** un voto válido, el nulo y el no marcado no.

    Hay una trampa en los datos que esto también resuelve. En las filas de voto de lista,
    la columna `candidato` **no trae un candidato: trae el nombre del partido** y
    `cod_candidato` es `00000`. Cualquier conteo de candidatos distintos que no las
    excluya saldría inflado.
    """
    d = datos.copy()
    cod = d["cod_candidato"].astype(str)

    d["tipo_opcion"] = "candidato"
    d.loc[d["clase_opcion"] == "voto_de_lista_no_preferente", "tipo_opcion"] = "lista"
    for codigo, (etiqueta, _) in OPCIONES_ESPECIALES.items():
        d.loc[cod == codigo, "tipo_opcion"] = etiqueta

    # El blanco es válido; el nulo y el no marcado no. El voto de lista sí es válido.
    d["es_voto_valido"] = ~d["tipo_opcion"].isin(["nulo", "no_marcado"])
    # El nombre de candidato solo es un candidato cuando la fila es una candidatura.
    d["nombre_candidato"] = d["candidato"].where(d["tipo_opcion"] == "candidato", None)
    d["nombre_partido"] = d["partido"].where(
        d["tipo_opcion"].isin(["candidato", "lista"]), None)
    return d


# ------------------------------------------------------------- tabla unificada

ESQUEMA_LARGO = [
    "anio", "familia", "corporacion", "cod_corporacion", "es_uninominal",
    "cod_circunscripcion", "cod_zona", "cod_puesto", "puesto", "id_puesto", "mesa",
    "cod_comuna", "territorio", "ambito", "origen_del_ambito",
    "cod_partido", "nombre_partido", "cod_candidato", "nombre_candidato",
    "tipo_opcion", "es_voto_valido", "votos", "id_fuente", "archivo_origen",
    "tipo_resultado",
]


def unificar(tablas: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Une las tablas de todas las elecciones en una sola, con esquema común.

    Las familias no traen las mismas columnas: Congreso 2022 tiene `citrep` y el nombre
    de la circunscripción, las territoriales no. En vez de llenar lo que falta con vacíos
    y dejar un esquema distinto según el año, se declara un esquema común y lo que sobra
    se descarta aquí, quedando disponible en las tablas de ingesta para quien lo necesite.
    """
    partes = []
    informe = []
    for etiqueta, bruto in sorted(tablas.items()):
        d, centinelas = normalizar_centinelas(bruto)
        d = normalizar_codigos(d)
        d = marcar_opciones(d)

        terr = [clasificar_territorio(z, c)
                for z, c in zip(d["cod_zona"], d.get("cod_comuna", pd.Series(dtype=str)))]
        d["territorio"] = [t[0] for t in terr]
        d["ambito"] = [t[1] for t in terr]
        d["origen_del_ambito"] = [t[2] for t in terr]

        d["votos"] = pd.to_numeric(d["votos"], errors="coerce")
        d["es_uninominal"] = d["corporacion"].isin(UNINOMINALES)

        faltan = [c for c in ESQUEMA_LARGO if c not in d.columns]
        for c in faltan:
            d[c] = None

        informe.append({
            "eleccion": etiqueta,
            "filas": int(len(d)),
            "puestos": int(d["id_puesto"].nunique()),
            "mesas": int(d.groupby(["id_puesto", "mesa"]).ngroups),
            "votos": int(d["votos"].sum()),
            "columnas_descartadas": ", ".join(
                sorted(set(bruto.columns) - set(ESQUEMA_LARGO))),
            "columnas_ausentes_rellenadas": ", ".join(faltan),
            "texto_centinela": "; ".join(
                f"{r.columna}={r.texto_centinela}({r.filas})"
                for r in centinelas.itertuples()) if len(centinelas) else "",
            "votos_nulos_al_convertir": int(d["votos"].isna().sum()),
        })
        partes.append(d[ESQUEMA_LARGO])

    larga = pd.concat(partes, ignore_index=True)
    return larga, pd.DataFrame(informe)


# ------------------------------------------------------- identidad de panel

def construir_panel(larga: pd.DataFrame,
                    anio_referencia: str | None = None,
                    umbral: float = UMBRAL_PANEL) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Asigna a cada puesto una identidad estable entre años: `id_panel`.

    **Por qué no se usa `cod_puesto`.** Está renumerado entre años: el mismo código
    apunta a lugares distintos, y la verificación está en el encabezado del módulo. Lo
    que sí es estable es la **zona**: los 49 puestos que existen en 2019 y en 2023 están
    los 49 en la misma zona.

    Así que se empareja por nombre **dentro de la zona**, contra el año más reciente, que
    es el que tiene más puestos. El emparejamiento es codicioso y exclusivo: un puesto de
    referencia se usa una sola vez, de modo que dos puestos de otro año no pueden
    reclamar el mismo.

    Lo que no empareja **no se fuerza**. Recibe su propia identidad y queda con
    `en_panel = False`, porque un puesto que aparece solo en un año es un dato correcto
    —se abrió o se cerró— y no un error que haya que resolver.
    """
    pst = (larga.drop_duplicates(["anio", "cod_zona", "cod_puesto", "puesto"])
           [["anio", "cod_zona", "cod_puesto", "puesto", "id_puesto",
             "cod_comuna", "territorio", "ambito"]]
           .copy())
    # Un año puede traer el mismo puesto en varias corporaciones; basta una vez.
    pst = pst.drop_duplicates(["anio", "cod_zona", "puesto"]).reset_index(drop=True)

    anios = sorted(set(pst["anio"]))
    if anio_referencia is None:
        conteo = pst.groupby("anio")["puesto"].size()
        anio_referencia = str(conteo.idxmax())

    ref = pst[pst["anio"] == anio_referencia].copy()
    ref["id_panel"] = [huella("panel", z, expandir(p))
                       for z, p in zip(ref["cod_zona"], ref["puesto"])]
    ref["parecido_con_referencia"] = 1.0
    ref["emparejado_contra"] = ref["puesto"]

    resultado = [ref]
    informe = []

    for anio in anios:
        if anio == anio_referencia:
            informe.append({"anio": anio, "puestos": int(len(ref)),
                            "emparejados": int(len(ref)),
                            "sin_emparejar": 0, "es_referencia": True})
            continue

        otros = pst[pst["anio"] == anio].copy()
        usados = set()
        ids, puntajes, contra = [], [], []

        # Se ordena por el mejor parecido disponible para que los emparejamientos
        # claros se resuelvan antes que los dudosos y no les quiten el candidato.
        candidatos = []
        for i, r in otros.iterrows():
            misma_zona = ref[ref["cod_zona"] == r["cod_zona"]]
            for j, q in misma_zona.iterrows():
                s = similitud(r["puesto"], q["puesto"])
                if s >= umbral:
                    candidatos.append((s, i, j))
        candidatos.sort(key=lambda x: -x[0])

        asignado = {}
        for s, i, j in candidatos:
            if i in asignado or j in usados:
                continue
            asignado[i] = (j, s)
            usados.add(j)

        for i, r in otros.iterrows():
            if i in asignado:
                j, s = asignado[i]
                ids.append(ref.loc[j, "id_panel"])
                puntajes.append(round(s, 3))
                contra.append(ref.loc[j, "puesto"])
            else:
                ids.append(huella("panel", r["cod_zona"], expandir(r["puesto"])))
                puntajes.append(0.0)
                contra.append("")

        otros["id_panel"] = ids
        otros["parecido_con_referencia"] = puntajes
        otros["emparejado_contra"] = contra
        resultado.append(otros)
        informe.append({"anio": anio, "puestos": int(len(otros)),
                        "emparejados": int(len(asignado)),
                        "sin_emparejar": int(len(otros) - len(asignado)),
                        "es_referencia": False})

    panel = pd.concat(resultado, ignore_index=True)

    # Un puesto está "en el panel" si su identidad aparece en más de un año.
    presencia = panel.groupby("id_panel")["anio"].nunique()
    panel["anios_presentes"] = panel["id_panel"].map(presencia)
    panel["en_panel"] = panel["anios_presentes"] > 1
    panel["en_panel_completo"] = panel["anios_presentes"] == len(anios)

    return (panel.sort_values(["id_panel", "anio"]).reset_index(drop=True),
            pd.DataFrame(informe))


# --------------------------------------------------- tabla puesto × elección

VACIO = "__VACIO__"


def _llave_de_texto(datos: pd.DataFrame, columnas: list) -> pd.Series:
    """Pega varias columnas en una sola cadena, tratando el nulo de forma explícita.

    **Aquí hay una trampa que cuesta la mitad de los datos.** En pandas 3, `astype(str)`
    sobre una columna con nulos devuelve una columna de texto que **conserva el nulo**, y
    al concatenar con `+` ese nulo se propaga a toda la cadena. Después `groupby`
    descarta los grupos con llave nula y los votos de esas filas desaparecen sin ningún
    error. En pandas 2 el nulo se habría vuelto la cadena `'nan'` y no habría pasado
    nada: el mismo código da resultados distintos según la versión instalada.

    Por eso el nulo se reemplaza por un marcador antes de convertir a texto. Ninguna
    columna de la llave se queda en nulo, y la columna original no se modifica.
    """
    partes = []
    for c in columnas:
        s = datos[c]
        partes.append(s.astype("object").where(s.notna(), VACIO).astype(str))
    clave = partes[0]
    for p in partes[1:]:
        clave = clave + "|" + p
    if clave.isna().any():
        raise DatosInconsistentes(
            "La llave de agrupación quedó con nulos, lo que haría desaparecer filas "
            "en silencio. Revisa las columnas: " + ", ".join(columnas))
    return clave


def desglose_por_puesto(larga: pd.DataFrame) -> pd.DataFrame:
    """Una fila por puesto y elección, con el desglose completo de la votación.

    Es la tabla principal del análisis. El desglose cumple una identidad que se verifica
    después: válidos + nulos + no marcados = depositados. Los votos en blanco entran en
    los válidos, que es como los cuenta la ley para la cifra repartidora.
    """
    d = larga.copy()
    d["votos"] = pd.to_numeric(d["votos"], errors="coerce").fillna(0)

    llave = ["anio", "familia", "corporacion", "es_uninominal", "cod_zona",
             "cod_puesto", "puesto", "id_puesto", "cod_comuna", "territorio",
             "ambito", "origen_del_ambito"]

    # **Nada de `pivot_table` aquí.** Con una llave de doce columnas y `dropna=False`,
    # pandas construye el producto cartesiano de todos los niveles del índice antes de
    # llenarlo: con estos datos pide 2 TB de memoria y se cae. Se agrega por una llave
    # sustituta de texto, que además trata los nulos de forma consistente —un `merge`
    # sobre columnas con nulos es terreno resbaloso— y las columnas de la llave se
    # recuperan al final una sola vez.
    d["_k"] = _llave_de_texto(d, llave)
    mapa = d.drop_duplicates("_k")[["_k"] + llave].reset_index(drop=True)

    base = d.groupby("_k", as_index=False).agg(
        votos_depositados=("votos", "sum"),
        mesas=("mesa", "nunique"),
        filas_en_la_fuente=("votos", "size"))

    columnas = {"candidato": "votos_a_candidatos", "lista": "votos_de_lista",
                "blanco": "votos_blanco", "nulo": "votos_nulos",
                "no_marcado": "votos_no_marcados"}
    for tipo, nombre in columnas.items():
        sub = (d[d["tipo_opcion"] == tipo].groupby("_k", as_index=False)["votos"]
               .sum().rename(columns={"votos": nombre}))
        base = base.merge(sub, on="_k", how="left")
        base[nombre] = base[nombre].fillna(0)

    t = mapa.merge(base, on="_k", how="left")
    t["votos_validos"] = (t["votos_a_candidatos"] + t["votos_de_lista"]
                          + t["votos_blanco"])
    t["votos_no_validos"] = t["votos_nulos"] + t["votos_no_marcados"]

    # Candidatos y listas distintas con al menos un voto en ese puesto.
    #
    # **`cod_candidato` NO identifica a un candidato por sí solo.** Es el número de orden
    # dentro de su lista: el candidato 00001 del Partido A y el 00001 del Partido B son
    # dos personas. Contar solo ese código colapsa todas las listas en una y devuelve el
    # tamaño de la lista más larga en lugar del número de candidatos. En el Concejo eso
    # daba 17 —el número de curules, por coincidencia— cuando los candidatos reales son
    # 275 en 2019 y 359 en 2023. La identidad de una candidatura es el par lista más
    # número de orden.
    cands = d[(d["tipo_opcion"] == "candidato") & (d["votos"] > 0)].copy()
    if len(cands):
        cands["_cand"] = _llave_de_texto(cands, ["cod_partido", "cod_candidato"])
        cand = (cands.groupby("_k", as_index=False)
                .agg(candidatos_con_voto=("_cand", "nunique"),
                     listas_con_voto=("cod_partido", "nunique")))
    else:
        cand = pd.DataFrame(columns=["_k", "candidatos_con_voto", "listas_con_voto"])
    t = t.merge(cand, on="_k", how="left")
    t["candidatos_con_voto"] = t["candidatos_con_voto"].fillna(0).astype(int)
    t["listas_con_voto"] = t["listas_con_voto"].fillna(0).astype(int)

    for c, sobre in (("pct_validos", "votos_depositados"),
                     ("pct_blanco", "votos_depositados"),
                     ("pct_nulos", "votos_depositados"),
                     ("pct_no_marcados", "votos_depositados")):
        origen = {"pct_validos": "votos_validos", "pct_blanco": "votos_blanco",
                  "pct_nulos": "votos_nulos",
                  "pct_no_marcados": "votos_no_marcados"}[c]
        t[c] = (t[origen] / t[sobre] * 100).round(2)
    t["pct_blanco_sobre_validos"] = (t["votos_blanco"] / t["votos_validos"]
                                     * 100).round(2)

    # Invariante: agrupar no puede perder ni inventar votos. Se comprueba aquí dentro y
    # no solo en los controles finales, porque una pérdida silenciosa en este paso se
    # arrastraría a todas las tablas derivadas y ya no se sabría de dónde salió.
    esperado = int(d["votos"].sum())
    obtenido = int(t["votos_depositados"].sum())
    if esperado != obtenido:
        raise DatosInconsistentes(
            f"El desglose por puesto cambió el total de votos: {obtenido} en lugar de "
            f"{esperado}. Es una pérdida de filas al agrupar, no un error de redondeo.")
    desc = int((t["votos_validos"] + t["votos_no_validos"]
                != t["votos_depositados"]).sum())
    if desc:
        raise DatosInconsistentes(
            f"{desc} puestos donde válidos + no válidos no da los depositados. "
            "El desglose por tipo de opción no está cubriendo todas las filas.")
    return t.drop(columns=["_k"])


def unir_censo(puesto_eleccion: pd.DataFrame, raiz: Path) -> tuple[pd.DataFrame, dict]:
    """Trae el potencial electoral de las tablas de participación ya validadas.

    El cruce entre votos y censo lo resolvió `src/analisis/participacion.py`, con su
    procedimiento de dos pasos y su informe de cobertura. Rehacerlo aquí sería repetir
    trabajo y arriesgarse a que las dos versiones den números distintos. Se lee de ahí.
    """
    carpeta = raiz / "datos" / "procesados" / "participacion"
    trozos = []
    faltantes = []
    for (anio, corp), _ in puesto_eleccion.groupby(["anio", "corporacion"]):
        ruta = carpeta / f"participacion_por_puesto_{str(corp).lower()}_{anio}.csv"
        if not ruta.exists():
            faltantes.append(ruta.name)
            continue
        p = leer_csv(ruta)
        cols = ["id_puesto", "potencial_electoral", "via_del_cruce"]
        cols += [c for c in p.columns if c.startswith(("sexo_", "edad_"))]
        p = p[[c for c in cols if c in p.columns]].copy()
        p["anio"] = anio
        p["corporacion"] = corp
        trozos.append(p)

    if not trozos:
        return puesto_eleccion.copy(), {"con_potencial": 0,
                                        "sin_potencial": int(len(puesto_eleccion)),
                                        "archivos_faltantes": faltantes}

    censo = pd.concat(trozos, ignore_index=True)
    numericas = ["potencial_electoral"] + [c for c in censo.columns
                                           if c.startswith(("sexo_", "edad_"))]
    for c in numericas:
        censo[c] = pd.to_numeric(censo[c], errors="coerce")

    t = puesto_eleccion.merge(censo, on=["anio", "corporacion", "id_puesto"],
                              how="left")
    t["participacion"] = (t["votos_depositados"] / t["potencial_electoral"]
                          * 100).round(2)
    t["abstencion"] = (100 - t["participacion"]).round(2)

    jov = [c for c in t.columns if c in ("edad_18_20", "edad_21_25", "edad_26_30")]
    may = [c for c in t.columns if c == "edad_mas_de_60"]
    if jov:
        t["pct_censo_18_a_30"] = (t[jov].sum(axis=1)
                                  / t["potencial_electoral"] * 100).round(2)
    if may:
        t["pct_censo_mas_de_60"] = (t[may].sum(axis=1)
                                    / t["potencial_electoral"] * 100).round(2)
    if "sexo_mujeres" in t.columns:
        t["pct_censo_mujeres"] = (t["sexo_mujeres"]
                                  / t["potencial_electoral"] * 100).round(2)

    return t, {"con_potencial": int(t["potencial_electoral"].notna().sum()),
               "sin_potencial": int(t["potencial_electoral"].isna().sum()),
               "archivos_faltantes": faltantes}


def marcar_extremos(puesto_eleccion: pd.DataFrame) -> pd.DataFrame:
    """Marca lo que se sale de rango. **No borra ni recorta nada.**

    Un puesto con participación imposible es un dato que hay que mirar, no un estorbo que
    haya que quitar: puede ser un error de la fuente o puede ser un puesto real con una
    particularidad, como la cárcel. Quien analice decide, con la marca a la vista.
    """
    t = puesto_eleccion.copy()
    t["marca_participacion_imposible"] = (
        t["participacion"].notna() & (t["participacion"] > 100))
    t["marca_participacion_muy_baja"] = (
        t["participacion"].notna() & (t["participacion"] < 20))
    t["marca_sin_potencial"] = t["potencial_electoral"].isna()
    t["marca_puesto_pequeno"] = t["votos_depositados"] < 100
    t["marca_no_validos_altos"] = t["pct_no_validos"] > 30 if "pct_no_validos" in t.columns else False
    t["pct_no_validos"] = (t["votos_no_validos"] / t["votos_depositados"]
                           * 100).round(2)
    t["marca_no_validos_altos"] = t["pct_no_validos"] > 30
    t["marca_ambito_especial"] = t["ambito"] == "especial"

    marcas = [c for c in t.columns if c.startswith("marca_")]
    t["marcas_activas"] = t[marcas].sum(axis=1).astype(int)
    return t


def unir_geografia(puesto_eleccion: pd.DataFrame, raiz: Path) -> tuple[pd.DataFrame, dict]:
    """Añade coordenada del puesto y área del territorio, si la geometría existe."""
    t = puesto_eleccion.copy()
    informe = {"con_coordenada": 0, "con_area": 0}

    coord = raiz / "datos" / "procesados" / "geografia" / "puestos_coordenadas.csv"
    if coord.exists():
        g = leer_csv(coord)
        g = g[["id_puesto", "lon", "lat", "parecido", "puestos_en_el_mismo_sitio"]]
        g = g.rename(columns={"parecido": "parecido_geocodificacion",
                              "puestos_en_el_mismo_sitio": "puestos_que_comparten_punto"})
        for c in ("lon", "lat", "parecido_geocodificacion",
                  "puestos_que_comparten_punto"):
            g[c] = pd.to_numeric(g[c], errors="coerce")
        g = g.drop_duplicates("id_puesto")
        t = t.merge(g, on="id_puesto", how="left")
        informe["con_coordenada"] = int(t["lon"].notna().sum())

    limites = raiz / "datos" / "geograficos" / "limites_administrativos.geojson"
    if limites.exists():
        import json
        gj = json.loads(limites.read_text(encoding="utf-8"))
        filas = []
        for f in gj.get("features", []):
            p = f["properties"]
            m = re.search(r"COMUNA\s+(\d+)", canon(p.get("nombre", "")))
            if p.get("admin_level") == "8" and m:
                filas.append({"cod_comuna": m.group(1).zfill(2),
                              "area_km2": p.get("area_km2_aprox")})
        if filas:
            areas = pd.DataFrame(filas)
            t = t.merge(areas, on="cod_comuna", how="left")
            informe["con_area"] = int(t["area_km2"].notna().sum())
            t["densidad_votos_km2"] = (t["votos_depositados"]
                                       / t["area_km2"]).round(1)
    return t, informe


# ------------------------------------------------------------------ controles

def controles(larga: pd.DataFrame, puesto_eleccion: pd.DataFrame,
              panel: pd.DataFrame, informe_panel: pd.DataFrame,
              informe_censo: dict) -> pd.DataFrame:
    """Controles del preprocesamiento. Lo que no cuadra se marca con criticidad alta."""
    filas = []

    def chequeo(nombre, valor, esperado, pasa, criticidad="Media"):
        filas.append({"control": nombre, "valor": valor, "esperado": esperado,
                      "criticidad": criticidad, "pasa": bool(pasa)})

    t = puesto_eleccion
    desc = int((t["votos_validos"] + t["votos_no_validos"]
                != t["votos_depositados"]).sum())
    chequeo("válidos + no válidos = depositados, en cada puesto", desc,
            "0 filas descuadradas", desc == 0, "Alta")

    suma_larga = int(pd.to_numeric(larga["votos"], errors="coerce").fillna(0).sum())
    suma_puesto = int(t["votos_depositados"].sum())
    chequeo("la tabla por puesto conserva todos los votos",
            f"{suma_puesto} vs {suma_larga}", "iguales",
            suma_puesto == suma_larga, "Alta")

    sin_voto = int(larga["votos"].isna().sum())
    chequeo("ningún voto se perdió al convertir a número", sin_voto,
            "0 valores no numéricos", sin_voto == 0, "Alta")

    anchos_malos = []
    for c, ancho in ANCHOS.items():
        if c in larga.columns:
            w = {len(str(x)) for x in larga[c].dropna()}
            if w - {ancho}:
                anchos_malos.append(f"{c}:{sorted(w)}")
    chequeo("todos los códigos quedaron del mismo ancho",
            ", ".join(anchos_malos) or "todos correctos",
            "un solo ancho por código", not anchos_malos, "Alta")

    dup = int(t.duplicated(["anio", "corporacion", "id_puesto"]).sum())
    chequeo("un puesto no se repite dentro de una elección", dup,
            "0 duplicados", dup == 0, "Alta")

    sin_ambito = int((t["ambito"] == "sin_dato").sum())
    chequeo("todo puesto tiene ámbito urbano, rural o especial", sin_ambito,
            "0 puestos sin ámbito", sin_ambito == 0, "Alta")

    imposible = int(t["marca_participacion_imposible"].sum())
    chequeo("ninguna participación pasa de 100 %", imposible,
            "0 puestos", imposible == 0, "Alta")

    chequeo("puestos con potencial electoral",
            f"{informe_censo['con_potencial']} con, {informe_censo['sin_potencial']} sin",
            "informativo: sin potencial no se calcula participación",
            True, "Baja")
    if informe_censo.get("archivos_faltantes"):
        chequeo("faltan tablas de participación",
                ", ".join(informe_censo["archivos_faltantes"]),
                "ninguna", False, "Media")

    en_panel = int(panel["en_panel"].sum())
    chequeo("puestos con identidad de panel en más de un año",
            f"{en_panel} de {len(panel)} filas de puesto-año",
            "informativo: los demás abrieron o cerraron", True, "Baja")
    completo = panel[panel["en_panel_completo"]]["id_panel"].nunique()
    chequeo("puestos presentes en todos los años", completo,
            "informativo: es la base del panel equilibrado", True, "Baja")

    sin_emp = int(informe_panel["sin_emparejar"].sum())
    chequeo("puestos que no emparejaron con el año de referencia", sin_emp,
            "informativo: no se fuerzan", True, "Baja")

    especiales = sorted(set(larga.loc[larga["tipo_opcion"].isin(
        ["blanco", "nulo", "no_marcado"]), "cod_candidato"].dropna()))
    chequeo("las opciones especiales son 996, 997 y 998",
            ", ".join(especiales), "00996, 00997, 00998",
            especiales == ["00996", "00997", "00998"], "Media")

    lista_con_cand = int(((larga["tipo_opcion"] == "lista")
                          & larga["nombre_candidato"].notna()).sum())
    chequeo("ningún voto de lista cuenta como candidato", lista_con_cand,
            "0 filas", lista_con_cand == 0, "Alta")

    return pd.DataFrame(filas)
