# CF3 — Calendario completo incluyendo partidos sin fecha/hora

Sustituye en el repositorio:

- `atualizar_jogos_chile.py`

## Qué cambió

`parse_cf3_page` ya capturaba correctamente los partidos que **tienen** fecha
(jugados o programados), incluso cuando CF3 los muestra sin horario (los
guarda con `hora=""` y el resultado/estado en `extra`).

Lo que faltaba: los partidos de **jornadas lejanas que todavía no tienen ni
fecha ni hora asignada** por la ANFA. Antes, el parser exigía encontrar una
fecha (`dd/mm/aaaa`) para empezar a leer un bloque de partido, así que esos
cruces quedaban completamente fuera del calendario.

Se agregó una segunda pasada, `_parse_cf3_sin_fecha`, que:

1. Recorre las líneas que **no** fueron usadas por un partido con fecha.
2. Detecta pares de equipos separados por `VS` / `V/S`, por la etiqueta
   `Por Definir` / `Programado`, o directamente uno tras otro sin separador.
3. Agrega esos partidos con `data=""` y `hora=""`, y `extra="status=Sin
   fecha/hora definida"`, para que igual aparezcan en el calendario completo.

Estos partidos **no** se filtran por la ventana `--dias/--dias-atras`
(no tiene sentido filtrar por fecha algo que no tiene fecha) — siempre se
incluyen salvo que uses el nuevo flag `--excluir-sin-fecha`.

También se corrigió `is_probably_team` para que "Por Definir", "Programado",
"A Definir", etc. no se confundan con nombres de equipo (antes esto podía
"comerse" el siguiente partido cuando estas etiquetas aparecían sueltas).

## Nuevo flag de CLI

```bash
# comportamiento nuevo por defecto: incluye partidos sin fecha/hora
python atualizar_jogos_chile.py --once --dias 180 --dias-atras 14

# para volver al comportamiento anterior (solo partidos con fecha):
python atualizar_jogos_chile.py --once --dias 180 --dias-atras 14 --excluir-sin-fecha
```

## ⚠️ Importante: esto no fue probado contra el sitio real

El entorno donde se preparó este parche no tiene acceso de red a `cf3.cl`
(solo a un puñado de dominios de paquetes), así que no fue posible abrir en
vivo una página de una jornada lejana sin fecha para confirmar su HTML
exacto. La lógica se basa en patrones que **sí** se observaron en el sitio
(el separador `VS` en la tabla de posiciones, y el texto `Por Definir` usado
para estadio) y se probó con HTML simulado (ver el bloque de test más abajo),
pero **antes de dejarlo corriendo en el GitHub Action**, te recomiendo:

```bash
python atualizar_jogos_chile.py --once --dias 365 --dias-atras 14 2>&1 | grep "CF3 ->"
```

y revisar unas filas con `data` vacío en `data/jogos_programados.csv` para
confirmar que los nombres de equipo quedaron bien (mandante/visitante) y no
se coló ningún texto que no era un equipo. Si el HTML real de CF3 usa un
patrón distinto al esperado, lo más probable es que esos partidos
simplemente no se detecten (el parser es defensivo: prefiere omitir un bloque
ambiguo antes que inventar datos), no que se generen filas corruptas.

## Actualización 2: roster oficial 2026 verificado con Wikipedia (42 equipos)

Se agregó también `corrigir_competicao_tercera()`, que corrige el campo
`competicao` de **todos** los partidos de Tercera A/B (de cualquier fuente)
usando un roster oficial 2026 verificado cruzando:

- Las tablas de posiciones de `cf3.cl` (borrador inicial)
- https://es.wikipedia.org/wiki/Tercera_Divisi%C3%B3n_A_de_Chile (tabla
  "Equipos participantes — Temporada 2026", con Ciudad/Estadio/Capacidad)
- https://es.wikipedia.org/wiki/Tercera_Divisi%C3%B3n_B_de_Chile_2026 (tablas
  de Zona Norte/Zona Sur, "Información" con Estadio/Capacidad, y
  "Localización" con Ciudad/Región)

Roster final: 14 Tercera A + 14 Tercera B Norte + 14 Tercera B Sur = 42
equipos, coincide exactamente con lo que documenta Wikipedia.

**Bug real encontrado y corregido**: `Quintero Unido` (Tercera A según
Wikipedia) aparecía en tu `data/jogos_programados.json` etiquetado como
`Tercera B - Norte` (desde `cf3.cl`) y como `ANFA Tercera División` genérico
(desde `anfaterceradivision.cl`, que nunca distingue A/B/Norte/Sur). No fue
un caso aislado: al correr la corrección sobre tu JSON real se corrigieron
**29 partidos**.

Dos nombres de equipo tuvieron que ajustarse tras cruzar con Wikipedia
(mis primeras adivinanzas basadas solo en `cf3.cl` no coincidían con el
nombre oficial):
- "Tricolor de Paine" (mi adivinanza) → nombre oficial "Tricolor Municipal"
  (ciudad Paine) — se dejaron ambos como alias.
- "Villarrica Pérez Rosales" (mi adivinanza, mal transcrita) → nombre oficial
  "Vicente Pérez Rosales" (Puerto Montt) — corregido.

**Bug de parsing aparte, no corregido en este parche**: apareció un partido
`CDSC Iberia vs Equipo` — `"Equipo"` es un placeholder de parsing, no un
rival real. Vale la pena revisarlo por separado.

## Estadios de Tercera A/B agregados a `estadios.js`

Con las tablas de Wikipedia se agregaron 28 estadios reales (con ciudad,
región y coordenadas a nivel de ciudad/comuna — no el pin exacto de la
cancha, marcado como `fonte: "manual/aproximado (...)"`). 4 de esos 28 ya
existían en el archivo porque los comparten con equipos de otras categorías
(Jardín del Edén → Bicentenario de La Florida, Unión Glorias Navales →
Sausalito, Unión Compañías → La Portada, Fernández Vial → Ester Roa
Rebolledo), así que no se duplicaron — se dejó la entrada original, más
precisa.

Quedan pendientes (pediría lo mismo que ya compartiste, pero de estas
páginas, si quieres completar el cruce a nivel de coordenada real de
estadio en vez de nivel-ciudad):

- Artículos individuales de cada estadio en Wikipedia (cuando existan),
  que si tienen coordenadas exactas del recinto, no solo de la ciudad.


## Test rápido incluido (sin red)

```python
from atualizar_jogos_chile import parse_cf3_page
from datetime import date

html_sin_fecha = """
<h1>Jornada 22 Tercera A</h1>
<div>Lautaro de Buin</div><div>VS</div><div>Comunal Cabrero</div><div>Por Definir</div>
<div>Chimbarongo FC</div><div>Dep. Rancagua</div><div>Por Definir</div>
"""
partidos = parse_cf3_page(
    "https://cf3.cl/torneo/tercera-a/fecha/22", html_sin_fecha, 2026,
    date(2026, 1, 1), date(2027, 1, 1),
    incluir_passados=True, incluir_sin_fecha=True,
)
for p in partidos:
    print(p.data, p.mandante, "vs", p.visitante, p.extra)
# '' Lautaro de Buin vs Comunal Cabrero status=Sin fecha/hora definida
# '' Chimbarongo FC vs Dep. Rancagua status=Sin fecha/hora definida
```
