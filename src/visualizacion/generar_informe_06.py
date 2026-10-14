"""Genera el informe narrativo HTML del cuaderno 06 (patrones de comunas y mirada a 2027).

Las cifras provienen de las salidas del cuaderno notebooks/06_patrones_comunas_y_mirada_2027.ipynb.
Uso: python src/visualizacion/generar_informe_06.py
"""
import base64
import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "entregables" / "informes" / "informe_hallazgos_06.html"

AZUL, NARANJA, VERDE, GRIS, ROJO = "#1f3a5f", "#e07a1f", "#2a9d8f", "#b8c0cc", "#c0392b"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#888", "figure.dpi": 130})
COMUNAS = [f"C{i}" for i in range(1, 8)]


def b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def etiquetas(ax, barras, fmt="{:.1f}", sufijo=""):
    for b in barras:
        ax.annotate(fmt.format(b.get_height()) + sufijo, (b.get_x() + b.get_width() / 2, b.get_height()),
                    ha="center", va="bottom", fontsize=9.5, xytext=(0, 2), textcoords="offset points")


def g_participacion():
    n = ["Local\n2019", "Local\n2023", "Congreso\n2022", "Congreso\n2026",
         "Presid. 2026\n1.ª vuelta", "Presid. 2026\n2.ª vuelta"]
    v = [69.6, 70.5, 60.3, 57.6, 64.5, 69.1]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    bs = ax.bar(n, v, color=[AZUL, AZUL, NARANJA, NARANJA, VERDE, VERDE])
    etiquetas(ax, bs, sufijo="%")
    ax.set_ylim(0, 80); ax.set_ylabel("Participación (%)")
    return b64(fig)


def g_heatmap():
    cols = ["Concejo\n2019", "Concejo\n2023", "Congreso\n2026", "Presid.\n2026 1.ª"]
    m = np.array([[70.6, 71.1, 60.9, 66.0], [59.5, 61.6, 52.9, 60.8], [70.0, 71.2, 57.1, 64.3],
                  [70.0, 70.6, 59.7, 66.6], [72.8, 74.1, 59.9, 66.9], [71.3, 69.5, 51.8, 57.7],
                  [71.8, 72.0, 53.8, 61.6]])
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    im = ax.imshow(m, cmap="YlGnBu", aspect="auto", vmin=50, vmax=76)
    ax.set_xticks(range(4), cols); ax.set_yticks(range(7), [f"Comuna {i}" for i in range(1, 8)])
    for i in range(7):
        for j in range(4):
            ax.text(j, i, f"{m[i, j]:.0f}", ha="center", va="center",
                    color="white" if m[i, j] > 66 else "#222", fontsize=10)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.colorbar(im, ax=ax, label="Participación (%)", shrink=0.8)
    return b64(fig)


def g_rolloff():
    r19 = [0.73, 0.88, 1.86, 1.83, 1.70, 2.10, 1.48]
    r23 = [2.10, 1.13, 2.18, 1.42, 2.12, 2.45, 2.76]
    x = np.arange(7)
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.bar(x - 0.2, r19, 0.4, color=GRIS, label="2019")
    ax.bar(x + 0.2, r23, 0.4, color=NARANJA, label="2023")
    ax.set_xticks(x, COMUNAS); ax.set_ylabel("% de voto que no llega al Concejo")
    ax.legend(frameon=False)
    return b64(fig)


def g_censo_brecha():
    crec = [-1.0, -6.1, 6.8, 2.1, 7.5, 12.7, 33.6]
    brecha = [10.3, 8.8, 14.1, 10.9, 14.2, 17.7, 18.2]
    fig, axs = plt.subplots(1, 2, figsize=(9.5, 3.6))
    axs[0].bar(COMUNAS, crec, color=[ROJO if c < 0 else AZUL for c in crec])
    axs[0].axhline(0, color="#555", lw=0.8)
    axs[0].set_title("Crecimiento del censo 2019→2026 (%)", fontsize=11)
    axs[1].bar(COMUNAS, brecha, color=[NARANJA if c > 15 else GRIS for c in brecha])
    axs[1].set_title("Brecha local − nacional (pts)", fontsize=11)
    fig.tight_layout()
    return b64(fig)


