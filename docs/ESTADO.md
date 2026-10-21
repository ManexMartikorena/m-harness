# Estado del proyecto

Última actualización: 2026-10-21. **Hito 3 (streaming) cerrado y publicado
como `v0.3.0`.** Hito 4 (tool calling y bucle agéntico): spec APROBADA (PR #19); PR 1 integrado
(#20) y PR 2 de 6 en revisión.

Lo primero al abrir: "Siguiente paso", más abajo.

## Fase actual

**Desarrollo. Hito 3 cerrado (`v0.3.0`). Hito 4 (tool calling y bucle
agéntico): spec APROBADA (PR #19); PR 1 integrado (#20); PR 2
(`feature/hito-4-adaptador`) en revisión.**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: **`v0.3.0` — Streaming** (2026-10-21):
  https://github.com/ManexMartikorena/m-harness/releases/tag/v0.3.0
- Ramas abiertas: `feature/hito-4-adaptador` (PR 2 del hito 4). Las integradas se
  conservan en GitHub.

## Para la release

Aquí va solo lo que el workflow de release no hace solo: una variable nueva o
un paso fuera de lo normal.

- Nada pendiente. `v0.3.0` salió sin pasos fuera de lo normal.

## Hecho

Lo más reciente primero.

- **Hito 4, PR 2, 2026-10-21** (rama `feature/hito-4-adaptador`; piezas 5
  a 8): el adaptador envía `tools`, las llamadas (`tool_calls`, `content`
  null sin texto) y un mensaje `tool` por resultado; traduce
  `delta.tool_calls` (con `null` explícito) y `message.tool_calls`. En
  verde: 238 tests.
- **Hito 4, PR 1 (#20) integrado, 2026-10-21** (merge `6f73e95`; piezas 1
  a 4 de la spec §6): `ToolCallBlock` (argumentos como texto JSON),
  `ToolResultBlock`, `Message` validado por `type`, `ToolSpec` en la
  petición y `ToolCallDelta` juntado por `index` en el `Accumulator`. En
  verde: 230 tests, ruff, mypy e import-linter.
- **PR #19 integrado, 2026-10-21** (merge `b34bd60`): spec del hito 4
  APROBADA.
- **Spec del hito 4 aprobada, 2026-10-21** (PR #19): el mantenedor acepta
  las cinco recomendaciones de §11 sin cambios.
- **Spec del hito 4 propuesta, 2026-10-21** (rama
  `docs/spec-hito-4-bucle-agentico`):
  - bloques `ToolCallBlock` (argumentos como texto JSON) y
    `ToolResultBlock`; `ToolCallDelta` que junta el `Accumulator`;
  - puerto `Tool` con modelo Pydantic; el registro rechaza herramientas con
    efecto hasta el hito 5;
  - `read_file`, `list_dir`, `glob` y `grep`, sin hilos, dentro del
    directorio de trabajo y sin ficheros secretos;
  - `Agent` sustituye a `Chat`: límite de 25 pasos, llamadas en orden,
    errores devueltos al modelo, turno atómico ante fallo o Ctrl+C;
  - corrige DESIGN §5 (argumentos y resultado como texto; calendario de
    `AgentEvent`).

  Hechos comprobados ese día: la referencia de Chat Completions de OpenAI
  (leída con `curl`; la URL citada en la spec 3 sigue viva) y una sonda de 9
  llamadas a OpenCode Go con permiso del mantenedor: cada llamada llega
  entera en un trozo, varias llamadas en una respuesta,
  `parallel_tool_calls: false` ignorado y `"tool_calls": null` explícito en
  los trozos de texto (spec §1.1).
- **`v0.3.0` publicada, 2026-10-21.** Tag anotado sobre el merge del PR #17
  (`1caebec`), creado y publicado por el agente a petición del mantenedor.
  `release.yml` creó la release en 12 s: título "v0.3.0 — Streaming", las
  notas del tag y la lista de PRs #12 a #17. `uvx --from
  git+https://github.com/ManexMartikorena/m-harness@v0.3.0 maha --version`
  → `maha 0.3.0`. El CI del merge del #17 en `main`, en verde.
- **Hito 3, PR 4 (#17) integrado, 2026-10-21** (merge `1caebec`; piezas
  16 a 19 de la spec §6): versión 0.3.0, nota `docs/guia/03-streaming.md`, spec en
  IMPLEMENTADA y README, MAPA y ESTADO al día. Verificación a mano de la spec
  §7 por el agente en pty con el modelo real: 9 de 10 puntos en verde; el 9
  (cortar la red) no se pudo provocar en WSL y lo cubren los tests (spec
  §12.9).
- **Hito 3, PR 3 (#16) integrado, 2026-10-21** (merge `3e03407`; piezas 9
  a 15 de la spec §6): `stream()` en el puerto y el fake (`Gate`, `HANG`),
  `Chat.stream()`, terminal en directo, spinner con "maha" en colores y
  Ctrl+C que corta solo la respuesta. En verde: 216 tests, ruff, mypy e
  import-linter. Probado en pty con el modelo real (spec §12.8).
- **Hito 3, PR 2 (#15) integrado, 2026-10-21** (merge `3a4fa5e`; piezas 5
  a 8 de la spec §6): `OpenAIChatClient.stream()` con la petición en stream,
  decodificador incremental, traducción de los trozos, errores del stream y
  cierre de la conexión al cancelar. Timeout `read=120` como silencio
  máximo entre trozos. En verde: 181 tests, ruff, mypy e import-linter. Lo
  aprendido, en la spec §12 (respx admite cuerpos que fallan a mitad;
  `stream()` se anota `AsyncGenerator`).
- **Hito 3, PR 1 (#14) integrado, 2026-10-21** (merge `5fadc22`; piezas 1 a
  4 de la spec §6): eventos del dominio
  (`domain/events.py`), `collect()` (`application/collect.py`), analizador
  SSE (`adapters/models/sse.py`) y mapa. En verde: 142 tests, ruff, mypy e
  import-linter.
- **PR #13 integrado, 2026-10-21** (merge `2f7d6a5`): spec del hito 3
  APROBADA. Push e integración por el agente, a petición del mantenedor.
- **Spec del hito 3 aprobada, 2026-10-21** (PC de Windows, WSL; rama
  `docs/spec-hito-3-streaming`). Decisiones del mantenedor (spec §11):
  - duda 1: `complete()` se queda en el puerto, junto a `stream()` (contra
    la propuesta del agente). Corrige DESIGN §6. Sale la pieza que lo
    quitaba;
  - duda 2: spinner braille con "maha", cada letra en un color y los
    colores rotando (spec §1.12, nueva pieza 12). Solo en una terminal real
    y sin color con `NO_COLOR` (https://no-color.org, comprobado ese día);
  - duda 3: Ctrl+C a mitad de respuesta vuelve al prompt;
  - duda 5: `Usage` sigue sin `None`.
- **Spec del hito 3 propuesta, 2026-10-20** (rama
  `docs/spec-hito-3-streaming`, PR #13 abierto
  (https://github.com/ManexMartikorena/m-harness/pull/13), CI en verde):
  - `complete()` sale del puerto: queda `stream()`, y `collect()` (en
    `application`) construye la respuesta entera a partir de los eventos;
  - SSE (*Server-Sent Events*, el formato de streaming de las APIs) a mano,
    sin dependencias nuevas. Las líneas se parten solo en CRLF, LF o CR:
    `aiter_lines()` de httpx 0.28.1 parte también en U+2028 y otros, y
    rompería un JSON válido;
  - corrige DESIGN §5: `MessageEnd` lleva `model`;
  - Ctrl+C a mitad de respuesta corta la respuesta y vuelve al prompt;
  - sonda lanzada en la fase de spec, con permiso del mantenedor (spec
    §1.7): los tokens de salida altos de `glm-5.3-flash` son razonamiento.
    `completion_tokens` incluye `reasoning_tokens`: para "OK", 13 de 16,
    18 de 21 y 43 de 46 (varía mucho). Llega en `delta.reasoning_content`
    con stream y en `message.reasoning` sin él;
  - OpenCode manda `usage` aunque no se pida `stream_options`; ~5 s de
    silencio hasta el primer byte. En OpenCode solo queda POR VERIFICAR el
    formato de un error a mitad de stream.

  Hechos comprobados ese día por el agente en la documentación oficial: el
  endpoint de Go, `https://opencode.ai/inference/go/openai/v1/chat/completions`,
  coincide con el código; la URL que dio Context7 estaba desfasada.
- **Ubuntu de casa preparado, 2026-10-20:**
  - Ubuntu 24.04.5 LTS, no 26.04 como el CI. Funciona: 116 tests, mypy,
    lint-imports y ruff en verde con el python3.14 del sistema (3.14.8), sin
    Python gestionado por uv;
  - uv 0.13.4, con el instalador oficial y `UV_NO_MODIFY_PATH=1`, en
    `~/.local/bin` (ya estaba en el PATH; no se tocó ningún fichero de
    shell). `uv sync` y `pre-commit install` hechos;
  - `.env` con la clave de OpenCode Go y `~/.config/maha/config.toml`.
    Prueba de dos turnos con `glm-5.3-flash` correcta;
  - `gh auth status`: login en github.com como ManexMartikorena, con el scope
    `workflow`;
  - aviso: en ese PC hay otro uv 0.12.17 en `~/.hermes/bin/` (de hermes,
    fuera del PATH) que comparte `~/.cache/uv`. Para quitar uv, no usar
    `uv cache clean` ni `rm -r "$(uv tool dir)"`;
  - dato: "OK" contó `22 in · 67 out` (spec 2 §12.12; se investiga en la
    spec 3, §1.7).
- **PR #12 integrado, 2026-10-20** (merge `80d958d`): cierre de la
  documentación del hito 2.
- **`v0.2.0` publicada, 2026-10-20.** Tag anotado sobre el merge del PR #11
  (`9480b1d`). `release.yml` creó la release en 12 s: título
  "v0.2.0 — Primera conversación", las notas del tag y la lista de PRs #6 a
  #11. `uvx --from git+https://github.com/ManexMartikorena/m-harness@v0.2.0
  maha --version` → `maha 0.2.0`. El CI del merge del #11 pasó entero (ya sin
  cancelaciones en `main`).
- **Hito 2, PR 4 (#11) integrado, 2026-10-20** (merge `9480b1d`; piezas 19
  a 22): versión 0.2.0, nota
  `docs/guia/02-llamada-a-un-llm.md`, spec en IMPLEMENTADA, y README, MAPA y
  ESTADO al día.
  - fuera de plan, a petición del mantenedor: el CI ya no cancela las
    ejecuciones de los pushes a `main`. Al integrar #8, #9 y #10 seguidos,
    las de #8 y #9 salieron canceladas (spec §12.13).
- **Hito 2, PRs 1 a 3 integrados, 2026-10-20** (#8 `ca1aa21`, #9 `dcb7983`,
  #10 `a1964f5`):
  - PR 1, el núcleo: Pydantic 2.14.1, mensajes, petición y respuesta,
    errores del modelo, puerto `ModelClient`, `FakeModelClient` y `Chat`;
  - PR 2, el adaptador: httpx 0.28.1, respx 0.23.1 y `OpenAIChatClient`.
    Un fallo encontrado (la clave cortada por el límite de 300 caracteres),
    convertido en test y arreglado;
  - PR 3, configuración y terminal: `config.py`, la conversación, el
    cableado en `bootstrap`, `.env.example` y `PUESTA_EN_MARCHA` §3.1.
    Corrige la spec §1.11, con el visto bueno del mantenedor: la entrada se
    lee sin hilos, porque con `input()` en un hilo Ctrl+C colgaba `maha`;
  - en verde: 116 tests, con Python 3.14 y 3.15. Lo imprevisto, en la spec
    §12.
- **Verificación a mano del hito 2, 2026-10-20** (spec §7 y §12.10): los
  9 puntos en verde con OpenCode Go y `glm-5.3-flash`. Go acepta
  `Authorization: Bearer`. Clave del mantenedor en el `.env` y
  `~/.config/maha/config.toml` creados en el WSL del PC de Windows.
- **Spec del hito 2 aprobada, 2026-10-20** (PR #7, merge `09ebdb5`), sin
  cambios.
- **Spec del hito 2 propuesta, 2026-10-20** (rama
  `docs/spec-hito-2-primera-conversacion`, PR abierto en GitHub, sin
  integrar). Proveedor elegido por el mantenedor: OpenCode Go.
  - hechos comprobados ese día en la documentación oficial (spec §1.1): URLs
    de chat completions de OpenCode Go y Zen, cabecera
    `x-opencode-session`, modelos sin entrenamiento, formato de OpenAI;
    versiones de pydantic 2.14.1, httpx 0.28.1 y respx 0.23.1, probadas con
    Python 3.14 y 3.15;
  - corrige DESIGN §7: la configuración del proyecto solo elige proveedor y
    modelo (spec §1.10);
  - cuatro PRs de implementación (spec §6).

- **`v0.1.0` publicada, 2026-10-20.** Tag anotado sobre el merge del PR #5
  (`e78f7d9`). `release.yml` creó la release en 12 s: título
  "v0.1.0 — Esqueleto", las notas del tag y la lista de PRs #1 a #5.
  `uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.1.0`
  instala `maha 0.1.0`. Spec §7 completa.
- **Hito 1, PR 2 (#5) integrado, 2026-10-20** (merge `e78f7d9`; piezas 11 a
  15 de la spec §6):
  - workflow de release, versión 0.1.0, nota de la guía
    `docs/guia/01-arquitectura-hexagonal.md`, spec en IMPLEMENTADA, y README,
    MAPA, PUESTA_EN_MARCHA y ESTADO al día;
  - fuera de plan, con el visto bueno del mantenedor: el CI fija gitleaks
    8.30.1, la misma versión que pre-commit (spec §12).
- **GitHub tras el PR 1, 2026-10-20** (humano): el ruleset "main protegida"
  exige `checks (3.14)`, `checks (3.15)` y `secrets`, con "up to date"
  activada (`PUESTA_EN_MARCHA` §5). CI lanzado a mano sobre `main`: gitleaks
  revisó el historial entero (41 commits), sin secretos.
- **Hito 1, PR 1 (#4) integrado, 2026-10-20** (merge `e935068`). Un commit
  por pieza (spec §6, piezas 1 a 10):
  - proyecto uv, ruff, mypy estricto, las cuatro capas con import-linter,
    pytest con el test de arquitectura, el adaptador `cli` con `--version`,
    `bootstrap.py` y el comando `maha`, pre-commit, CI y mapa;
  - en verde: ruff, mypy, import-linter y pytest (8 tests), con Python 3.14
    y también con 3.15;
  - verificación a mano (spec §7): puntos 1 a 8 hechos;
  - lo imprevisto, en la spec §12 "Aprendido al implementar": ruff formatea
    Markdown, mypy e import-linter piden que existan `tests/` y las capas, y
    el hook de gitleaks no mira el primer commit de un repo.

- **Clon en `~/` en el PC de Windows, 2026-10-20:** el agente trabaja desde
  `~/Desarrollo/m-harness`, dentro de WSL. El clon viejo de `/mnt/c/…`, limpio
  y al día, se borró.
- **WSL preparado en el PC de Windows, 2026-10-19:** Ubuntu 26.04.1,
  uv 0.13.1, gh 2.102 con login y el agente dentro de WSL.
- **GitHub revisado, 2026-10-19:** ajustes, rulesets y alertas coinciden con
  `docs/PUESTA_EN_MARCHA.md` §5. Sin issues, tags ni releases.
- **Spec del hito 1 aprobada, 2026-10-19** (PR #2), sin cambios.
  - Plataforma: Linux. En Windows, Ubuntu 26.04 en WSL2, con el agente
    dentro de WSL. CI con `ubuntu-26.04`.
  - Versiones de las herramientas comprobadas ese día (spec §1.1).
- **GitHub configurado, 2026-10-19.**
  - Solo merge commit; las ramas integradas se conservan.
  - `main` y los tags `v*` protegidos con rulesets.
  - Alertas de seguridad activadas.

  Detalle en `docs/PUESTA_EN_MARCHA.md` §5.
- **Repositorio público creado y primer push, 2026-10-19.** Un commit por
  fichero fundacional.
- **Documentos fundacionales, 2026-10-19:**
  - en la raíz: `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore`
    y `.gitattributes`;
  - en `docs/`: `ANALISIS.md`, `DESIGN.md`, `ESTADO.md`, `PUESTA_EN_MARCHA.md`,
    `MAPA.md`, `guia/README.md` y `specs/PLANTILLA.md`;
  - en `.github/`: `pull_request_template.md`.
- **Decisiones de diseño del mantenedor, 2026-10-19:**
  - sin frameworks de agentes: a mano lo que es del agente, fontanería
    estándar y la industria documentada al lado;
  - monolito modular con arquitectura hexagonal; asíncrono con `asyncio`;
  - httpx directo; adaptador de OpenAI primero y de Anthropic en el hito 9;
  - trazas propias y OpenTelemetry opcional; Pydantic también en el dominio;
  - comando `maha`, módulo `mharness`, distribución `m-harness`;
  - spec en su propio PR; integración con merge commit; muchos commits
    pequeños;
  - todo lo que hace el agente de código se explica al mantenedor, corto y
    directo.
- **Análisis cerrado, 2026-10-19.**

## Siguiente paso

El mantenedor autorizó el 2026-10-21 que el agente haga push e integre cada
PR del hito 4 con el CI en verde.

1. **Agente:** push de `feature/hito-4-adaptador`, PR e integración.
2. **Agente:** PR 3 del hito 4 (spec §6, piezas 9 a 15) en
   `feature/hito-4-bucle`: puerto `Tool`, registro, eventos del agente y el
   bucle, con fakes.

**Sesión del 2026-10-21 en el PC de Windows (WSL).**

### Al abrir el agente en otro PC

Los dos PCs ya están preparados: el WSL del PC de Windows y el Ubuntu de
casa. No hace falta repetir la puesta a punto. Si un pull cambia
dependencias, basta con `uv sync`.

Lo primero, en cualquiera de los dos: `cd` al clon, `git fetch` y contrastar
con GitHub (`gh pr list`) en qué punto de "Siguiente paso" se está.

**Solo para un PC nuevo o tras un pull que toque dependencias:**
1. `cd` al clon y `git switch main && git pull`.
2. `uv --version`: tiene que ser 0.13.1 o posterior (si no,
   `uv self update`).
3. `gh auth status`: con login en github.com y el scope `workflow` en
   "Token scopes". Si falta: `gh auth refresh --hostname github.com --scopes
   workflow` (sin él, GitHub rechaza el push de `.github/workflows/`).
4. `uv sync` y `uv run pre-commit install` (`PUESTA_EN_MARCHA` §0). La
   primera ejecución de los hooks descarga Go y compila gitleaks.
5. Comprobar: `uv run pytest`, `uv run mypy` y `uv run lint-imports` en
   verde, y `uv run maha --version` → `maha 0.2.0`.
6. Para conversar: `cp .env.example .env` con la clave de OpenCode Go, y
   `~/.config/maha/config.toml` (`PUESTA_EN_MARCHA` §2 y §3.1). La clave no
   viaja por git: se copia de la consola de opencode.ai (o se crea otra para
   ese PC). Probar con `uv run --env-file .env maha`: dos turnos y `/exit`.

Después, lanzar el agente desde el clon. Él lee `AGENTS.md` y este fichero,
y sigue por el primer punto de "Siguiente paso" que no esté hecho. Para
saber cuál es, el agente lo contrasta con GitHub (`gh pr list`, `gh release
list`). Si hay un PR abierto, se trabaja en su rama:
`git switch <rama> && git pull`.

Regla: no trabajar en los dos PCs a la vez sin push entre medias.

## Pendientes / decisiones abiertas

**Puestos de trabajo:**
- Los dos listos, con clave y configuración: el WSL del PC de Windows
  (Ubuntu 26.04.1) y el Ubuntu de casa (24.04.5, no 26.04; ver "Hecho",
  2026-10-20).

**Externas, con el hito en que bloquean:**
- **Proveedor de modelos: OpenCode Go**, funcionando desde el 2026-10-20
  (verificación a mano del hito 2).

**Se deciden en la spec de su hito:**
- búsqueda en la memoria (hito 13);
- tecnología del sandbox (hito 14);
- cliente MCP a mano o con el SDK oficial (hito 16);
- proveedor de búsqueda web (hito 17);
- tratamiento de PDFs (hito 18).

**Pendientes del hito 3** (anotados en su spec; cada uno con el hito que lo
resuelve):
- **Tokens de razonamiento:** "OK" cuesta de 16 a 99 tokens de salida
  porque `glm-5.3-flash` razona; varía mucho con el mismo prompt.
  `reasoning_content` se ignora. Desglose y coste: hito 7 (spec 3, §1.7 y
  §12.9.3).
- **`refusal` y `tool_calls` del stream se ignoran:** una negativa del
  modelo se perdería en silencio. Hito 4 (spec 3, §10).
- **Respuesta cortada con Ctrl+C:** queda en pantalla, pero el modelo no la
  recuerda. Guardarla marcada como cortada: hito 6 (spec 3, §1.6).
- **Sin reintentos** ante 429 o 5xx: se valoran en el hito 7 o el 8 (spec 3,
  §1.9).
- **Lo que se teclea mientras gira el spinner se mezcla con él** en pantalla
  (solo visual). Hito 19, con prompt_toolkit (spec 3, §12.10).
- **POR VERIFICAR:** el formato de un error a mitad de stream en OpenCode
  (no se pudo provocar; el código lo lee de forma defensiva) y cortar la red
  a mitad de respuesta a mano (punto 9 de la verificación, no provocado en
  WSL; lo cubren los tests). Se miran si aparecen, o en la verificación del
  hito 4 desde el Ubuntu de casa.

**Por medir:**
- Línea base de las evals (hito 8).
- Ahorro de tokens de la memoria (hito 13).

## Versiones

Fase de desarrollo (DESIGN §14), un tag por hito:

- [x] 1. Esqueleto. `v0.1.0` (2026-10-20)
- [x] 2. Primera conversación. `v0.2.0` (2026-10-20)
- [x] 3. Streaming. `v0.3.0` (2026-10-21)
- [ ] 4. Tool calling y bucle agéntico. `v0.4.0`
- [ ] 5. Permisos y herramientas con efecto. `v0.5.0`
- [ ] 6. Sesiones e historial. `v0.6.0`
- [ ] 7. Trazas y coste. `v0.7.0`
- [ ] 8. Evals y modo no interactivo. `v0.8.0`
- [ ] 9. Adaptador de Anthropic. `v0.9.0`
- [ ] 10. System prompt por capas. `v0.10.0`
- [ ] 11. Gestión del contexto. `v0.11.0`
- [ ] 12. Skills. `v0.12.0`
- [ ] 13. Memoria persistente. `v0.13.0`
- [ ] 14. Sandbox. `v0.14.0`
- [ ] 15. Subagentes. `v0.15.0`
- [ ] 16. MCP. `v0.16.0`
- [ ] 17. Web. `v0.17.0`
- [ ] 18. Multimodal. `v0.18.0`
- [ ] 19. Interfaz completa. `v0.19.0`
- [ ] 20. Exportador OpenTelemetry. `v0.20.0`
- [ ] 21. Versión 1.0. `v0.21.0` y `v1.0.0`

**Mantenimiento.** `v1.N.0` para una mejora y `v1.N.M` para un arreglo.
