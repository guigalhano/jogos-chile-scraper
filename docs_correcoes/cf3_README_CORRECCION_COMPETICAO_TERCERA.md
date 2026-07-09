# CF3/ANFA — Corrección de competencia (Tercera A vs B) cruzada con Wikipedia

Sustituye en el repositorio:

- `atualizar_jogos_chile.py` (ya incluye también el parche anterior de partidos
  CF3 sin fecha/hora)

## El bug (confirmado con datos reales)

`Quintero Unido` es Tercera A 2026 según Wikipedia:

- https://es.wikipedia.org/wiki/Tercera_Divisi%C3%B3n_A_de_Chile_2026
- https://es.wikipedia.org/wiki/Tercera_Divisi%C3%B3n_A_de_Chile (confirma que
  Quintero Unido es uno de los 2 clubes que siguen en la categoría desde el
  primer torneo de 1981)

Pero en tu `data/jogos_programados.json` aparecía así:

```
Tercera B - Norte | cf3.cl | Quintero Unido vs Comunal Cabrero
ANFA Tercera División | anfaterceradivision.cl/calendario | Quintero Unido Valparaíso vs Comunal Cabrero Biobío
```

No es un caso aislado: al correr la corrección contra tu JSON real aparecieron
**29 partidos mal etiquetados**, la mayoría porque `cf3.cl` arrastra jogos de
otro grupo en la misma página, y `anfaterceradivision.cl` nunca distingue A de
B / Norte de Sur (todo queda como "ANFA Tercera División").

## La corrección

Se armó un roster oficial 2026 (42 equipos: 14 Tercera A + 14 Tercera B Norte
+ 14 Tercera B Sur) cruzando:

1. Las tablas de posiciones de `cf3.cl` (`/torneo/tabla/tercera-a`,
   `/torneo/tabla/tercera-b/grupo-norte`, `/torneo/tabla/tercera-b/grupo-sur`)
2. Los 3 artículos de Wikipedia que confirman el número de equipos por grupo
   (14+14+14 = 42, coincide exactamente)

Con ese roster, la función `corrigir_competicao_tercera()`:

- Recorre **todos** los partidos ya recolectados (de cualquier fuente),
- Busca el equipo mandante/visitante en el roster (normalizando acentos y
  sufijos regionales tipo "... Valparaíso", "... Biobío" que agrega
  `anfaterceradivision.cl`),
- Si el `competicao` guardado no coincide con el roster oficial, lo corrige
  y lo deja registrado en el log como `[CORREÇÃO] ...`,
- Si detecta que mandante y visitante quedaron en grupos distintos según el
  roster (posible error de parsing, no solo de etiqueta), no corrige nada y
  avisa con `[AVISO] ... verificar manualmente` para que lo revises a mano.

Se aplica automáticamente dentro de `update()`, para **todas** las fuentes
(`cf3.cl` y `anfaterceradivision.cl`), justo antes de generar el CSV/JSON
final.

## Bug adicional encontrado (fuera de este parche)

Al revisar tu JSON apareció esta fila:

```
CDSC Iberia vs Equipo
```

`"Equipo"` no es un rival real — es un placeholder que se coló en el parser
de alguna fuente (probablemente `anfaterceradivision.cl`, cuando el nombre del
segundo equipo no cargó a tiempo en el HTML). No lo toqué en este parche
porque es un problema de extracción, no de clasificación de competencia, pero
te lo marco para que lo revises — probablemente valga la pena un filtro que
descarte partidos donde `mandante` o `visitante` sea literalmente "Equipo".

## Sobre el cruce de coordenadas de estadio con Wikipedia

Los 3 artículos de Wikipedia que diste (Tercera A histórico, Tercera A 2026,
Tercera B 2026) **no traen latitud/longitud de estadios** — son artículos de
competición (equipos, formato, ascensos/descensos), no de estadios. Para
tener coordenadas reales hay dos caminos:

1. Wikipedia sí tiene artículos individuales por estadio con coordenadas
   (como los que ya están en tu `estadios.js` para Primera División), pero
   hay que buscarlos uno por uno — no vienen en los 3 links que compartiste.
2. Ya extraje de tus propios datos (cruzando `anfaterceradivision.cl`, que
   agrega la región al nombre del equipo, con los estadios que `cf3.cl` ya
   captura) una tabla equipo → región → nombre de estadio para ~20-24 de los
   42 equipos. Esto reduce mucho el trabajo de geocodificación, pero no
   inventé coordenadas — eso requiere una búsqueda dedicada por estadio.

Si quieres, en un siguiente paso puedo tomar esa tabla y buscar cada estadio
individualmente para agregarlo a `estadios.js` con coordenadas reales
(siguiendo el mismo formato que ya usa el archivo).