def g_etiqueta():
    fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.4))
    b = axs[0].bar(["Liberal", "Pacto\nHistórico"], [-0.07, 0.44], color=[GRIS, AZUL])
    axs[0].axhline(0, color="#555", lw=0.8); axs[0].set_ylim(-0.2, 0.6)
    axs[0].set_title("Correlación geografía\nConcejo vs Senado", fontsize=10.5)
    etiquetas(axs[0], b, "{:+.2f}")
    b = axs[1].bar(["2019", "2023"], [11.3, 8.4], color=NARANJA)
    axs[1].set_title("% del voto que va a listas\npresentes en ambos ciclos", fontsize=10.5)
    axs[1].set_ylim(0, 100); etiquetas(axs[1], b, "{:.1f}", "%")
    axs[2].pie([68, 3], labels=["Cambió de\npartido (68)", "Mismo (3)"], colors=[AZUL, GRIS],
               startangle=90, autopct="%1.0f%%", textprops={"fontsize": 9.5}, pctdistance=0.7,
               wedgeprops={"width": 0.45})
    axs[2].set_title("Candidatos que repiten\nentre ciclos (71)", fontsize=10.5)
    fig.tight_layout()
    return b64(fig)


def g_fortin():
    fig, ax = plt.subplots(figsize=(6, 3.2))
    b = ax.barh(["Mediana de\nlos electos", "Ceferino\nGaray"], [0.029, 0.213], color=[GRIS, NARANJA])
    ax.set_xlabel("Concentración territorial del voto (HHI)")
    for r in b:
        ax.annotate(f"{r.get_width():.3f}", (r.get_width(), r.get_y() + r.get_height() / 2),
                    va="center", xytext=(4, 0), textcoords="offset points")
    ax.set_xlim(0, 0.26)
    return b64(fig)


def g_piso():
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    fig_x = ["2019", "2023"]
    b = ax.bar(fig_x, [23.0, 23.1], color=AZUL, width=0.5)
    etiquetas(ax, b, "{:.1f}", "% de la cifra")
    for i, (piso, cifra) in enumerate([(1013, 4412), (932, 4042)]):
        ax.text(i, 11, f"piso {piso:,}\ncifra {cifra:,}".replace(",", "."), ha="center", color="white", fontsize=10)
    ax.set_ylim(0, 30); ax.set_ylabel("Piso del último concejal electo")
    return b64(fig)


def g_franjas():
    labels = ["0 figuras", "1 figura", "2 o más figuras"]
    con = np.array([0, 5, 16]); sin = np.array([15, 4, 0])
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(labels, con, color=VERDE, label="Sacó curul")
    ax.barh(labels, sin, left=con, color=GRIS, label="No sacó curul")
    for i, (c, s) in enumerate(zip(con, sin)):
        ax.text(c + s + 0.3, i, f"{c}/{c + s}", va="center", fontweight="bold")
    ax.invert_yaxis(); ax.set_xlim(0, 19); ax.set_xlabel("Listas abiertas, 2019 y 2023")
    ax.legend(frameon=False, loc="lower right")
    return b64(fig)


def g_banca():
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    b = ax.bar(["Banca de 4 a 6", "Banca de 7 a 12"], [0, 100], color=[GRIS, VERDE], width=0.5)
    ax.set_ylabel("% de listas con 1 figura que sacó curul"); ax.set_ylim(0, 115)
    ax.text(0, 4, "0 de 4", ha="center", fontweight="bold")
    ax.text(1, 104, "5 de 5", ha="center", fontweight="bold")
    return b64(fig)


