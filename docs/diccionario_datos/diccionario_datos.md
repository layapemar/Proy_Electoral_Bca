# Diccionario de datos

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
