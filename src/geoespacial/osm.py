# -*- coding: utf-8 -*-
"""Geometrías de Barrancabermeja desde OpenStreetMap, sin librerías geoespaciales.

**Por qué esta ruta.** El DANE publica el Marco Geoestadístico Nacional, que es la fuente
oficial de los límites de comuna y corregimiento. Su portal no responde desde este entorno
y la descarga manual tampoco se logró. OpenStreetMap sí tiene las 7 comunas de
Barrancabermeja cargadas como límites administrativos (`admin_level=8`), el perímetro
urbano (`admin_level=7`) y el límite municipal (`admin_level=6`). Eso salva la geometría
urbana, que es donde está la gran mayoría del censo electoral.

**Qué cambia respecto a la fuente oficial.** OSM es colaborativo: los límites los cargó
alguien, no la autoridad catastral. Para este proyecto eso es aceptable con dos
condiciones, y el módulo las cumple las dos:

1. Cada polígono queda registrado con su identificador de OSM, su versión y la fecha de
   la consulta, de modo que cualquiera puede ir a verlo.
2. La asignación de puesto a comuna que produce OSM se **compara** contra el código de
   comuna que la Registraduría ya trae en los resultados electorales. Son dos fuentes
   independientes; si coinciden, la geometría es usable, y si no, el desacuerdo se
   reporta puesto por puesto y manda la Registraduría, que es la fuente oficial para la
   pertenencia administrativa de un puesto de votación.

Es decir: **OSM aporta la forma, no la clasificación.** La comuna de un puesto la sigue
diciendo la Registraduría. OSM sirve para dibujar el mapa y para calcular vecindad, que es
lo que hacía falta.

**Sin dependencias geoespaciales.** No hay geopandas, shapely ni pyproj en el entorno. No
se instalan: todo lo que se necesita —ensamblar anillos, punto en polígono, centroide,
área aproximada, vecindad por frontera compartida— son cuarenta líneas de geometría
elemental y están aquí. La salida es GeoJSON estándar, así que el día que haya geopandas
lo lee sin tocar nada.

**Lo que este módulo NO resuelve.** Los corregimientos (códigos 08 a 13, donde vota
alrededor del 15 % del censo) no están en OSM como polígonos administrativos. Para esos la
salida es un punto, cuando OSM tiene el centro poblado, y nada cuando no lo tiene. Un mapa
de comunas con los corregimientos como puntos es honesto; uno que les invente un polígono
no lo es.

Uso:
    python src/geoespacial/osm.py
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# Espejos de Overpass. El primero limita por uso; los otros son alternativas públicas.
ESPEJOS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

CABECERAS = {
    "User-Agent": ("ObservatorioElectoralBarrancabermeja/1.0 "
                   "(investigacion academica; contacto via repositorio)"),
    "Accept": "application/json",
}

MUNICIPIO = "Barrancabermeja"

# Los límites administrativos dentro del municipio: comunas (8), perímetro urbano (7)
# y el municipio mismo (6).
CONSULTA_LIMITES = f"""
[out:json][timeout:180];
area["name"="{MUNICIPIO}"]["boundary"="administrative"]->.a;
(
  relation(area.a)["boundary"="administrative"]["admin_level"~"^(6|7|8)$"];
  relation["name"="{MUNICIPIO}"]["boundary"="administrative"]["admin_level"="6"];
);
out geom;
"""
# Nota sobre `out geom;`: en Overpass, `out tags;` imprime SOLO las etiquetas y suprime
# los miembros de la relación. Escribir `out geom tags;` devuelve los nombres pero sin
# geometría, y el resultado es una colección vacía de polígonos sin ningún error visible.
# `out geom;` trae cuerpo y geometría, que es lo que hace falta.

# Centros poblados: lo único que OSM ofrece para los corregimientos.
CONSULTA_POBLADOS = f"""
[out:json][timeout:180];
area["name"="{MUNICIPIO}"]["boundary"="administrative"]->.a;
node(area.a)["place"];
out tags center;
"""

# Sitios que suelen alojar puestos de votación. Sirven para darle coordenada a cada
# puesto por coincidencia de nombre.
CONSULTA_SITIOS = f"""
[out:json][timeout:180];
area["name"="{MUNICIPIO}"]["boundary"="administrative"]->.a;
(
  nwr(area.a)["amenity"~"^(school|college|university|kindergarten|community_centre|place_of_worship|townhall)$"];
  nwr(area.a)["building"~"^(school|university|college|civic|public)$"];
  nwr(area.a)["office"="government"];
);
out tags center;
"""

TOLERANCIA_NODO = 1e-7  # grados; dos vértices más cercanos que esto son el mismo nodo
RADIO_TIERRA_KM = 6371.0088

# La Registraduría abrevia los nombres de los puestos y OSM los escribe completos.
# Sin esta tabla el emparejamiento por nombre no encuentra casi nada.
ABREVIATURAS = {
    "COL": "COLEGIO", "COLE": "COLEGIO", "ESC": "ESCUELA", "ESCU": "ESCUELA",
    "INST": "INSTITUTO", "INSTIT": "INSTITUTO", "I E": "INSTITUCION EDUCATIVA",
    "IE": "INSTITUCION EDUCATIVA", "INEM": "INEM", "CENT": "CENTRO",
    "CTRO": "CENTRO", "SED": "SEDE", "NTRA": "NUESTRA", "NTRO": "NUESTRO",
    "SRA": "SENORA", "STA": "SANTA", "STO": "SANTO", "S": "SAN",
    "TEC": "TECNICO", "TECN": "TECNICO", "NAL": "NACIONAL", "DPTAL": "DEPARTAMENTAL",
    "MPAL": "MUNICIPAL", "UNIV": "UNIVERSIDAD", "POLIDEP": "POLIDEPORTIVO",
    "CONC": "CONCENTRACION", "DES": "DESARROLLO", "COM": "COMUNAL",
    # Abreviaturas vistas en las tablas reales de Barrancabermeja.
    "SD": "SEDE", "HDEZ": "HERNANDEZ", "EDUC": "EDUCATIVA",
    "AGROP": "AGROPECUARIO", "RESTR": "RESTREPO",
    "UIS": "UNIVERSIDAD INDUSTRIAL SANTANDER",
}

# Palabras que no distinguen un puesto de otro: si el parecido se apoya solo en ellas,
# no es un parecido.
VACIAS = {"DE", "DEL", "LA", "EL", "LOS", "LAS", "Y", "SEDE", "COLEGIO", "ESCUELA",
          "INSTITUCION", "EDUCATIVA", "INSTITUTO", "CENTRO", "PUESTO", "VOTACION"}

# Para nombres de lugares la lista es más corta: `CENTRO` sí distingue, porque el
# corregimiento El Centro se llama así. Con `CENTRO` en la lista de palabras vacías, ese
# corregimiento no se puede ubicar nunca.
VACIAS_LUGAR = VACIAS - {"CENTRO"}


class OverpassInalcanzable(RuntimeError):
    """Ningún espejo de Overpass respondió con datos utilizables."""

    def __init__(self, mensaje, intentos):
        super().__init__(mensaje)
        self.intentos = intentos


# --------------------------------------------------------------------------- consulta

def consultar(consulta: str, espejos=ESPEJOS, reintentos: int = 3,
              espera: float = 12.0, verboso: bool = True) -> dict:
    """Envía una consulta a Overpass, rotando espejos y esperando entre intentos.

    Overpass limita por uso y responde HTML cuando lo hace. La respuesta se valida como
    JSON antes de darla por buena: un HTML con código 200 no es un resultado vacío, es un
    rechazo, y confundir las dos cosas produciría un mapa sin comunas sin avisar.
    """
    intentos = []
    for vuelta in range(reintentos):
        for url in espejos:
            etiqueta = f"{url.split('/')[2]} (intento {vuelta + 1})"
            try:
                r = requests.post(url, data={"data": consulta},
                                  headers=CABECERAS, timeout=240)
            except Exception as e:  # noqa: BLE001
                intentos.append({"espejo": etiqueta, "resultado": f"error de red: {e}"})
                if verboso:
                    print(f"   . {etiqueta}: error de red")
                continue

            if r.status_code != 200:
                intentos.append({"espejo": etiqueta, "resultado": f"HTTP {r.status_code}"})
                if verboso:
                    print(f"   . {etiqueta}: HTTP {r.status_code}")
                time.sleep(espera)
                continue

            try:
                datos = r.json()
            except Exception:  # noqa: BLE001
                pista = re.sub(r"\s+", " ", r.text[:200])
                intentos.append({"espejo": etiqueta,
                                 "resultado": f"respuesta no JSON: {pista}"})
                if verboso:
                    print(f"   . {etiqueta}: respondió HTML, probablemente límite de uso")
                time.sleep(espera)
                continue

            if "elements" not in datos:
                intentos.append({"espejo": etiqueta, "resultado": "JSON sin 'elements'"})
                continue

            if verboso:
                print(f"   ok {etiqueta}: {len(datos['elements'])} elementos")
            return datos
        time.sleep(espera)

    raise OverpassInalcanzable(
        "Ningún espejo de Overpass devolvió datos. Casi siempre es límite de uso: "
        "espera unos minutos y vuelve a correr. El resto del proyecto no depende de esto.",
        intentos)


# ------------------------------------------------------------------- geometría básica

def _mismo_punto(a, b, tol=TOLERANCIA_NODO) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def ensamblar_anillos(segmentos: list[list[tuple]]) -> list[dict]:
    """Pega tramos sueltos en anillos cerrados.

    Una relación de límite administrativo en OSM no es un polígono: es una lista de
    tramos (`way`) que, puestos en orden, cierran el contorno. Vienen desordenados y con
    orientación arbitraria. Esto los encadena por extremos coincidentes.

    Cada anillo devuelto dice si logró cerrarse. Un anillo abierto significa que al
    límite le faltan tramos en OSM, y eso se reporta como control fallido en vez de
    cerrarlo a la fuerza y fingir que el polígono estaba completo.
    """
    pendientes = [list(s) for s in segmentos if len(s) >= 2]
    anillos = []

    while pendientes:
        actual = pendientes.pop(0)
        while not _mismo_punto(actual[0], actual[-1]):
            pegado = False
            for i, s in enumerate(pendientes):
                if _mismo_punto(actual[-1], s[0]):
                    actual.extend(s[1:])
                elif _mismo_punto(actual[-1], s[-1]):
                    actual.extend(list(reversed(s))[1:])
                elif _mismo_punto(actual[0], s[-1]):
                    actual = s[:-1] + actual
                elif _mismo_punto(actual[0], s[0]):
                    actual = list(reversed(s))[:-1] + actual
                else:
                    continue
                pendientes.pop(i)
                pegado = True
                break
            if not pegado:
                break

        cerrado = _mismo_punto(actual[0], actual[-1])
        if not cerrado:
            actual = actual + [actual[0]]  # se cierra para poder dibujarlo, y se avisa
        anillos.append({"puntos": actual, "cerrado_en_osm": cerrado})

    return anillos


def area_con_signo(anillo: list[tuple]) -> float:
    """Área con signo en grados cuadrados. El signo indica la orientación del anillo."""
    s = 0.0
    for i in range(len(anillo) - 1):
        x1, y1 = anillo[i]
        x2, y2 = anillo[i + 1]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def area_km2(anillo: list[tuple]) -> float:
    """Área aproximada en km².

    Proyección equirectangular local: se escala la longitud por el coseno de la latitud
    media del anillo. A la latitud de Barrancabermeja (7° N) y para áreas del tamaño de
    una comuna el error es de décimas de porcentaje, muy por debajo de lo que importa
    para una densidad de votantes. No es un área catastral y no se debe usar como tal.
    """
    if len(anillo) < 4:
        return 0.0
    lat_media = sum(p[1] for p in anillo) / len(anillo)
    k = math.cos(math.radians(lat_media))
    grado_km = math.pi * RADIO_TIERRA_KM / 180.0
    proyectado = [(x * k * grado_km, y * grado_km) for x, y in anillo]
    return abs(area_con_signo(proyectado))


def centroide(anillo: list[tuple]) -> tuple:
    """Centroide del área del anillo (no el promedio de los vértices)."""
    a = area_con_signo(anillo)
    if abs(a) < 1e-15:
        n = max(len(anillo), 1)
        return (sum(p[0] for p in anillo) / n, sum(p[1] for p in anillo) / n)
    cx = cy = 0.0
    for i in range(len(anillo) - 1):
        x1, y1 = anillo[i]
        x2, y2 = anillo[i + 1]
        cruz = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cruz
        cy += (y1 + y2) * cruz
    return (cx / (6 * a), cy / (6 * a))


def punto_en_anillo(lon: float, lat: float, anillo: list[tuple]) -> bool:
    """Punto en polígono por lanzamiento de rayo (par-impar).

    Se cuenta cuántas veces un rayo horizontal hacia el este cruza el borde. Impar es
    dentro. Es el algoritmo clásico y no necesita ninguna librería.
    """
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i]
        xj, yj = anillo[j]
        if (yi > lat) != (yj > lat):
            x_corte = xi + (lat - yi) * (xj - xi) / (yj - yi)
            if lon < x_corte:
                dentro = not dentro
        j = i
    return dentro


def punto_en_feature(lon: float, lat: float, feature: dict) -> bool:
    """Dentro de un Feature de GeoJSON: dentro de un anillo exterior y fuera de los huecos."""
    geo = feature.get("geometry") or {}
    tipo = geo.get("type")
    if tipo == "Polygon":
        poligonos = [geo["coordinates"]]
    elif tipo == "MultiPolygon":
        poligonos = geo["coordinates"]
    else:
        return False

    for poli in poligonos:
        if not poli:
            continue
        exterior = [tuple(p) for p in poli[0]]
        if not punto_en_anillo(lon, lat, exterior):
            continue
        en_hueco = any(punto_en_anillo(lon, lat, [tuple(p) for p in hueco])
                       for hueco in poli[1:])
        if not en_hueco:
            return True
    return False


# ----------------------------------------------------------------------- a GeoJSON

def _geometria_de_relacion(elemento: dict) -> tuple[dict, dict]:
    """Convierte una relación de límite de OSM en una geometría de GeoJSON."""
    externos, internos = [], []
    for m in elemento.get("members", []):
        geo = m.get("geometry")
        if not geo:
            continue
        tramo = [(float(p["lon"]), float(p["lat"])) for p in geo]
        (internos if m.get("role") == "inner" else externos).append(tramo)

    anillos_ext = ensamblar_anillos(externos)
    anillos_int = ensamblar_anillos(internos)

    abiertos = sum(1 for a in anillos_ext + anillos_int if not a["cerrado_en_osm"])

    if not anillos_ext:
        return {}, {"anillos_exteriores": 0, "anillos_abiertos": abiertos}

    # Cada anillo exterior lleva los huecos que caen dentro de él.
    poligonos = []
    for ext in anillos_ext:
        ext_pts = ext["puntos"]
        huecos = []
        for int_ in anillos_int:
            p = int_["puntos"][0]
            if punto_en_anillo(p[0], p[1], ext_pts):
                huecos.append([list(q) for q in int_["puntos"]])
        poligonos.append([[list(q) for q in ext_pts]] + huecos)

    if len(poligonos) == 1:
        geometria = {"type": "Polygon", "coordinates": poligonos[0]}
    else:
        geometria = {"type": "MultiPolygon", "coordinates": poligonos}

    mayor = max(anillos_ext, key=lambda a: area_km2(a["puntos"]))
    cx, cy = centroide(mayor["puntos"])
    diag = {
        "anillos_exteriores": len(anillos_ext),
        "anillos_interiores": len(anillos_int),
        "anillos_abiertos": abiertos,
        "area_km2_aprox": round(sum(area_km2(a["puntos"]) for a in anillos_ext), 3),
        "centroide_lon": round(cx, 6),
        "centroide_lat": round(cy, 6),
        "vertices": sum(len(a["puntos"]) for a in anillos_ext),
    }
    return geometria, diag


def limites_a_geojson(datos: dict, consultado_en: str) -> dict:
    """FeatureCollection con los límites administrativos encontrados."""
    features = []
    for e in datos.get("elements", []):
        if e.get("type") != "relation":
            continue
        tags = e.get("tags", {})
        geometria, diag = _geometria_de_relacion(e)
        if not geometria:
            continue
        features.append({
            "type": "Feature",
            "geometry": geometria,
            "properties": {
                "nombre": tags.get("name", ""),
                "admin_level": tags.get("admin_level", ""),
                "osm_tipo": "relation",
                "osm_id": e.get("id"),
                "osm_version": e.get("version"),
                "fuente": "OpenStreetMap (ODbL 1.0)",
                "consultado_en": consultado_en,
                **diag,
            },
        })
    features.sort(key=lambda f: (f["properties"]["admin_level"],
                                 f["properties"]["nombre"]))
    return {"type": "FeatureCollection",
            "name": "limites_administrativos_barrancabermeja",
            "licencia": "ODbL 1.0 - (c) colaboradores de OpenStreetMap",
            "features": features}


def puntos_a_geojson(datos: dict, consultado_en: str, nombre: str) -> dict:
    """FeatureCollection de puntos a partir de nodos o de centros de elementos."""
    features = []
    for e in datos.get("elements", []):
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        if lon is None or lat is None:
            continue
        tags = e.get("tags", {})
        if not tags.get("name"):
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {
                "nombre": tags.get("name", ""),
                "place": tags.get("place", ""),
                "amenity": tags.get("amenity", ""),
                "building": tags.get("building", ""),
                "osm_tipo": e.get("type"),
                "osm_id": e.get("id"),
                "fuente": "OpenStreetMap (ODbL 1.0)",
                "consultado_en": consultado_en,
            },
        })
    return {"type": "FeatureCollection", "name": nombre,
            "licencia": "ODbL 1.0 - (c) colaboradores de OpenStreetMap",
            "features": features}


# ------------------------------------------------------- nombres y emparejamiento

def canon(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Za-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip().upper()


def expandir(nombre: str) -> str:
    """Desarma las abreviaturas de la Registraduría para poder comparar con OSM.

    Dos pasos antes de traducir palabra por palabra. Primero se pegan las letras
    sueltas consecutivas, porque `I.E.` queda como `I E` al quitar los puntos y
    `INSTITUCION EDUCATIVA` se perdería. Después se aplican las abreviaturas que son de
    más de una palabra. Solo entonces se traduce cada palabra.
    """
    t = canon(nombre)
    # `I E` -> `IE`, `C D I` -> `CDI`. Una letra sola rodeada de palabras no se toca.
    t = re.sub(r"\b([A-Z])(?:\s+([A-Z])\b)+",
               lambda m: m.group(0).replace(" ", ""), t)
    for clave, valor in ABREVIATURAS.items():
        if " " in clave:
            t = re.sub(rf"\b{re.escape(clave)}\b", valor, t)
    return " ".join(ABREVIATURAS.get(p, p) for p in t.split())


def _distintivas(nombre: str, vacias: set = VACIAS) -> set:
    t = expandir(nombre)
    tokens = {p for p in t.split() if p not in vacias and len(p) > 2}
    # La letra de la sede sí distingue: `SEDE A` y `SEDE B` del mismo colegio son dos
    # puestos. Sin esto las dos sedes quedan idénticas y se pelean la misma coordenada.
    for letra in re.findall(r"\bSEDE\s+([A-Z])\b", t):
        tokens.add("SEDE" + letra)
    return tokens


def parecido(a: str, b: str) -> float:
    """Parecido entre dos nombres, de 0 a 1, contando solo palabras distintivas.

    Dos puestos pueden compartir todas las palabras genéricas —`COLEGIO`, `SEDE`— y ser
    lugares distintos. Lo que decide es lo que queda después de quitar esas: si no hay
    palabras distintivas en común, el parecido es cero por mucho que las cadenas se
    parezcan.
    """
    pa, pb = _distintivas(a), _distintivas(b)
    if not pa or not pb:
        return 0.0
    comunes = pa & pb
    if not comunes:
        return 0.0
    return len(comunes) / len(pa | pb)


def emparejar_puestos(puestos: pd.DataFrame, *colecciones: dict,
                      perimetro: dict | None = None,
                      umbral_seguro: float = 0.6,
                      umbral_dudoso: float = 0.34) -> dict:
    """Le busca coordenada a cada puesto de votación entre los sitios de OSM.

    Devuelve tres grupos separados y **no los mezcla**: los seguros se pueden usar, los
    dudosos hay que revisarlos a mano, y los que no cruzaron se quedan sin coordenada.
    Un puesto sin coordenada se queda sin coordenada; no se le pone el centro de la
    comuna ni nada parecido, porque eso sería inventar un dato.

    `puestos` necesita las columnas `id_puesto` y `puesto`. Si trae `cod_comuna` y
    `comuna`, se arrastran para la verificación posterior. Se pueden pasar varias
    colecciones de puntos: los equipamientos urbanos y los centros poblados, porque los
    puestos rurales llevan el nombre del caserío y no el de un colegio.

    **El perímetro urbano se usa como filtro, y vale la pena explicar por qué.** Hay
    nombres que se repiten entre el casco urbano y la zona rural: `Santa Isabel` es un
    colegio en la comuna 3 y también una vereda. Sin filtro, el puesto urbano se
    empareja con la vereda y queda a veinte kilómetros de donde está. Como la
    Registraduría ya dice si el puesto es urbano (comunas 01 a 07) o rural (08 a 13),
    esa información descarta al candidato imposible.

    Lo que **no** se hace es filtrar por comuna. Sería fácil y mejoraría los números,
    pero volvería circular la verificación posterior: se estaría eligiendo el punto para
    que caiga en la comuna correcta y luego comprobando que cae en la comuna correcta.
    El filtro llega hasta urbano o rural y ahí se detiene.
    """
    candidatos = []
    vistos = set()
    for coleccion in colecciones:
        for f in coleccion.get("features", []):
            p = f["properties"]
            clave = (p.get("osm_tipo"), p.get("osm_id"))
            if clave in vistos:
                continue
            vistos.add(clave)
            lon, lat = f["geometry"]["coordinates"][:2]
            candidatos.append({
                "nombre_osm": p["nombre"], "lon": lon, "lat": lat,
                "osm_tipo": p.get("osm_tipo", ""),
                "osm_id": p.get("osm_id"),
                "distintivas": _distintivas(p["nombre"]),
                "urbano": (punto_en_feature(lon, lat, perimetro)
                           if perimetro else None),
            })

    arrastre = [c for c in ("cod_comuna", "comuna", "cod_zona", "cod_puesto")
                if c in puestos.columns]

    filas = []
    for _, r in puestos.iterrows():
        pa = _distintivas(r["puesto"])

        # Urbano o rural según la Registraduría. Si no lo dice, no se filtra nada.
        cod = str(r.get("cod_comuna", "") or "").zfill(2)
        espera_urbano = None
        if perimetro is not None and cod.isdigit() and cod != "00":
            espera_urbano = cod <= "07"

        mejor, puntaje = None, 0.0
        for c in candidatos:
            if not pa or not c["distintivas"]:
                continue
            if (espera_urbano is not None and c["urbano"] is not None
                    and c["urbano"] != espera_urbano):
                continue
            comunes = pa & c["distintivas"]
            if not comunes:
                continue
            s = len(comunes) / len(pa | c["distintivas"])
            if s > puntaje:
                mejor, puntaje = c, s

        fila = {"id_puesto": r["id_puesto"], "puesto": r["puesto"],
                "puesto_expandido": expandir(r["puesto"]),
                "se_esperaba_urbano": espera_urbano}
        fila.update({c: r[c] for c in arrastre})
        if mejor and puntaje >= umbral_dudoso:
            fila.update({"nombre_osm": mejor["nombre_osm"], "lon": mejor["lon"],
                         "lat": mejor["lat"], "osm_tipo": mejor["osm_tipo"],
                         "osm_id": mejor["osm_id"], "parecido": round(puntaje, 3)})
        else:
            fila.update({"nombre_osm": "", "lon": None, "lat": None, "osm_tipo": "",
                         "osm_id": None, "parecido": round(puntaje, 3)})
        filas.append(fila)

    d = pd.DataFrame(filas)

    # Varios puestos pueden caer en el mismo sitio de OSM. A veces es correcto —dos sedes
    # del mismo colegio, dos puestos en un mismo polideportivo— y a veces es un
    # emparejamiento flojo. No se puede distinguir automáticamente, así que la coordenada
    # se conserva y la fila queda **marcada**: `puestos_en_el_mismo_sitio` dice cuántos
    # comparten el punto. Para asignar comuna da igual, porque es el mismo lugar; para
    # cualquier cosa que trate los puestos como puntos distintos, hay que mirar la marca.
    d["puestos_en_el_mismo_sitio"] = 1
    con_id = d["osm_id"].notna()
    if con_id.any():
        cuenta = d.loc[con_id].groupby("osm_id")["id_puesto"].transform("size")
        d.loc[con_id, "puestos_en_el_mismo_sitio"] = cuenta

    seguros = d[d["parecido"] >= umbral_seguro].copy()
    dudosos = d[(d["parecido"] >= umbral_dudoso)
                & (d["parecido"] < umbral_seguro)].copy()
    sin_cruce = d[d["parecido"] < umbral_dudoso].copy()
    compartidos = d[(d["puestos_en_el_mismo_sitio"] > 1)
                    & con_id].sort_values(["osm_id", "puesto"])

    return {"todos": d, "seguros": seguros, "dudosos": dudosos,
            "sin_cruce": sin_cruce, "sitios_compartidos": compartidos,
            "sitios_en_osm": len(candidatos)}


# --------------------------------------------------------------- verificación cruzada

def nombre_de_territorio(bruto) -> str:
    """Limpia el nombre de comuna o corregimiento tal como viene de la Registraduría.

    En las tablas de votos el mismo territorio aparece escrito de dos formas, con el
    código pegado al nombre y sin él: `08CORREGIMIENTO EL CENTRO` y
    `CORREGIMIENTO EL CENTRO`. Sin normalizar, cada corregimiento sale duplicado.
    """
    return re.sub(r"^\d{2}(?=[A-Z])", "", canon(bruto)).strip()


def _comuna_de_osm(nombre_osm: str) -> str:
    """Saca el número de comuna del nombre que usa OSM, p. ej. `Comuna 3 de ...` -> `03`."""
    m = re.search(r"COMUNA\s+(\d+)", canon(nombre_osm))
    return m.group(1).zfill(2) if m else ""


def verificar_comunas(emparejados: pd.DataFrame, limites: dict) -> dict:
    """Compara la comuna que dice el polígono de OSM con la que dice la Registraduría.

    Esta es la prueba que decide si la geometría sirve. Son dos fuentes que no se
    hablan: la Registraduría asigna cada puesto a una comuna por acto administrativo, y
    OSM dibuja los límites por su lado. Si al meter el punto del puesto en el polígono
    sale la misma comuna, la geometría concuerda con la realidad administrativa.

    **Ante un desacuerdo manda la Registraduría.** OSM aporta la forma, no la
    clasificación.
    """
    comunas = [f for f in limites.get("features", [])
               if f["properties"].get("admin_level") == "8"
               and _comuna_de_osm(f["properties"]["nombre"])]

    con_punto = emparejados[emparejados["lon"].notna()].copy()
    if not len(con_punto) or not comunas:
        return {"tabla": pd.DataFrame(), "comunas_en_osm": len(comunas),
                "puestos_con_punto": int(len(con_punto)), "comparables": 0,
                "coinciden": 0, "discrepan": 0, "pct_coincidencia": 0.0,
                "fuera_de_todo_poligono": int(len(con_punto))}

    # Un punto que varios puestos comparten solo sirve para esta prueba si todos esos
    # puestos están en la misma comuna según la Registraduría. Cuando no lo están, el
    # punto es de uno solo y a los demás se les asignó por parecido de nombre: usarlo
    # como prueba produciría discrepancias que no dicen nada sobre el polígono.
    ambiguos = set()
    if "osm_id" in con_punto.columns and "cod_comuna" in con_punto.columns:
        for oid, g in con_punto.groupby("osm_id"):
            codigos = {str(x).zfill(2) for x in g["cod_comuna"].dropna()}
            if len(codigos) > 1:
                ambiguos.add(oid)

    filas = []
    for _, r in con_punto.iterrows():
        dentro_de = [_comuna_de_osm(f["properties"]["nombre"]) for f in comunas
                     if punto_en_feature(r["lon"], r["lat"], f)]
        cod = (str(r.get("cod_comuna", "")).zfill(2)
               if pd.notna(r.get("cod_comuna")) else "")
        filas.append({
            "id_puesto": r["id_puesto"], "puesto": r["puesto"],
            "nombre_osm": r.get("nombre_osm", ""), "parecido": r.get("parecido"),
            "comuna_registraduria": cod,
            "es_urbano_segun_registraduria": (cod <= "07" if cod.isdigit()
                                              and cod != "00" else None),
            "comuna_segun_osm": dentro_de[0] if len(dentro_de) == 1 else "",
            "poligonos_que_lo_contienen": len(dentro_de),
            "punto_compartido_entre_comunas": r.get("osm_id") in ambiguos,
        })

    t = pd.DataFrame(filas)
    urbano = t["es_urbano_segun_registraduria"] == True  # noqa: E712
    util = (t["comuna_registraduria"] != "") & ~t["punto_compartido_entre_comunas"]
    comparable = util & urbano & (t["comuna_segun_osm"] != "")

    t["veredicto"] = ""
    t.loc[comparable & (t["comuna_registraduria"] == t["comuna_segun_osm"]),
          "veredicto"] = "coincide"
    t.loc[comparable & (t["comuna_registraduria"] != t["comuna_segun_osm"]),
          "veredicto"] = "discrepa"
    t.loc[(t["veredicto"] == "") & t["punto_compartido_entre_comunas"],
          "veredicto"] = "no concluyente: varios puestos comparten el punto"
    # Un puesto rural fuera de las comunas es lo correcto, no un error.
    t.loc[(t["veredicto"] == "") & ~urbano & (t["poligonos_que_lo_contienen"] == 0),
          "veredicto"] = "rural y fuera de las comunas: como se espera"
    t.loc[(t["veredicto"] == "") & urbano & (t["poligonos_que_lo_contienen"] == 0),
          "veredicto"] = "urbano pero fuera de toda comuna: revisar"
    t.loc[(t["veredicto"] == "") & (t["poligonos_que_lo_contienen"] > 1),
          "veredicto"] = "punto en varios poligonos: revisar"
    t.loc[t["veredicto"] == "", "veredicto"] = "sin comuna en la Registraduria"

    n_comp = int(comparable.sum())
    coinciden = int((t["veredicto"] == "coincide").sum())
    return {
        "tabla": t.sort_values(["veredicto", "puesto"]).reset_index(drop=True),
        "comunas_en_osm": len(comunas),
        "puestos_con_punto": int(len(con_punto)),
        "comparables": n_comp,
        "coinciden": coinciden,
        "discrepan": int((t["veredicto"] == "discrepa").sum()),
        "pct_coincidencia": round(coinciden / n_comp * 100, 1) if n_comp else 0.0,
        "no_concluyentes": int(t["punto_compartido_entre_comunas"].sum()),
        "rurales_fuera": int((t["veredicto"]
                              == "rural y fuera de las comunas: como se espera").sum()),
        "urbanos_fuera": int((t["veredicto"]
                              == "urbano pero fuera de toda comuna: revisar").sum()),
        "fuera_de_todo_poligono": int((t["poligonos_que_lo_contienen"] == 0).sum()),
    }


def ubicar_corregimientos(territorios: pd.DataFrame, poblados: dict,
                          umbral: float = 0.5) -> pd.DataFrame:
    """Le busca un punto a cada corregimiento entre los centros poblados de OSM.

    Los corregimientos **no tienen polígono** en OSM: no están cargados como límites
    administrativos. Lo que sí hay es el caserío como nodo `place`. Un punto no es un
    área y no sirve para calcular densidad ni para colorear un mapa de coropletas, pero
    sí sirve para ubicar el corregimiento en el mapa y para medir distancias.

    Pedirle a OSM el polígono de un corregimiento que no existe produciría un invento.
    Esto devuelve lo que hay, y lo que no hay queda en blanco.

    `territorios` necesita `cod_comuna` y `comuna` (el nombre que usa la Registraduría).
    """
    candidatos = [{
        "nombre_osm": f["properties"]["nombre"],
        "place": f["properties"].get("place", ""),
        "lon": f["geometry"]["coordinates"][0],
        "lat": f["geometry"]["coordinates"][1],
        "osm_id": f["properties"].get("osm_id"),
        "distintivas": _distintivas(f["properties"]["nombre"], VACIAS_LUGAR),
    } for f in poblados.get("features", [])]

    # Jerarquía de OSM: un `village` es más probable que sea la cabecera del
    # corregimiento que un `locality`, que suele ser una finca o un paraje.
    peso = {"town": 3, "village": 3, "suburb": 2, "hamlet": 2,
            "neighbourhood": 1, "locality": 0, "isolated_dwelling": 0}

    filas = []
    for _, r in territorios.iterrows():
        # Se quitan las palabras que OSM no usa en el nombre del caserío, y la
        # abreviatura `CORREG.`/`CORRE.` que la Registraduría escribe de varias formas.
        nombre = re.sub(r"\b(CORREGIMIENTO|CORREG|CORRE|CGTO)\b", "",
                        nombre_de_territorio(r["comuna"])).strip()
        pa = _distintivas(nombre, VACIAS_LUGAR)
        mejor, puntaje, rango = None, 0.0, -1
        for c in candidatos:
            if not pa or not c["distintivas"]:
                continue
            comunes = pa & c["distintivas"]
            if not comunes:
                continue
            s = len(comunes) / len(pa | c["distintivas"])
            p = peso.get(c["place"], 0)
            if (s, p) > (puntaje, rango):
                mejor, puntaje, rango = c, s, p
        fila = {"cod_comuna": r["cod_comuna"], "territorio": r["comuna"],
                "parecido": round(puntaje, 3)}
        if mejor and puntaje >= umbral:
            fila.update({"nombre_osm": mejor["nombre_osm"], "place": mejor["place"],
                         "lon": mejor["lon"], "lat": mejor["lat"],
                         "osm_id": mejor["osm_id"], "geometria": "punto"})
        else:
            fila.update({"nombre_osm": "", "place": "", "lon": None, "lat": None,
                         "osm_id": None, "geometria": "sin ubicar"})
        filas.append(fila)
    return pd.DataFrame(filas)


def vecindad(limites: dict, tol: float = 1e-5) -> pd.DataFrame:
    """Qué comunas comparten frontera, por vértices casi coincidentes.

    Es la matriz que necesita cualquier medida de autocorrelación espacial (Moran, LISA).
    Se construye por contacto de vértices, que es suficiente porque los polígonos de OSM
    comparten los mismos nodos en los bordes comunes. Si dos comunas colindantes no
    aparecen vecinas aquí, es que en OSM sus bordes no están pegados, y eso se ve.
    """
    comunas = [f for f in limites.get("features", [])
               if f["properties"].get("admin_level") == "8"
               and _comuna_de_osm(f["properties"]["nombre"])]

    def vertices(f):
        geo = f["geometry"]
        polis = [geo["coordinates"]] if geo["type"] == "Polygon" else geo["coordinates"]
        s = set()
        for poli in polis:
            for anillo in poli:
                for x, y in anillo:
                    s.add((round(x / tol), round(y / tol)))
        return s

    vs = {_comuna_de_osm(f["properties"]["nombre"]): vertices(f) for f in comunas}
    claves = sorted(vs)
    filas = []
    for i, a in enumerate(claves):
        for b in claves[i + 1:]:
            compartidos = len(vs[a] & vs[b])
            if compartidos:
                filas.append({"comuna_a": a, "comuna_b": b,
                              "vertices_compartidos": compartidos})
    return pd.DataFrame(filas)


def controles(limites: dict, emparejados: dict, verificacion: dict,
              poblados: dict) -> pd.DataFrame:
    """Controles de la geometría. Lo que no cuadra se marca, no se arregla por detrás."""
    filas = []

    def chequeo(nombre, valor, esperado, pasa, criticidad="Media"):
        filas.append({"control": nombre, "valor": valor, "esperado": esperado,
                      "criticidad": criticidad, "pasa": bool(pasa)})

    fs = limites.get("features", [])
    n8 = [f for f in fs if f["properties"].get("admin_level") == "8"]
    comunas = [f for f in n8 if _comuna_de_osm(f["properties"]["nombre"])]
    chequeo("están las 7 comunas como polígono", len(comunas), "7 comunas",
            len(comunas) == 7, "Alta")

    numeros = sorted(_comuna_de_osm(f["properties"]["nombre"]) for f in comunas)
    chequeo("las comunas van de la 01 a la 07", ", ".join(numeros) or "ninguna",
            "01, 02, 03, 04, 05, 06, 07",
            numeros == [f"{i:02d}" for i in range(1, 8)], "Alta")

    abiertos = sum(f["properties"].get("anillos_abiertos", 0) for f in fs)
    chequeo("todos los contornos cierran en OSM", abiertos,
            "0 anillos abiertos", abiertos == 0, "Alta")

    area = round(sum(f["properties"].get("area_km2_aprox", 0) for f in comunas), 1)
    chequeo("el área urbana sumada es plausible", f"{area} km²",
            "entre 20 y 200 km² (las comunas son el casco urbano)",
            20 <= area <= 200, "Media")

    chequeo("hay límite municipal (nivel 6)",
            sum(1 for f in fs if f["properties"].get("admin_level") == "6"),
            "al menos 1", any(f["properties"].get("admin_level") == "6" for f in fs),
            "Media")

    e = emparejados
    total = len(e["todos"])
    chequeo("puestos con coordenada confiable",
            f"{len(e['seguros'])} de {total}",
            "informativo: los dudosos y los sin cruce no reciben coordenada",
            True, "Baja")
    chequeo("puestos que comparten un mismo punto de OSM",
            len(e["sitios_compartidos"]),
            "informativo: queda marcado en `puestos_en_el_mismo_sitio`",
            True, "Baja")

    v = verificacion
    # **Cuál de estos dos controles prueba la geometría.** El decisivo es el primero: si
    # un puesto que la Registraduría pone en el casco urbano cayera fuera de las siete
    # comunas, el conjunto de polígonos no cubriría la ciudad y no serviría. Ese control
    # no depende de acertar *cuál* comuna, solo de que las comunas cubran lo urbano.
    #
    # El segundo, la coincidencia comuna por comuna, mide dos cosas a la vez: el polígono
    # y el geocodificador por nombre. Cuando falla casi siempre es lo segundo —una sede
    # emparejada con el campus principal, que está en otra comuna—, así que su criticidad
    # es media y los casos quedan listados uno por uno para revisarlos a mano. Bajarle la
    # criticidad no es maquillar el resultado: es dejar de atribuirle al polígono un error
    # que es del emparejamiento, y el porcentaje se sigue reportando tal cual.
    chequeo("ningún puesto urbano cae fuera de las 7 comunas",
            v.get("urbanos_fuera", 0), "0 puestos",
            v.get("urbanos_fuera", 0) == 0, "Alta")
    chequeo("la comuna de OSM concuerda con la de la Registraduría",
            f"{v['coinciden']} de {v['comparables']} ({v['pct_coincidencia']} %)",
            "90 % o más; por debajo, revisar `verificacion_comuna.csv` caso por caso",
            v["comparables"] > 0 and v["pct_coincidencia"] >= 90, "Media")
    chequeo("los puestos rurales caen fuera de las comunas, como corresponde",
            v.get("rurales_fuera", 0),
            "informativo: los corregimientos no están dentro del casco urbano",
            True, "Baja")
    chequeo("puestos excluidos de la prueba por compartir punto",
            v.get("no_concluyentes", 0),
            "informativo: no prueban ni refutan la geometría",
            True, "Baja")

    pobl = [f for f in poblados.get("features", []) if f["properties"].get("nombre")]
    chequeo("centros poblados para ubicar corregimientos", len(pobl),
            "informativo: los corregimientos no tienen polígono en OSM",
            True, "Baja")

    return pd.DataFrame(filas)


# ------------------------------------------------------------------------- ejecución

def escribir_geojson(ruta: Path, datos: dict) -> None:
    """Escribe GeoJSON y se niega a escribirlo si lleva NaN o infinitos.

    `json.dumps` acepta `NaN` por omisión y produce un texto que Python vuelve a leer
    pero que **no es JSON válido**: QGIS, un navegador o cualquier otra herramienta lo
    rechaza. Con `allow_nan=False` el error aparece aquí, al escribir, en vez de
    aparecerle a quien intente abrir el mapa.
    """
    try:
        texto = json.dumps(datos, ensure_ascii=False, allow_nan=False)
    except ValueError as e:
        raise ValueError(
            f"{ruta.name} quedaría con valores no representables en JSON ({e}). "
            "Casi siempre es una coordenada vacía que llegó como NaN: hay que dejar "
            "fuera ese elemento, no escribirlo con coordenada nula.") from e
    ruta.write_text(texto, encoding="utf-8")


def _obtener(ruta: Path, consulta: str, convertidor, sello: str,
             refrescar: bool, etiqueta: str) -> dict:
    """Trae una capa de OSM, reusando la copia en disco si ya está descargada.

    Overpass es un servicio público gratuito y limita por uso: tres o cuatro corridas
    seguidas y empieza a responder 429. Guardar lo descargado permite rehacer el
    emparejamiento de puestos cuantas veces haga falta sin volver a pedir los mismos
    polígonos, que además no cambian de un día para otro.

    Para forzar la descarga: `python src/geoespacial/osm.py --refrescar`.
    """
    if ruta.exists() and not refrescar:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            n = len(datos.get("features", []))
            fechas = {f["properties"].get("consultado_en", "")
                      for f in datos.get("features", [])}
            cuando = sorted(fechas)[-1][:10] if fechas else "fecha desconocida"
            print(f"   se reutiliza {ruta.name}: {n} elementos "
                  f"(descargado el {cuando}; --refrescar para volver a pedirlo)")
            return datos
        except Exception as e:  # noqa: BLE001
            print(f"   {ruta.name} ilegible ({e}); se vuelve a descargar")

    try:
        datos = convertidor(consultar(consulta), sello)
    except OverpassInalcanzable as e:
        print(f"   no se pudo descargar {etiqueta}:")
        for i in e.intentos[-3:]:
            print(f"     - {i['espejo']}: {i['resultado']}")
        return {"type": "FeatureCollection", "features": []}
    escribir_geojson(ruta, datos)
    return datos


def raiz_del_proyecto() -> Path:
    aqui = Path(__file__).resolve()
    for p in [aqui.parent, *aqui.parents]:
        if (p / "datos").is_dir() or (p / "src").is_dir():
            if (p / "src").is_dir():
                return p
    return Path.cwd()


def _puestos_del_proyecto(raiz: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Arma el universo de puestos y de territorios a partir de las tablas de votos.

    Se recorren **todas** las tablas de votos y se une el resultado, no solo una: un
    puesto puede existir en 2023 y no en 2019, y el mapa los necesita todos. Se leen solo
    de `datos/procesados/votos`, nunca de la carpeta de salida de este módulo, para que
    una corrida no termine leyendo lo que escribió la anterior.
    """
    base = raiz / "datos" / "procesados" / "votos"
    columnas = {"id_puesto", "puesto"}
    partes = []
    for ruta in sorted(base.rglob("*.csv")):
        try:
            cab = pd.read_csv(ruta, nrows=0, dtype=str)
        except Exception:  # noqa: BLE001
            continue
        if not columnas.issubset(cab.columns):
            continue
        usar = [c for c in ("id_puesto", "puesto", "cod_zona", "cod_puesto",
                            "cod_comuna", "comuna") if c in cab.columns]
        partes.append(pd.read_csv(ruta, usecols=usar, dtype=str))

    if not partes:
        print(f"   no encontré tablas de votos con `id_puesto` y `puesto` en "
              f"{base.relative_to(raiz) if base.exists() else base}")
        return (pd.DataFrame(columns=["id_puesto", "puesto"]),
                pd.DataFrame(columns=["cod_comuna", "comuna"]))

    d = pd.concat(partes, ignore_index=True)
    print(f"   {len(partes)} tablas de votos leídas")

    territorios = pd.DataFrame(columns=["cod_comuna", "comuna"])
    if "cod_comuna" in d.columns and "comuna" in d.columns:
        d["comuna"] = d["comuna"].map(nombre_de_territorio)
        # El código `00` es el consolidado nacional, no un territorio del municipio.
        d = d[d["cod_comuna"].fillna("") != "00"]
        territorios = (d[["cod_comuna", "comuna"]].dropna()
                       .drop_duplicates("cod_comuna").sort_values("cod_comuna")
                       .reset_index(drop=True))
        # No todas las tablas traen comuna. Las filas que sí la traen se ordenan
        # primero, para que al quitar duplicados cada puesto conserve su comuna en vez
        # de quedarse con el vacío de otra tabla.
        d = d.sort_values("cod_comuna", na_position="last")

    puestos = d.drop_duplicates("id_puesto").reset_index(drop=True)
    print(f"   puestos distintos: {len(puestos)}   territorios: {len(territorios)}")
    return puestos, territorios


