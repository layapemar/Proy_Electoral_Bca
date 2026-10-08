# -*- coding: utf-8 -*-
"""Pruebas del preprocesamiento con datos sinteticos que reproducen las trampas reales.

    python src/transformacion/pruebas/prueba_preparacion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import indicadores as ind
import preparacion as prep

fallos = []


def ok(nombre, cond, detalle=""):
    print(("  ok  " if cond else "  XX  ") + nombre + ("" if cond else "  -> " + str(detalle)))
    if not cond:
        fallos.append(nombre)


def fila(**kw):
    base = dict(cod_depto="27", departamento="SANTANDER", cod_municipio="019",
                municipio="BARRANCABERMEJA", cod_zona="01", cod_puesto="01",
                puesto="COL X", mesa="1", cod_comuna="01", comuna="COMUNA 1",
                comuna_normalizada="COMUNA 1", cod_corporacion="004",
                corporacion="CONCEJO", cod_circunscripcion="2", cod_partido="00001",
                partido="PARTIDO A", cod_candidato="00001", candidato="JUAN PEREZ",
                votos="10", clase_opcion="candidatura", id_puesto="aaa",
                archivo_origen="x.csv", tipo_resultado="resultado_publicado",
                id_fuente="REG", anio="2023", familia="territorial")
    base.update(kw)
    return base


print("\n== centinelas de texto ==")
d = pd.DataFrame([fila(comuna="NULL", partido="N/A"), fila(comuna="N/A"), fila()])
lim, inf = prep.normalizar_centinelas(d)
ok("detecta NULL y N/A como centinela", len(inf) >= 2, inf.to_dict("records"))
ok("los convierte a nulo", lim["comuna"].isna().sum() == 2,
   lim["comuna"].tolist())
ok("deja constancia del conteo", int(inf["filas"].sum()) >= 3, inf.to_dict("records"))
ok("no toca los valores legitimos", lim["comuna"].dropna().tolist() == ["COMUNA 1"])

print("\n== ancho de los codigos ==")
d = pd.DataFrame([fila(cod_candidato="996", cod_partido="0000", mesa="1",
                       cod_corporacion="02", cod_circunscripcion="02"),
                  fila(cod_candidato="00996", cod_partido="00000", mesa="0001",
                       cod_corporacion="004", cod_circunscripcion="2")])
n = prep.normalizar_codigos(d)
ok("cod_candidato 996 y 00996 quedan iguales",
   n["cod_candidato"].nunique() == 1, n["cod_candidato"].tolist())
ok("cod_partido queda a 5", set(n["cod_partido"]) == {"00000"}, n["cod_partido"].tolist())
ok("mesa queda a 4", set(n["mesa"]) == {"0001"}, n["mesa"].tolist())
ok("cod_corporacion queda a 3", set(n["cod_corporacion"]) == {"002", "004"},
   n["cod_corporacion"].tolist())
ok("cod_circunscripcion queda a 2", set(n["cod_circunscripcion"]) == {"02"},
   n["cod_circunscripcion"].tolist())

print("\n== territorio ==")
ok("zona 98 es la carcel",
   prep.clasificar_territorio("98", "00")[:2] == ("CARCEL", "especial"))
ok("zona 98 sigue siendo carcel aunque la comuna venga vacia",
   prep.clasificar_territorio("98", None)[:2] == ("CARCEL", "especial"))
ok("comuna 03 es urbana",
   prep.clasificar_territorio("03", "03")[:2] == ("COMUNA 3", "urbano"))
ok("comuna 10 es rural con nombre canonico",
   prep.clasificar_territorio("99", "10")[:2]
   == ("CORREGIMIENTO LA FORTUNA AUTOPISTA", "rural"))
t, a, o = prep.clasificar_territorio("99", None)
ok("zona 99 sin comuna: ambito rural pero territorio vacio",
   (t, a) == ("", "rural"), (t, a, o))
ok("y queda explicado de donde salio el ambito", "zona 99" in o, o)
t2, a2, _ = prep.clasificar_territorio("01", None)
ok("sin comuna y sin zona especial: sin_dato", a2 == "sin_dato", (t2, a2))

print("\n== opciones de la tarjeta ==")
d = pd.DataFrame([
    fila(cod_candidato="00001", clase_opcion="candidatura", votos="10"),
    fila(cod_candidato="00000", clase_opcion="voto_de_lista_no_preferente",
         candidato="PARTIDO A", votos="5"),
    fila(cod_candidato="00996", clase_opcion="opcion_especial",
         candidato="VOTOS EN BLANCO", partido="N/A", votos="3"),
    fila(cod_candidato="00997", clase_opcion="opcion_especial",
         candidato="VOTOS NULOS", partido="N/A", votos="2"),
    fila(cod_candidato="00998", clase_opcion="opcion_especial",
         candidato="VOTOS NO MARCADOS", partido="N/A", votos="1"),
])
m = prep.marcar_opciones(d)
ok("los cinco tipos se identifican",
   m["tipo_opcion"].tolist() == ["candidato", "lista", "blanco", "nulo", "no_marcado"],
   m["tipo_opcion"].tolist())
ok("el blanco es voto valido", bool(m.loc[2, "es_voto_valido"]))
ok("el nulo NO es voto valido", not bool(m.loc[3, "es_voto_valido"]))
ok("el no marcado NO es voto valido", not bool(m.loc[4, "es_voto_valido"]))
ok("el voto de lista NO cuenta como candidato",
   m.loc[1, "nombre_candidato"] is None or pd.isna(m.loc[1, "nombre_candidato"]),
   m.loc[1, "nombre_candidato"])
ok("el nombre del partido no se guarda para el blanco",
   pd.isna(m.loc[2, "nombre_partido"]), m.loc[2, "nombre_partido"])

print("\n== nombres ==")
ok("COL -> COLEGIO", "COLEGIO" in prep.expandir("COL X"))
ok("I.E. -> INSTITUCION EDUCATIVA",
   prep.expandir("I.E. PUEBLO REGAO").startswith("INSTITUCION EDUCATIVA"),
   prep.expandir("I.E. PUEBLO REGAO"))
ok("SD -> SEDE", "SEDE" in prep.expandir("CAMILO TORRES SD F"))
s1 = prep.similitud("COL TECINDUSTRIAL SEDE E", "COL TEC INDUSTRIAL SEDE E")
ok("variantes de grafia del caso real emparejan", s1 >= 0.6, s1)
s2 = prep.similitud("COL EL CASTILLO SEDE D (EL PAL", "COL EL CASTILLO SEDE D  EL PALMAR")
ok("el castillo con parentesis empareja", s2 >= 0.6, s2)
s3 = prep.similitud("COL SANTA TERESITA", "INSTITUTO ANTONIO NARINO")
ok("dos colegios distintos NO emparejan", s3 == 0.0, s3)
s4 = prep.similitud("COL X SEDE A", "COL X SEDE B")
ok("sede A y sede B se distinguen", s4 < 0.6, s4)

print("\n== panel: reproduce la renumeracion real ==")
# En 2019 el puesto 04 es INTECOBA D y el 08 es SANTA TERESITA.
# En 2023 el 04 es ANTONIO NARINO, el 05 es INTECOBA y el 07 es SANTA TERESITA.
filas = []
for p, nombre in (("04", "COL. INTECOBA - D"), ("08", "COL SANTA TERESITA"),
                  ("09", "COL ANTONIA SANTOS")):
    filas.append(fila(anio="2019", cod_puesto=p, puesto=nombre,
                      id_puesto="19" + p))
for p, nombre in (("04", "INSTITUTO ANTONIO NARINO"), ("05", "COL INTECOBA"),
                  ("07", "COL SANTA TERESITA")):
    filas.append(fila(anio="2023", cod_puesto=p, puesto=nombre,
                      id_puesto="23" + p))
larga = pd.DataFrame(filas)
larga = prep.marcar_opciones(prep.normalizar_codigos(larga))
larga["territorio"] = "COMUNA 1"
larga["ambito"] = "urbano"
larga["origen_del_ambito"] = "cod_comuna"
larga["es_uninominal"] = False
larga["votos"] = 10

panel, inf_panel = prep.construir_panel(larga, anio_referencia="2023")
por_nombre = {}
for _, r in panel.iterrows():
    por_nombre.setdefault(r["id_panel"], []).append((r["anio"], r["puesto"]))

intecoba = [v for v in por_nombre.values()
            if any("INTECOBA" in p for _, p in v)]
ok("INTECOBA 2019 y 2023 comparten identidad pese al cambio de codigo",
   len(intecoba) == 1 and len(intecoba[0]) == 2, intecoba)
teresita = [v for v in por_nombre.values()
            if any("TERESITA" in p for _, p in v)]
ok("SANTA TERESITA tambien, aunque paso del 08 al 07",
   len(teresita) == 1 and len(teresita[0]) == 2, teresita)
narino = [v for v in por_nombre.values()
          if any("NARINO" in p for _, p in v)]
ok("ANTONIO NARINO queda solo en 2023", len(narino) == 1 and len(narino[0]) == 1,
   narino)
santos = [v for v in por_nombre.values()
          if any("SANTOS" in p for _, p in v)]
ok("ANTONIA SANTOS queda solo en 2019", len(santos) == 1 and len(santos[0]) == 1,
   santos)
ok("los que emparejan quedan en_panel",
   int(panel["en_panel"].sum()) == 4, panel[["anio", "puesto", "en_panel"]].to_dict("records"))
ok("los que no emparejan NO quedan en_panel",
   int((~panel["en_panel"]).sum()) == 2)

# La prueba clave: si se hubiera usado cod_puesto, el 04 de 2019 y el 04 de 2023
# habrian quedado juntos, que es el error que se quiere evitar.
p04 = panel[panel["cod_puesto"] == "04"]
ok("el puesto 04 de 2019 y el de 2023 NO comparten identidad",
   p04["id_panel"].nunique() == 2, p04[["anio", "puesto", "id_panel"]].to_dict("records"))

print("\n== desglose por puesto ==")
d = pd.DataFrame([
    fila(cod_candidato="00001", clase_opcion="candidatura", votos="100", mesa="1"),
    fila(cod_candidato="00002", clase_opcion="candidatura", votos="50", mesa="1"),
    fila(cod_candidato="00000", clase_opcion="voto_de_lista_no_preferente",
         candidato="PARTIDO A", votos="30", mesa="1"),
    fila(cod_candidato="00996", clase_opcion="opcion_especial",
         candidato="VOTOS EN BLANCO", votos="20", mesa="1"),
    fila(cod_candidato="00997", clase_opcion="opcion_especial",
         candidato="VOTOS NULOS", votos="7", mesa="1"),
    fila(cod_candidato="00998", clase_opcion="opcion_especial",
         candidato="VOTOS NO MARCADOS", votos="3", mesa="2"),
])
larga2, inf2 = prep.unificar({"2023_CONCEJO": d})
des = prep.desglose_por_puesto(larga2)
r = des.iloc[0]
ok("depositados = 210", int(r["votos_depositados"]) == 210, r["votos_depositados"])
ok("validos = 200 (incluye blanco, excluye nulo y no marcado)",
   int(r["votos_validos"]) == 200, r["votos_validos"])
ok("no validos = 10", int(r["votos_no_validos"]) == 10, r["votos_no_validos"])
ok("identidad validos+no validos=depositados",
   int(r["votos_validos"] + r["votos_no_validos"]) == int(r["votos_depositados"]))
ok("votos a candidatos = 150", int(r["votos_a_candidatos"]) == 150)
ok("votos de lista = 30", int(r["votos_de_lista"]) == 30)
ok("cuenta 2 mesas", int(r["mesas"]) == 2, r["mesas"])
ok("cuenta 2 candidatos con voto", int(r["candidatos_con_voto"]) == 2)

print("\n== indicadores ==")
pe = ind.partido_por_eleccion(larga2)
ok("una sola lista en el ejemplo", len(pe) == 1, pe.to_dict("records"))
ok("la lista no es cerrada porque tiene voto preferente",
   not bool(pe.iloc[0]["sin_voto_preferente_observado"]))

# HHI y NEP con un caso de aritmetica conocida
part = pd.DataFrame([
    {"anio": "2023", "corporacion": "CONCEJO", "nombre_partido": "A", "votos": 25,
     "sin_voto_preferente_observado": False},
    {"anio": "2023", "corporacion": "CONCEJO", "nombre_partido": "B", "votos": 25,
     "sin_voto_preferente_observado": False},
    {"anio": "2023", "corporacion": "CONCEJO", "nombre_partido": "C", "votos": 25,
     "sin_voto_preferente_observado": False},
    {"anio": "2023", "corporacion": "CONCEJO", "nombre_partido": "D", "votos": 25,
     "sin_voto_preferente_observado": False},
])
c = ind.concentracion_por_eleccion(part)
ok("cuatro listas iguales dan HHI 0.25", abs(c.iloc[0]["hhi"] - 0.25) < 1e-9,
   c.iloc[0]["hhi"])
ok("y numero efectivo de partidos = 4",
   abs(c.iloc[0]["numero_efectivo_de_partidos"] - 4.0) < 1e-9,
   c.iloc[0]["numero_efectivo_de_partidos"])

part2 = pd.concat([part, part.assign(anio="2019")], ignore_index=True)
part2.loc[part2["anio"] == "2019", "votos"] = [40, 30, 20, 10]
v = ind.volatilidad(part2)
# 2019: 40/30/20/10 ; 2023: 25/25/25/25 -> |15|+|5|+|5|+|15| = 40 ; /2 = 20
ok("volatilidad de Pedersen = 20", abs(v.iloc[0]["volatilidad_pedersen"] - 20.0) < 1e-9,
   v.to_dict("records"))
ok("ninguna lista entro ni salio", int(v.iloc[0]["listas_que_entraron"]) == 0
   and int(v.iloc[0]["listas_que_salieron"]) == 0)

print("\n== estabilidad de codigos: detecta el problema que motivo el panel ==")
e = ind.estabilidad_de_codigos(larga, "cod_puesto", "puesto")
ok("reporta el codigo 04 con dos nombres distintos",
   "04" in set(e["codigo"]), e.to_dict("records"))

print("\n== marcar extremos: no borra nada ==")
pe2 = des.copy()
pe2["potencial_electoral"] = [100.0]
pe2["participacion"] = [210.0]
pe2["abstencion"] = [-110.0]
mk = prep.marcar_extremos(pe2)
ok("marca la participacion imposible", bool(mk.iloc[0]["marca_participacion_imposible"]))
ok("pero conserva la fila", len(mk) == len(pe2))
ok("y conserva el valor original sin recortar", float(mk.iloc[0]["participacion"]) == 210.0)

print("\n" + "=" * 62)
print("FALLOS: %d" % len(fallos))
for f in fallos:
    print("  - " + f)

print("\n== regresion: cod_candidato no identifica a un candidato ==")
# Dos listas, cada una con sus candidatos 00001 y 00002: son CUATRO personas.
filas_c = []
for part in ("00001", "00002"):
    for c in ("00001", "00002"):
        filas_c.append(fila(cod_partido=part, partido="PARTIDO " + part,
                            cod_candidato=c, candidato="NOMBRE %s %s" % (part, c),
                            clase_opcion="candidatura", votos="10"))
dc = pd.DataFrame(filas_c)
lc, _ = prep.unificar({"2023_CONCEJO": dc})
des_c = prep.desglose_por_puesto(lc)
ok("cuenta 4 candidatos, no 2", int(des_c.iloc[0]["candidatos_con_voto"]) == 4,
   des_c.iloc[0]["candidatos_con_voto"])
ok("cuenta 2 listas", int(des_c.iloc[0]["listas_con_voto"]) == 2,
   des_c.iloc[0]["listas_con_voto"])
of = ind.oferta_electoral(lc)
ok("la oferta tambien cuenta 4", int(of.iloc[0]["candidatos_con_al_menos_un_voto"]) == 4,
   of.iloc[0]["candidatos_con_al_menos_un_voto"])
ok("y 2 listas", int(of.iloc[0]["listas_con_candidatos"]) == 2)
ce = ind.candidato_por_eleccion(lc)
ok("candidato_por_eleccion ya daba 4 filas", len(ce) == 4, len(ce))

print("\n== volatilidad: marca cuando no es interpretable ==")
pa = pd.DataFrame([
    {"anio": "2019", "corporacion": "ALCALDE", "nombre_partido": "NUEVA BARRANCA",
     "votos": 100, "sin_voto_preferente_observado": False},
    {"anio": "2023", "corporacion": "ALCALDE", "nombre_partido": "NUEVO CAPITULO",
     "votos": 100, "sin_voto_preferente_observado": False}])
vv = ind.volatilidad(pa)
ok("volatilidad 100 cuando no hay listas comunes",
   vv.iloc[0]["volatilidad_pedersen"] == 100.0, vv.iloc[0]["volatilidad_pedersen"])
ok("y queda marcada como NO INTERPRETABLE",
   vv.iloc[0]["lectura"].startswith("NO INTERPRETABLE"), vv.iloc[0]["lectura"])
pb = pd.DataFrame([
    {"anio": "2019", "corporacion": "CONCEJO", "nombre_partido": "A", "votos": 60,
     "sin_voto_preferente_observado": False},
    {"anio": "2019", "corporacion": "CONCEJO", "nombre_partido": "B", "votos": 40,
     "sin_voto_preferente_observado": False},
    {"anio": "2023", "corporacion": "CONCEJO", "nombre_partido": "A", "votos": 40,
     "sin_voto_preferente_observado": False},
    {"anio": "2023", "corporacion": "CONCEJO", "nombre_partido": "B", "votos": 60,
     "sin_voto_preferente_observado": False}])
vb = ind.volatilidad(pb)
ok("con listas continuas queda interpretable",
   vb.iloc[0]["lectura"] == "interpretable", vb.iloc[0]["lectura"])
ok("y la volatilidad es 20", vb.iloc[0]["volatilidad_pedersen"] == 20.0,
   vb.iloc[0]["volatilidad_pedersen"])

print("\n" + "=" * 62)
print("FALLOS FINALES: %d" % len(fallos))
for f in fallos:
    print("  - " + f)