def g_cambio():
    tipos = ["Fuerte\n(≥930)", "Medio\n(500–929)", "Seria\n(300–499)", "Campaña\n(100–299)"]
    a19 = [3.0, 6.2, 11.6, 24.6]; a23 = [3.1, 6.0, 10.5, 23.8]
    x = np.arange(4)
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.bar(x - 0.2, a19, 0.4, color=GRIS, label="2019")
    ax.bar(x + 0.2, a23, 0.4, color=AZUL, label="2023")
    ax.set_xticks(x, tipos); ax.set_ylabel("Candidatos necesarios para 1 curul")
    ax.legend(frameon=False)
    return b64(fig)


def g_quemadas():
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.pie([33, 38, 4], labels=["Electas (33)", "Quemadas por su\npropia lista (38)", "Lista sin curul (4)"],
           colors=[VERDE, NARANJA, GRIS], startangle=90, autopct="%1.0f%%",
           wedgeprops={"width": 0.45}, pctdistance=0.78, textprops={"fontsize": 10})
    ax.text(0, 0, "75\nfiguras", ha="center", va="center", fontsize=12, fontweight="bold")
    return b64(fig)


def g_fragmenta():
    fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.2))
    for ax, t, v in zip(axs, ["Nº efectivo\nde listas", "Candidatos", "Voto mediano\npor candidato"],
                        [(12.8, 16.0), (275, 359), (178, 113)]):
        b = ax.bar(["2019", "2023"], v, color=[GRIS, NARANJA])
        ax.set_title(t, fontsize=10.5); etiquetas(ax, b, "{:.0f}" if v[0] > 20 else "{:.1f}")
        ax.set_ylim(0, max(v) * 1.2)
    fig.tight_layout()
    return b64(fig)


def g_2027():
    t23 = [71.3, 61.8, 71.3, 70.6, 74.3, 69.4, 71.9]
    t27 = [72.2, 64.1, 72.3, 70.9, 75.6, 67.2, 71.9]
    x = np.arange(7)
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.bar(x - 0.2, t23, 0.4, color=GRIS, label="2023 (real)")
    ax.bar(x + 0.2, t27, 0.4, color=AZUL, label="2027 (escenario de tendencia)")
    ax.set_xticks(x, COMUNAS); ax.set_ylim(50, 80); ax.set_ylabel("Participación (%)")
    ax.legend(frameon=False, loc="upper left", ncol=2)
    return b64(fig)


