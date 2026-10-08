from pathlib import Path


def crear_estructura():
    """
    Crea la estructura inicial del proyecto:
    Observatorio de Dinámicas Electorales de Barrancabermeja.

    La carpeta raíz del proyecto será la misma carpeta donde
    se encuentre guardado este archivo crear_estructura.py.
    """

    # ============================================================
    # 1. RAÍZ DEL PROYECTO
    # ============================================================
    base = Path(__file__).resolve().parent

    print("\n" + "=" * 70)
    print("OBSERVATORIO ELECTORAL DE BARRANCABERMEJA")
    print("Creando estructura inicial del proyecto...")
    print(f"Raíz del proyecto: {base}")
    print("=" * 70 + "\n")

    # ============================================================
    # 2. ESTRUCTURA DE CARPETAS
    # ============================================================
    carpetas = [
        # --------------------------------------------------------
        # DATOS
        # --------------------------------------------------------
        "datos/brutos/registraduria/2015",
        "datos/brutos/registraduria/2018",
        "datos/brutos/registraduria/2019",
        "datos/brutos/registraduria/2022",
        "datos/brutos/registraduria/2023",
        "datos/brutos/registraduria/2026",
        "datos/brutos/registraduria/divipole",
        "datos/brutos/dane",
        "datos/brutos/cne",
        "datos/brutos/alcaldia_barrancabermeja",
        "datos/brutos/moe",
        "datos/brutos/otras_fuentes",

        "datos/intermedios",
        "datos/procesados",
        "datos/geograficos",

        # --------------------------------------------------------
        # NOTEBOOKS
        # --------------------------------------------------------
        "notebooks",

        # --------------------------------------------------------
        # CÓDIGO REUTILIZABLE
        # --------------------------------------------------------
        "src/ingesta",
        "src/limpieza",
        "src/transformacion",
        "src/features",
        "src/geoespacial",
        "src/analisis",
        "src/modelos",
        "src/visualizacion",
        "src/utils",

        # --------------------------------------------------------
        # CONFIGURACIÓN
        # --------------------------------------------------------
        "config",

        # --------------------------------------------------------
        # ENTREGABLES / OUTPUTS
        # --------------------------------------------------------
        "entregables/graficos",
        "entregables/mapas",
        "entregables/tablas",
        "entregables/informes",
        "entregables/dashboards",

        # --------------------------------------------------------
        # DOCUMENTACIÓN
        # --------------------------------------------------------
        "docs",
        "docs/diccionario_datos",
        "docs/fuentes",
        "docs/metodologia",

        # --------------------------------------------------------
        # TESTS
        # --------------------------------------------------------
        "tests",

    ]

    for carpeta in carpetas:
        ruta = base / carpeta
        ruta.mkdir(parents=True, exist_ok=True)
        print(f"✅ Creada/verificada: {ruta.relative_to(base)}")

    # ============================================================
    # 3. ARCHIVOS .gitkeep
    #    Permiten conservar carpetas vacías en Git.
    # ============================================================
    carpetas_gitkeep = [
        "datos/brutos",
        "datos/intermedios",
        "datos/procesados",
        "datos/geograficos",
        "entregables/graficos",
        "entregables/mapas",
        "entregables/tablas",
        "entregables/informes",
        "entregables/dashboards",
    ]

    for carpeta in carpetas_gitkeep:
        gitkeep = base / carpeta / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    # ============================================================
    # 4. ARCHIVOS __init__.py
    #    Facilitan importar funciones desde src/.
    # ============================================================
    carpetas_python = [
        "src",
        "src/ingesta",
        "src/limpieza",
        "src/transformacion",
        "src/features",
        "src/geoespacial",
        "src/analisis",
        "src/modelos",
        "src/visualizacion",
        "src/utils",
    ]

    for carpeta in carpetas_python:
        init_path = base / carpeta / "__init__.py"
        if not init_path.exists():
            init_path.touch()

    # ============================================================
    # 5. CREAR .gitignore
    # ============================================================
    gitignore_path = base / ".gitignore"

    if not gitignore_path.exists():
        gitignore_content = """# Sistema operativo
desktop.ini
Thumbs.db
.DS_Store

# Variables de entorno y secretos locales
.env
.env.*
!.env.example
!.env.template
*.pem
*.key
*.p12
*.pfx
secrets/
.aws/

# Entornos virtuales
/.venv/
/venv/
/env/

# Python y herramientas de desarrollo
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
build/
dist/
*.egg-info/

# Jupyter
.ipynb_checkpoints/

# Configuración local de editores
.vscode/
.idea/

# Registros y bases locales
*.log
*.db
*.sqlite
*.sqlite3
*.duckdb

# Datos descargados o generados: mantener solo documentación y estructura
/datos/**
!/datos/**/
!/datos/**/.gitkeep
!/datos/**/README.md

# Entregables generados: mantener solo documentación y estructura
/entregables/**
!/entregables/**/
!/entregables/**/.gitkeep
!/entregables/**/README.md
"""
        gitignore_path.write_text(gitignore_content, encoding="utf-8")
        print(f"\n✅ Creado: {gitignore_path.name}")
    else:
        print(f"\nℹ️ Ya existe: {gitignore_path.name}")

    # ============================================================
    # 6. README DEL PROYECTO
    # ============================================================
    readme_path = base / "README.md"

    if not readme_path.exists():
        readme_content = """# Observatorio de Dinámicas Electorales de Barrancabermeja

Proyecto de ciencia de datos y análisis electoral enfocado en Barrancabermeja,
Santander, Colombia.

## Objetivo inicial

Construir una base de datos histórica, reproducible y georreferenciada que
permita estudiar patrones agregados de participación, abstención, resultados,
fragmentación, oferta electoral y comportamiento territorial.

## Fuentes previstas

- Registraduría Nacional del Estado Civil
- DIVIPOLE
- DANE
- Consejo Nacional Electoral / Cuentas Claras
- Alcaldía Distrital de Barrancabermeja
- Misión de Observación Electoral
- Otras fuentes públicas documentadas

## Flujo de datos

datos/brutos
→ datos/intermedios
→ datos/procesados
→ análisis / modelos
→ entregables

## Principio fundamental

Los archivos originales descargados nunca deben modificarse.
"""
        readme_path.write_text(readme_content, encoding="utf-8")
        print(f"✅ Creado: {readme_path.name}")
    else:
        print(f"ℹ️ Ya existe: {readme_path.name}")

    # ============================================================
    # 8. CATÁLOGO INICIAL DE FUENTES
    # ============================================================
    fuentes_path = base / "docs" / "fuentes" / "catalogo_fuentes.md"

    if not fuentes_path.exists():
        fuentes_content = """# Catálogo de fuentes

Este documento se utilizará para registrar cada fuente incorporada al proyecto.

| fuente | institución | elección/año | archivo | url | fecha_descarga | nivel_geográfico | observaciones |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Reglas

1. Registrar siempre la URL original.
2. Registrar la fecha de descarga.
3. No modificar el archivo bruto.
4. Documentar si corresponde a preconteo, escrutinio u otra fuente.
5. Registrar cambios de estructura o codificación entre años.
"""
        fuentes_path.write_text(fuentes_content, encoding="utf-8")
        print(f"✅ Creado: {fuentes_path.relative_to(base)}")
    else:
        print(f"ℹ️ Ya existe: {fuentes_path.relative_to(base)}")

    # ============================================================
    # 9. DICCIONARIO DE DATOS INICIAL
    # ============================================================
    diccionario_path = (
        base / "docs" / "diccionario_datos" / "diccionario_datos.md"
    )

    if not diccionario_path.exists():
        diccionario_content = """# Diccionario de datos

Aquí se documentarán las variables estandarizadas del proyecto.

## Tabla central prevista: fact_votos

| variable | tipo | descripción | fuente |
|---|---|---|---|
| eleccion_id | string | Identificador único de elección | derivada |
| anio | int | Año de la elección | Registraduría |
| tipo_eleccion | string | Nacional o territorial | Registraduría |
| corporacion | string | Presidencia, Senado, Cámara, Alcaldía, Concejo, JAL, etc. | Registraduría |
| vuelta | int/string | Vuelta electoral cuando aplique | Registraduría |
| departamento | string | Departamento | Registraduría |
| municipio | string | Municipio | Registraduría |
| zona | string | Zona electoral | Registraduría |
| puesto | string | Puesto de votación | Registraduría |
| mesa | string/int | Mesa de votación | Registraduría |
| partido | string | Partido, movimiento, coalición o agrupación | Registraduría |
| candidato | string | Candidato cuando aplique | Registraduría |
| votos | int | Número de votos | Registraduría |

Este diccionario crecerá a medida que se incorporen fuentes y elecciones.
"""
        diccionario_path.write_text(diccionario_content, encoding="utf-8")
        print(f"✅ Creado: {diccionario_path.relative_to(base)}")
    else:
        print(f"ℹ️ Ya existe: {diccionario_path.relative_to(base)}")

    # ============================================================
    # 10. FINAL
    # ============================================================
    print("\n" + "=" * 70)
    print("✅ ESTRUCTURA CREADA CORRECTAMENTE")
    print("=" * 70)
    print("\nSiguiente paso recomendado:")
    print("1. Abrir esta carpeta en VS Code.")
    print("2. Crear/activar el entorno virtual.")
    print("3. Preparar el notebook 00_auditoria_fuentes.ipynb.")
    print("4. Iniciar la descarga y auditoría de los datos de Registraduría 2026.\n")


if __name__ == "__main__":
    crear_estructura()
