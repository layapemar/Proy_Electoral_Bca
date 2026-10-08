# -*- coding: utf-8 -*-
"""Construye los datasets analíticos a partir de las tablas de ingesta.

    python src/transformacion/construir_datasets.py

Escribe en `datos/analitico/`. Nada de lo que hay en `datos/procesados/` se modifica, y
`datos/brutos/` no se toca en absoluto.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.transformacion import indicadores as ind  # noqa: E402
from src.transformacion import preparacion as prep  # noqa: E402


def raiz_del_proyecto() -> Path:
    aqui = Path(__file__).resolve()
    for p in aqui.parents:
        if (p / "src").is_dir() and (p / "datos").is_dir():
            return p
    return Path.cwd()


def escribir(d: pd.DataFrame, ruta: Path, etiqueta: str) -> dict:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(ruta, index=False, encoding="utf-8-sig")
    print("     %-44s %6d filas x %3d columnas" % (ruta.name, len(d), len(d.columns)))
    return {"dataset": etiqueta, "archivo": ruta.name, "filas": len(d),
            "columnas": len(d.columns)}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    raiz = raiz_del_proyecto()
    salida = raiz / "datos" / "analitico"
    salida.mkdir(parents=True, exist_ok=True)
    inventario = []

    print("=" * 74)
    print("CONSTRUCCIÓN DE LOS DATASETS ANALÍTICOS")
    print("=" * 74)

    print("\n1. Lectura de las tablas de votos")
    rutas = sorted((raiz / "datos" / "procesados" / "votos").rglob("*.csv"))
    if not rutas:
        print("   no hay tablas de votos en datos/procesados/votos")
        return 1
    tablas = {}
    for r in rutas:
        d = prep.leer_csv(r)
        etiqueta = "%s_%s" % (d["anio"].iloc[0], d["corporacion"].iloc[0])
        tablas[etiqueta] = d
        print("   %-26s %7d filas" % (etiqueta, len(d)))

    print("\n2. Unificación, normalización y marcado")
    larga, informe = prep.unificar(tablas)
    print("   tabla larga: %d filas, %d columnas" % (len(larga), len(larga.columns)))
    for _, r in informe.iterrows():
        extra = (" | centinelas: " + r["texto_centinela"]) if r["texto_centinela"] else ""
        print("   %-26s %7d filas  %3d puestos  %6d mesas  %7d votos%s"
              % (r["eleccion"], r["filas"], r["puestos"], r["mesas"], r["votos"],
                 extra))

    print("\n3. Identidad de panel (nombres dentro de la zona)")
    panel, informe_panel = prep.construir_panel(larga)
    for _, r in informe_panel.iterrows():
        marca = "  <- referencia" if r["es_referencia"] else ""
        print("   %s: %d puestos, %d emparejados, %d sin emparejar%s"
              % (r["anio"], r["puestos"], r["emparejados"], r["sin_emparejar"], marca))
    completos = panel[panel["en_panel_completo"]]["id_panel"].nunique()
    enpanel = panel[panel["en_panel"]]["id_panel"].nunique()
    print("   identidades distintas: %d | en más de un año: %d | en todos los años: %d"
          % (panel["id_panel"].nunique(), enpanel, completos))

    print("\n4. Tabla puesto × elección")
    pe = prep.desglose_por_puesto(larga)
    pe, informe_censo = prep.unir_censo(pe, raiz)
    pe, informe_geo = prep.unir_geografia(pe, raiz)
    ident = panel[["anio", "id_puesto", "id_panel", "en_panel",
                   "en_panel_completo", "anios_presentes",
                   "parecido_con_referencia"]].drop_duplicates(["anio", "id_puesto"])
    pe = pe.merge(ident, on=["anio", "id_puesto"], how="left")
    pe = prep.marcar_extremos(pe)
    print("   potencial electoral: %d con, %d sin"
          % (informe_censo["con_potencial"], informe_censo["sin_potencial"]))
    print("   coordenada: %d filas | área del territorio: %d filas"
          % (informe_geo.get("con_coordenada", 0), informe_geo.get("con_area", 0)))
    marcas = [c for c in pe.columns if c.startswith("marca_")]
    for m in marcas:
        n = int(pe[m].sum())
        if n:
            print("   %-38s %d filas marcadas" % (m, n))

    print("\n5. Indicadores derivados")
    por_eleccion = ind.agregado_por_eleccion(pe)
    por_territorio = ind.agregado_por_territorio(pe)
    partidos = ind.partido_por_eleccion(larga)
    concentracion = ind.concentracion_por_eleccion(partidos)
    vol = ind.volatilidad(partidos)
    oferta = ind.oferta_electoral(larga)
    candidatos = ind.candidato_por_eleccion(larga)
    conc_terr = ind.concentracion_territorial(larga)
    estab_partido = ind.estabilidad_de_codigos(larga, "cod_partido", "nombre_partido")
    estab_puesto = ind.estabilidad_de_codigos(larga, "cod_puesto", "puesto")
    panel_part = ind.panel_de_participacion(pe, panel)
    territorios = prep.tabla_de_territorios(
        pe.drop_duplicates(["id_puesto", "territorio"]))

    print("\n6. Escritura")
    inventario.append(escribir(larga, salida / "votos_mesa.csv",
                               "voto por mesa y opción, todas las elecciones"))
    inventario.append(escribir(pe, salida / "puesto_eleccion.csv",
                               "TABLA PRINCIPAL: un puesto por elección"))
    inventario.append(escribir(panel, salida / "panel_puestos.csv",
                               "identidad estable de puesto entre años"))
    inventario.append(escribir(por_eleccion, salida / "agregado_eleccion.csv",
                               "totales del distrito por elección"))
    inventario.append(escribir(por_territorio, salida / "agregado_territorio.csv",
                               "totales por comuna y corregimiento"))
    inventario.append(escribir(partidos, salida / "partido_eleccion.csv",
                               "votos de cada lista por elección"))
    inventario.append(escribir(concentracion, salida / "concentracion_eleccion.csv",
                               "HHI y número efectivo de partidos"))
    inventario.append(escribir(vol, salida / "volatilidad.csv",
                               "índice de Pedersen entre elecciones"))
    inventario.append(escribir(oferta, salida / "oferta_electoral.csv",
                               "listas y candidatos que compitieron"))
    inventario.append(escribir(candidatos, salida / "candidato_eleccion.csv",
                               "votos de cada candidatura"))
    if len(conc_terr):
        inventario.append(escribir(conc_terr, salida / "concentracion_territorial.csv",
                                   "concentración territorial por candidatura"))
    inventario.append(escribir(territorios, salida / "territorios.csv",
                               "dimensión de territorios"))
    inventario.append(escribir(panel_part, salida / "panel_participacion.csv",
                               "participación del mismo puesto entre años"))
    inventario.append(escribir(informe, salida / "informe_unificacion.csv",
                               "qué se leyó y qué se transformó"))
    inventario.append(escribir(informe_panel, salida / "informe_panel.csv",
                               "cuántos puestos emparejaron por año"))
    if len(estab_puesto):
        inventario.append(escribir(estab_puesto, salida / "codigos_de_puesto_reusados.csv",
                                   "evidencia de la renumeración de puestos"))
    if len(estab_partido):
        inventario.append(escribir(estab_partido,
                                   salida / "codigos_de_partido_reusados.csv",
                                   "códigos de partido con más de un nombre"))

    # Matriz por puesto y apoyo por lista, para el Concejo de cada año.
    for anio in sorted(set(pe[pe["corporacion"] == "CONCEJO"]["anio"])):
        m = ind.matriz_por_puesto(pe, anio, "CONCEJO")
        inventario.append(escribir(
            m, salida / f"matriz_puesto_concejo_{anio}.csv",
            f"variables por puesto, Concejo {anio}, para agrupar y mapear"))
        a = ind.apoyo_de_partido_por_puesto(larga, anio, "CONCEJO")
        inventario.append(escribir(
            a, salida / f"apoyo_por_lista_concejo_{anio}.csv",
            f"proporción de voto de cada lista por puesto, Concejo {anio}"))

    print("\n7. Controles")
    ctrl = prep.controles(larga, pe, panel, informe_panel, informe_censo)
    escribir(ctrl, salida / "controles_preparacion.csv", "controles")
    for _, r in ctrl.iterrows():
        print("   [%s] %-52s %s" % ("ok" if r["pasa"] else "XX", r["control"],
                                    r["valor"]))

    escribir(pd.DataFrame(inventario), salida / "inventario_datasets.csv",
             "inventario")

    fallos = ctrl[(~ctrl["pasa"]) & (ctrl["criticidad"] == "Alta")]
    print("\n" + "=" * 74)
    print("Datasets en datos/analitico/")
    if len(fallos):
        print("\nATENCIÓN: %d control(es) de criticidad alta no pasaron." % len(fallos))
        for _, r in fallos.iterrows():
            print("  - %s: %s (se esperaba %s)"
                  % (r["control"], r["valor"], r["esperado"]))
        print("\nLos datasets quedaron escritos, pero NO se deben usar hasta resolver")
        print("eso: un control alto que falla significa que algún número está mal.")
    else:
        print("\nTodos los controles de criticidad alta pasaron.")
    print("=" * 74)
    return 1 if len(fallos) else 0


if __name__ == "__main__":
    raise SystemExit(main())