# (capítulo, número, titular, gráfica, texto, nivel)
CAPITULOS = [
    ("1 · El votante: quién va a las urnas", [
        ("Barranca se moviliza más por lo local que por lo nacional", g_participacion,
         "La participación en Alcaldía y Concejo ronda el <b>70 %</b>. El Congreso es lo que menos arrastra "
         "(<b>60 % → 57,6 %</b>, a la baja) y la Presidencia sube hasta igualar lo local en segunda vuelta (69,1 %).",
         "A/B"),
        ("El mapa de la abstención es estructural, no coyuntural", g_heatmap,
         "La Comuna 2 es la menos participativa en <b>todas</b> las elecciones y la Comuna 5 la más fiel. "
         "El orden se repite entre ciclos (Spearman 0,72): cambia el nivel, no la jerarquía.", "B"),
        ("Quien va a votar, vota todo — pero el Concejo se queda sin marcar", g_rolloff,
         "Casi nadie deposita solo Alcaldía (0,15–0,18 %), pero el Concejo recibe ~2 % menos votos válidos "
         "(2.265 tarjetas en 2023). La fuga <b>subió en 6 de 7 comunas</b>, con el mayor salto en la Comuna 7 "
         "(1,5 % → 2,8 %): un margen disputable.", "A/B"),
        ("El electorado se corre hacia la periferia, y allí se vota para lo local", g_censo_brecha,
         "Las Comunas 6 y 7 crecen (la 7, <b>+34 %</b>), son las más jóvenes y tienen la mayor brecha local-nacional "
         "(~18 pts): se activan sobre todo en territoriales. La Comuna 2 se encoge y su abstención es pareja en todo: "
         "<b>apatía, no movilización</b>.", "A/B"),
    ]),
    ("2 · La lista: cómo se gana una curul", [
        ("El piso del concejal es una fracción estable de la cifra repartidora", g_piso,
         "El último electo sacó 1.013 votos (2019) y 932 (2023), pero en ambos casos el <b>23 %</b> de la cifra. "
         "Para 2027 el umbral no es “930 votos”, es ~23 % de la cifra de ese año.", "A/B"),
        ("Sin figura no hay curul; con dos, siempre la hay", g_franjas,
         "Ninguna de las 15 listas sin figura (≥930 votos) sacó curul; las 16 con dos o más sí. "
         "La franja de una sola figura es la zona de riesgo.", "B"),
        ("Con una sola figura, decide la banca", g_banca,
         "Entre las 9 listas con una figura, ninguna con banca de 4–6 candidaturas ganó y las 5 con banca de 7 o más sí. "
         "Una figura sola no levanta una lista (el corte es el borde observado, no una ley).", "B"),
        ("Cada tipo de candidato tiene un “precio” estable en curules", g_cambio,
         "Una curul ≈ <b>3 figuras ≈ 6 medios ≈ 24 campañas</b>, casi idéntico en 2019 y 2023 aunque la cifra bajó 8 %. "
         "Sirve para dimensionar el objetivo de votos de una lista.", "B"),
        ("Amontonar figuras no suma: dos de cada tres se queman", g_quemadas,
         "De 75 figuras, solo 33 salieron electas; <b>38 se quemaron por sobrecarga de su propia lista</b>. "
         "Sus votos son por el mismo territorio (solapamiento ~0,77), así que más figuras compiten, no suman. "
         "Entrar como n.º 1 de una lista mediana vale más que ser el n.º 4 de una grande.", "A/B"),
        ("Hay concejales de un solo puesto (y la geografía no decide quién gana)", g_fortin,
         "Ceferino Garay sacó el <b>42 %</b> de su votación en un único puesto rural (HHI 7× la mediana). "
         "Pero entre figuras electas y quemadas la concentración territorial es igual (0,148 vs 0,148): "
         "el territorio sirve para conseguir votos, no para decidir la curul. <i>(resultado nulo, reportado igual)</i>", "A/B"),
    ]),
    ("3 · El sistema: la etiqueta no pesa, la competencia se fragmenta", [
        ("El Concejo se gana con nombre propio, no con partido", g_etiqueta,
         "Solo 1 de 18 listas de 2019 compitió también en 2023 y el <b>96 %</b> de los candidatos que repiten "
         "cambió de partido. El Liberal no alinea su voto local con el de Senado (r = −0,07). "
         "La etiqueta es un vehículo que se alquila cada elección; ninguna comuna es fiel a una marca.", "A/B"),
        ("La oferta se atomiza: más listas, más candidatos, menos votos cada uno", g_fragmenta,
         "El número efectivo de listas pasó de 12,8 a 16,0 y los candidatos de 275 a 359, mientras el voto mediano "
         "por candidato cayó de 178 a 113. Competir en 2027 será más fragmentado.", "A/B"),
    ]),
    ("4 · Mirada a 2027", [
        ("2027 se juega sobre un mapa conocido, con la periferia pesando más", g_2027,
         "Bajo persistencia o tendencia, la Comuna 2 sigue última y la 5 primera, pero el peso del censo se "
         "desplaza a las Comunas 6 y 7. <b>No es un pronóstico</b>: son dos escenarios sobre dos ciclos de datos.", "C"),
    ]),
]