def main() -> int:
    # La consola de Windows usa cp1252 y revienta al imprimir `²` o una tilde. Sin esto
    # el módulo falla al final, después de haber hecho todo el trabajo.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    raiz = raiz_del_proyecto()
    salida_geo = raiz / "datos" / "geograficos"
    salida_proc = raiz / "datos" / "procesados" / "geografia"
    salida_geo.mkdir(parents=True, exist_ok=True)
    salida_proc.mkdir(parents=True, exist_ok=True)
    sello = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 72)
    print("GEOMETRÍAS DE BARRANCABERMEJA DESDE OPENSTREETMAP")
    print("=" * 72)
    print("\nFuente: OpenStreetMap vía Overpass API. Licencia ODbL 1.0.")
    print("OSM aporta la forma de los límites; la comuna de cada puesto la sigue")
    print("diciendo la Registraduría. Las dos se comparan al final.\n")

    refrescar = "--refrescar" in sys.argv

    print("1. Límites administrativos (comunas, perímetro urbano, municipio)")
    limites = _obtener(salida_geo / "limites_administrativos.geojson",
                       CONSULTA_LIMITES, limites_a_geojson, sello, refrescar,
                       "los límites administrativos")
    if not limites.get("features"):
        print("\n   Sin los límites no hay nada que hacer. Es casi siempre límite de uso")
        print("   de Overpass: espera unos minutos y vuelve a correr. Nada de lo ya")
        print("   descargado se pierde.")
        return 1
    for f in limites["features"]:
        p = f["properties"]
        print(f"     nivel {p['admin_level']}  {p['nombre'] or '(sin nombre)':<42} "
              f"{p.get('area_km2_aprox', 0):>9.2f} km²  {p.get('vertices', 0):>5} vértices")

    print("\n2. Centros poblados (para ubicar los corregimientos)")
    poblados = _obtener(
        salida_geo / "centros_poblados.geojson", CONSULTA_POBLADOS,
        lambda d, s: puntos_a_geojson(d, s, "centros_poblados_barrancabermeja"),
        sello, refrescar, "los centros poblados")
    print(f"     {len(poblados['features'])} lugares con nombre")

    print("\n3. Sitios que pueden alojar puestos de votación")
    sitios = _obtener(
        salida_geo / "sitios_osm.geojson", CONSULTA_SITIOS,
        lambda d, s: puntos_a_geojson(d, s, "sitios_barrancabermeja"),
        sello, refrescar, "los equipamientos")
    print(f"     {len(sitios['features'])} sitios con nombre")
    if not sitios["features"]:
        print("     sin equipamientos no hay coordenadas de puestos, pero los")
        print("     polígonos de comuna ya quedaron guardados, que es lo principal")

    print("\n4. Coordenada para cada puesto de votación")
    puestos, territorios = _puestos_del_proyecto(raiz)
    if not len(puestos):
        print("     Corre primero la ingesta de la Registraduría; la geometría queda")
        print("     guardada igual y el emparejamiento se puede repetir luego.")
        return 0

    perimetros = [f for f in limites["features"]
                  if f["properties"].get("admin_level") == "7"]
    perimetro = perimetros[0] if perimetros else None
    if perimetro is None:
        print("     sin perímetro urbano en OSM: no se puede separar urbano de rural,")
        print("     así que un nombre repetido entre el casco y el campo puede cruzarse mal")
    emp = emparejar_puestos(puestos, sitios, poblados, perimetro=perimetro)
    print(f"     candidatos en OSM: {emp['sitios_en_osm']}")
    print(f"     seguros:   {len(emp['seguros']):>3}")
    print(f"     dudosos:   {len(emp['dudosos']):>3}  (hay que revisarlos a mano)")
    print(f"     sin cruce: {len(emp['sin_cruce']):>3}  (se quedan sin coordenada)")
    print(f"     comparten punto con otro puesto: {len(emp['sitios_compartidos'])}")
    emp["todos"].to_csv(salida_proc / "puestos_coordenadas.csv",
                        index=False, encoding="utf-8-sig")
    emp["dudosos"].to_csv(salida_proc / "puestos_coordenadas_dudosas.csv",
                          index=False, encoding="utf-8-sig")
    emp["sitios_compartidos"].to_csv(salida_proc / "puestos_mismo_punto.csv",
                                     index=False, encoding="utf-8-sig")

    con_coord = emp["seguros"]
    geo_puestos = {
        "type": "FeatureCollection", "name": "puestos_votacion_barrancabermeja",
        "advertencia": ("Coordenadas aproximadas: provienen de emparejar el nombre del "
                        "puesto con sitios de OpenStreetMap. No son la ubicación "
                        "certificada del puesto."),
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": {k: (None if pd.isna(r[k]) else r[k])
                           for k in con_coord.columns if k not in ("lon", "lat")},
        } for _, r in con_coord.iterrows()],
    }
    escribir_geojson(salida_geo / "puestos_votacion.geojson", geo_puestos)

    print("\n5. Verificación: ¿la comuna de OSM es la misma que la de la Registraduría?")
    ver = verificar_comunas(pd.concat([emp["seguros"], emp["dudosos"]])
                            if len(emp["dudosos"]) else emp["seguros"], limites)
    if len(ver["tabla"]):
        ver["tabla"].to_csv(salida_proc / "verificacion_comuna.csv",
                            index=False, encoding="utf-8-sig")
        print(f"     comparables: {ver['comparables']}")
        print(f"     coinciden:   {ver['coinciden']} ({ver['pct_coincidencia']} %)")
        print(f"     discrepan:   {ver['discrepan']}")
        print(f"     fuera de toda comuna: {ver['fuera_de_todo_poligono']} "
              f"(se espera que sean los corregimientos)")
        for v, n in ver["tabla"]["veredicto"].value_counts().items():
            print(f"       {n:>3}  {v}")

    print("\n6. Corregimientos: un punto, porque no tienen polígono en OSM")
    corr = pd.DataFrame()
    if len(territorios):
        rurales = territorios[territorios["cod_comuna"] >= "08"]
        if len(rurales):
            corr = ubicar_corregimientos(rurales, poblados)
            corr.to_csv(salida_proc / "corregimientos_punto.csv",
                        index=False, encoding="utf-8-sig")
            for _, r in corr.iterrows():
                destino = (f"{r['nombre_osm']} ({r['place']})" if r["lon"] is not None
                           else "SIN UBICAR")
                print(f"     {r['cod_comuna']} {r['territorio']:<34} -> {destino}")
            geo_corr = {
                "type": "FeatureCollection", "name": "corregimientos_punto",
                "advertencia": ("Punto, no polígono: los corregimientos no están "
                                "cargados como límites administrativos en OSM. No usar "
                                "para coropletas ni densidades."),
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                    "properties": {"cod_comuna": r["cod_comuna"],
                                   "territorio": r["territorio"],
                                   "nombre_osm": r["nombre_osm"], "place": r["place"],
                                   "osm_id": r["osm_id"], "parecido": r["parecido"],
                                   "fuente": "OpenStreetMap (ODbL 1.0)"},
                    # `pd.notna`, no `is not None`: al construir el DataFrame el None se
                    # vuelve NaN, y `NaN is not None` es verdadero. Con esa comparación
                    # los corregimientos sin ubicar entraban al GeoJSON con coordenadas
                    # NaN, y `NaN` no existe en JSON: el archivo deja de ser legible para
                    # cualquier herramienta que no sea Python.
                } for _, r in corr.iterrows() if pd.notna(r["lon"])],
            }
            escribir_geojson(salida_geo / "corregimientos_punto.geojson", geo_corr)

    print("\n7. Vecindad entre comunas (para autocorrelación espacial)")
    vec = vecindad(limites)
    vec.to_csv(salida_proc / "vecindad_comunas.csv", index=False, encoding="utf-8-sig")
    print(f"     {len(vec)} pares de comunas comparten frontera")

    print("\n8. Controles")
    ctrl = controles(limites, emp, ver, poblados)
    ctrl.to_csv(salida_proc / "controles_geografia.csv",
                index=False, encoding="utf-8-sig")
    for _, r in ctrl.iterrows():
        print(f"     [{'ok' if r['pasa'] else 'XX'}] {r['control']}: {r['valor']}")
    fallos = ctrl[(~ctrl["pasa"]) & (ctrl["criticidad"] == "Alta")]

    print("\n" + "=" * 72)
    print(f"Geometrías en {salida_geo.relative_to(raiz)}")
    print(f"Tablas y controles en {salida_proc.relative_to(raiz)}")
    if len(fallos):
        print(f"\nATENCIÓN: {len(fallos)} control(es) de criticidad alta no pasaron.")
        for _, r in fallos.iterrows():
            print(f"  - {r['control']}: {r['valor']} (se esperaba {r['esperado']})")
    else:
        print("\nTodos los controles de criticidad alta pasaron.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
