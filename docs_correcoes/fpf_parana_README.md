# Federação Paranaense de Futebol (FPF-PR) — nuevo scraper

Nuevo archivo: `scrap_fpf_parana.py`

## Por qué este enfoque (y no Playwright)

La home `federacaopr.com.br/campeonato/profissional/` muestra los partidos
en un widget JS que aparentemente consulta un backend de la CBF
(`servicos-fdrs.cbf.com.br` / `campeonatos.cbf.com.br`). **Ambos dominios
bloquean acceso automatizado vía `robots.txt`** — no hay forma de sortear
esto sin violar el robots.txt, así que se descartó esa vía por completo
(ni con Playwright serviría, porque el bloqueo es de red/servidor, no de
renderizado).

En cambio, `federacaopr.com.br/noticias/...` son páginas HTML normales
(WordPress, sin JS) que **sí** pude leer directamente. Muchas notícias de
"tabela"/"rodada" traen el calendario como texto plano con un formato bien
regular:

```
27/02 (sexta-feira): 20h – Paraná Clube x Prudentópolis (Vila Capanema)
28/02 (sábado): 16h – Patriotas x Batel (Atílio Gionédis)
01/03 (domingo): 15h30 – Paranavaí x Araucária (Waldemiro Wagner)
16h – Nacional x Toledo (José Carlos Galbier)
17h – Rio Branco x Laranja Mecânica (Gigante do Itiberê)
```

## Qué se validó y qué no

✅ **Validado con contenido real**: extraje el texto de 2 noticias reales
(una de Segundona, otra de Terceirona) durante la exploración, y el parser
extrajo **9/9 partidos correctamente** en ambos casos, incluidas fechas
compartidas entre líneas (cuando varios partidos caen el mismo día, la
fecha solo aparece en la primera línea).

⚠️ **No validado**: el *crawler* que descubre automáticamente qué noticias
contienen tablas (`descubrir_urls_noticias`). El entorno donde escribí esto
no tiene salida de red hacia `federacaopr.com.br` (mi sandbox solo llega a
un puñado de dominios de paquetes), así que no pude confirmar en vivo:
- El selector/estructura exacta de los links en las páginas de categoría
  (`/tag/segundona/`, `/category/noticias/paranaense/2-divisao/`, etc.) —
  por eso la búsqueda de links es deliberadamente genérica (cualquier
  `<a href>` que contenga `/noticias/` y cuyo texto contenga alguna palabra
  de `PALAVRAS_TABELA`), en vez de depender de una clase CSS específica.
- Si esas URLs de categoría/tag son exactamente las correctas (las armé
  siguiendo el patrón visto en otras páginas del sitio, no las confirmé
  una por una).
- Paginación (`/page/2/`, etc.) — es el patrón estándar de WordPress, pero
  no lo vi en vivo en este sitio específico.

## Cómo probarlo tú (primer paso obligatorio)

```bash
pip install requests beautifulsoup4
python scrap_fpf_parana.py --once --debug-html --max-paginas 2
```

El flag `--debug-html` guarda el HTML crudo de cada request en
`data/debug_fpf_parana_html/`. Revisa ahí:

1. Que las páginas de listado (`tag_segundona_.html`, etc.) realmente
   contengan links a noticias con "tabela"/"rodada" en el texto del link.
2. Si `descobrir_urls_noticias` no encuentra nada, abre esos HTML y ajusta
   `PALAVRAS_TABELA` o la lógica de búsqueda de links según lo que
   encuentres — está escrito para ser fácil de ajustar sin tocar el parser
   de partidos (que ya está validado).
3. Que los partidos extraídos (`data/jogos_programados.json`, filtrando por
   `fonte == "federacaopr.com.br"`) tengan sentido — fechas, horas, nombres
   de equipos y estadios correctos.

## Lo que NO cubre este script (por ahora)

- **Estadios con coordenadas**: a diferencia de Chile, todavía no crucé los
  ~40+ clubes de estas 4 competencias con Wikipedia para agregarlos a
  `estadios.js`. Es el mismo proceso que ya hicimos para Tercera A/B, pero
  para otro país — puedo hacerlo en un siguiente paso si quieres.
- **Copa Paraná y Terceirona** aparecieron con menos notícias de tabela
  encontradas en mi exploración manual que Segundona — puede que estas
  competencias publiquen menos "tabelas desmembradas" (más bien fixture
  completo de una vez); si es así, un solo artículo debería alcanzar para
  cubrir toda la fase de grupos de una vez.