CONCLUSIONES = [
    "<b>Mira a la periferia:</b> las Comunas 6 y 7 crecen y se activan para lo local.",
    "<b>Ancla + banca:</b> al menos una figura de ~23 % de la cifra, o dos; y una banca de 7+ candidaturas reales.",
    "<b>No amontones figuras:</b> la figura n.º N+1 compite por las mismas N curules.",
    "<b>Construye marca propia:</b> la etiqueta del partido no hereda votos entre ciclos.",
    "<b>Disputa el voto que se pierde:</b> el roll-off del Concejo (~2 %) es un margen movible.",
]

CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;color:#222;background:#f4f6f9;margin:0;line-height:1.5}
header{background:#1f3a5f;color:#fff;padding:48px 20px;text-align:center}
header h1{margin:0 0 8px;font-size:2rem} header p{margin:4px 0;opacity:.85}
main{max-width:900px;margin:0 auto;padding:20px}
.cap{margin:44px 0 12px;font-size:1.35rem;color:#1f3a5f;border-bottom:3px solid #e07a1f;padding-bottom:6px}
.card{background:#fff;border-radius:10px;padding:22px 26px;margin:18px 0;box-shadow:0 1px 4px rgba(0,0,0,.08);break-inside:avoid}
.card h3{margin:0 0 12px;font-size:1.15rem;color:#1f3a5f}
.num{display:inline-block;background:#e07a1f;color:#fff;border-radius:50%;width:28px;height:28px;text-align:center;line-height:28px;margin-right:8px;font-size:.9rem}
.card img{max-width:100%;display:block;margin:0 auto 12px}
.card p{margin:0}
.tag{float:right;font-size:.75rem;background:#e8edf4;color:#1f3a5f;border-radius:10px;padding:2px 9px}
.cierre{background:#1f3a5f;color:#fff;border-radius:10px;padding:24px 30px;margin:40px 0}
.cierre h2{margin-top:0} .cierre li{margin:8px 0}
footer{font-size:.8rem;color:#666;text-align:center;padding:20px}
.intro{font-size:1.05rem}
@media print{body{background:#fff}.card{box-shadow:none;border:1px solid #ddd}}
"""


def main():
    partes = []
    n = 0
    for cap, items in CAPITULOS:
        partes.append(f'<h2 class="cap">{cap}</h2>')
        for titulo, fn, texto, nivel in items:
            n += 1
            partes.append(
                f'<section class="card"><span class="tag">Evidencia {nivel}</span><h3><span class="num">{n}</span>{titulo}</h3>'
                f'<img src="data:image/png;base64,{fn()}" alt="{titulo}"><p>{texto}</p></section>')
    cierre = "".join(f"<li>{c}</li>" for c in CONCLUSIONES)
    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Barrancabermeja: patrones electorales y mirada a 2027</title><style>{CSS}</style></head><body>
<header><h1>Barrancabermeja vota: quién, cómo y qué esperar en 2027</h1>
<p>Observatorio de Dinámicas Electorales de Barrancabermeja</p><p>Laura Pérez · Ciencia de datos</p></header>
<main><p class="intro">Una historia en cuatro actos con datos oficiales de la Registraduría y el CNE: primero
<b>quién vota</b>, luego <b>cómo se gana una curul</b>, después <b>qué pasa con los partidos</b> y, al final,
<b>qué escenarios deja 2027</b>. Cada título es un hallazgo; la evidencia es A (hecho), B (inferencia sólida) o C (escenario).</p>
{''.join(partes)}
<section class="cierre"><h2>Lo que significa para 2027</h2><ul>{cierre}</ul></section></main>
<footer>Fuente: Registraduría Nacional y CNE; procesamiento propio (cuaderno 06). Análisis agregados por comuna; no describen votos individuales.</footer>
</body></html>"""
    SALIDA.write_text(html, encoding="utf-8")
    print(f"Informe generado: {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB, {n} hallazgos)")


if __name__ == "__main__":
    main()
