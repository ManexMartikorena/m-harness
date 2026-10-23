# Estado del proyecto

Última actualización: 2026-10-23 (cierre de sesión). **Hito 5 (permisos y
herramientas con efecto) cerrado: `v0.5.0`, más el arreglo `v0.5.1`. Cero
deuda conocida.**
Siguiente: la spec del hito 6 (sesiones e historial), cuando el mantenedor
dé paso. **Sesión en el PC del
trabajo (el WSL del PC de Windows).**

Lo primero al abrir: "Siguiente paso", más abajo.

## Fase actual

**Desarrollo. Hito 5 cerrado (`v0.5.0` y `v0.5.1`). Siguiente: hito 6
(sesiones e historial), empezando por su spec, cuando el mantenedor dé
paso.**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: **`v0.5.1` — Procesos escapados y grep por tandas**
  (2026-10-23):
  https://github.com/ManexMartikorena/m-harness/releases/tag/v0.5.1
- Ramas abiertas: ninguna. Las integradas se conservan en GitHub.

## Para la release

Aquí va solo lo que el workflow de release no hace solo: una variable nueva o
un paso fuera de lo normal.

- Nada pendiente. `v0.5.1` salió sin pasos fuera de lo normal. El arreglo
  del PR #47 está en `main` y sale con la próxima versión (`v0.6.0`), salvo
  que el mantenedor pida un `v0.5.2`.

## Hecho

Lo más reciente primero.

- **Cierre de sesión, 2026-10-23, PC de Windows (WSL).** Hito 5 cerrado:
  `v0.5.0` y el arreglo `v0.5.1` publicados. Una auditoría de fin de sesión
  encontró un fallo más, arreglado en `main` tras `v0.5.1` (PR #47): un
  proceso escapado que no se puede matar ya no corta la limpieza del
  comando. Sin ramas ni PRs abiertos; 750 tests, mypy, ruff e import-linter
  en verde. Método de la sesión: tres auditorías independientes del código
  (la última, sin hallazgos de arquitectura) y la regla nueva de
  `AGENTS.md`: ningún fallo conocido se deja sin arreglar por decisión del
  agente.
- **PRs #43, #44 y #46, 2026-10-23:** docs del cierre (release `v0.5.0`,
  ramas abiertas y release `v0.5.1`).
- **`v0.5.1` publicada, 2026-10-23.** Tag anotado sobre el merge del PR #45
  (`f688169`), con el CI de `main` en verde; creado por el agente con el
  visto bueno del mantenedor. `uvx --from
  git+https://github.com/ManexMartikorena/m-harness@v0.5.1 maha --version`
  → `maha 0.5.1`. Verificado a mano: un `setsid sleep 300` aprobado no
  queda vivo, y `grep` sobre 300 ficheros para en 100 resultados.
- **PR #45 integrado, 2026-10-23** (merge `f688169`; rama
  `fix/procesos-escapados-y-grep`): los procesos que salen de su grupo
  mueren con el comando (`96db36c`, E2 adelantado del hito 14) y `grep`
  busca por tandas (`f249080`). `AGENTS.md` gana la regla `v0.N.M` para un
  arreglo entre hitos.
- **`v0.5.0` publicada, 2026-10-23.** Tag anotado sobre el merge del PR #42
  (`2f8dc55`), con el CI de `main` en verde; creado por el agente (el
  mantenedor pidió "dejar el hito 5 cerrado"). `uvx --from
  git+https://github.com/ManexMartikorena/m-harness@v0.5.0 maha --version`
  → `maha 0.5.0`.
- **PR #42 integrado, 2026-10-23** (merge `2f8dc55`; rama
  `feature/hito-5-cierre`): versión 0.5.0, nota `docs/guia/05-permisos.md`,
  specs del hito 5 y de la mejora en IMPLEMENTADA, README, MAPA y ESTADO.
  Verificación a mano en una pseudoterminal con el modelo real: los 11
  puntos de la spec 5 §7 y los 3 de la mejora, en verde (spec 5, §12.23),
  repetida tras la auditoría final.
- **PR #41 integrado, 2026-10-23** (merge `56d3072`; rama
  `fix/auditoria-final`): los 8 hallazgos de la segunda auditoría (mejora,
  §12.22 a §12.29): título de la pregunta en una línea, tope del recorrido,
  comandos con hijos en segundo plano, `grep` en un proceso hijo contra
  ReDoS (decisión del mantenedor), caracteres invisibles, tests que
  faltaban, `collect()` a los fakes, DESIGN y MAPA. El CI destapó que
  `process.wait()` de Python 3.14.4 espera a las tuberías (`453d8eb`).
- **PR #40 integrado, 2026-10-23** (merge `c084629`; hito 5, PR 4, piezas 14
  a 18, con A2 y B3 de la mejora): un solo lector (`3ae659d`),
  `TerminalApproval` y `DenyAll` (`ea93db2`), la negativa en la conversación
  (`50725f3`), `refusal` (`89e0fec`) y el cableado (`e60101c`).
- **PR #39 integrado, 2026-10-23** (merge `b3294ce`; hito 5, PR 3, piezas 10
  a 13, con B4 y E1 de la mejora): puerto `CommandRunner` (`c1264b0`),
  `command_env()` (`30f1336`), `LocalCommandRunner` (`6991d63`) y
  `run_command` (`9836be4`).
- **PR #38 integrado, 2026-10-23** (merge `ff3c79f`; mejora, PR 4): E6,
  `.gitignore` traducido a mano (`e1b7ffd`) y usado en `glob` y `grep`
  (`eb675f1`).
- **PR #37 integrado, 2026-10-23** (merge `2be2a23`; mejora, PR 3): D6
  (`689adf7`), D3 (`b5bd7d3`), D4 (`fb79e82`), D1 y D2 (`bbce66e`), D7
  (`7a871a6`), D8 (`552804b`), D9 y D10 (`909a863`), D12 (`d6631a1`) y D13
  (`9eade8d`).
- **PR #36 integrado, 2026-10-23** (merge `6101881`; mejora, PR 2): B2
  `approval()` asíncrono (`f8b38f8`), B1 reglas de ruta en el dominio
  (`9d95f18`) y la limpieza C (`95014d5`, `eaddf2f`, `ea20fa2`, `397e5e4`,
  `bb98770`).
- **PR #35 integrado, 2026-10-23** (merge `618ea13`; mejora, PR 1): A1
  (`7235142`), A2 (`4e908f2`), A3 (`b99573b`), A4 (`ec235c3`), A5
  (`4da3ccd`), A6 (`52dc6ba`), A7 (`9c7b915`), E3 (`c64207b`) y E4
  (`e084fbd`).
- **PR #34 integrado, 2026-10-23** (merge `0e944d7`): spec
  `mejora-2026-10-23-deuda-hito-5` APROBADA. El mantenedor aprobó todas las
  recomendaciones del agente sobre los fallos de la primera auditoría y los
  límites conocidos, y pidió cerrar el hito 5 con cero deuda.
- **PR #33 integrado, 2026-10-23** (merge `b8b5c14`; rama
  `fix/fifo-sin-carrera`, `7f329ee`): el tipo de fichero se mira con `fstat`
  sobre el fichero ya abierto. Regla nueva del mantenedor en `AGENTS.md`:
  ningún fallo conocido se deja sin arreglar por decisión del agente.
- **PR #32 integrado, 2026-10-23** (merge `dfa2425`; rama
  `fix/fifo-bloquea-lectura`, `85c9e26`): `read_file` y `grep` ya no abren
  una FIFO.
- **PC de Windows al día, 2026-10-23:** pull de 30 commits, `uv sync` sin
  cambios; 487 tests, mypy, lint-imports y ruff en verde; `maha 0.4.0`.
- **Cierre de sesión, 2026-10-21, Ubuntu de casa.** Todo integrado y con
  push: `main` en `0f2317a` más este cierre; sin ramas abiertas ni cambios
  sin commitear; 487 tests en verde. Se mantiene para el hito 5 el permiso
  del mantenedor: el agente hace push e integra cada PR con el CI en verde;
  el tag sigue necesitando que el mantenedor lo pida. Método acordado esta
  sesión: ante cualquier hueco de la spec, el agente para y pregunta con
  opciones y recomendación; no inventa.
- **Hito 5, PR 2 integrado (#30, merge `0f2317a`), 2026-10-21, Ubuntu de
  casa** (rama `feature/hito-5-ficheros`, borrada en local y conservada en
  GitHub; CI en verde en el PR y en `main`; piezas 6 a 9 de la spec §6): leer fuera del directorio o un secreto con
  aprobación (`7e39cfb`), `write_file` con escritura atómica (`fad129c`),
  `fsync` de la carpeta tras el renombrado (`c22eb08`), `edit_file` con
  adaptación a CRLF (`b8e98b6`) y los docs (mapa, spec y estado: `4db13d8`,
  `e325e54` y `b42ce45`).
  Arreglos de la revisión, decididos por el mantenedor: con aviso, la
  pregunta va antes de los errores de contenido (`39162ca`), tamaño máximo
  de 2 MiB para cambiar (`40e7e1a`), `cannot read` (`b66b354`), la llamada
  entera en `_Shown` y `_Asked` (`06e285e`), `.git` siempre pregunta
  (`ad2341d`), refactor `_as_shown`/`_write` (`9015a45`), aviso de cambio de
  saltos de línea (`8458304`), `grep` salta los ilegibles (`105904d`) y el
  commit "Dar un error limpio si falla el stat del fichero que se cambia"
  (`30ffc45`). Segunda revisión: sin bloqueantes.
  `write_file` y `edit_file` aún no están cableadas en `bootstrap` (pieza
  17). En verde: 487 tests. Las decisiones, los límites conocidos, lo
  pendiente y la revisión, en la spec §12 (puntos 6 a 12).
- **Hito 5, PR 1 (#29) integrado, 2026-10-21** (`98fb0dd`).
- **Hito 5, PR 1, 2026-10-21, Ubuntu de casa** (sale por PR desde
  `feature/hito-5-aprobacion` y lo integra el agente con el CI en verde;
  piezas 1 a 5 de la spec §6):
  contrato de aprobación (`0f8311d`), aprobaciones de sesión (`14026e1`), el
  bucle pregunta (`839231f`), lo ejecutado consta (`a9acbab`) y los docs.
  Arreglos de la revisión, aprobados por el mantenedor: solo una decisión
  válida ejecuta (`d3953b0`), fallo de `summary()` y JSON demasiado anidado
  como error interno (`56d7909`) y más tests del bucle (`bf643a6`). En
  verde: 362 tests. Las decisiones que la spec no fijaba y la revisión, en
  la spec §12.
- **Ubuntu de casa al día, 2026-10-21:** `main` al día, rama local
  `docs/spec-hito-3-streaming` borrada, `uv sync`; 327 tests, mypy,
  lint-imports y ruff en verde; `uv run maha --version` → `maha 0.4.0`.
- **Cierre de sesión, 2026-10-21, PC de Windows (WSL).** Todo integrado y
  con push: `main` en el merge del PR #27 más este cierre; sin ramas
  abiertas ni cambios sin commitear. El mantenedor mantiene para el hito 5
  el permiso que dio en el hito 4: **el agente hace push e integra cada PR
  con el CI en verde** (merge commit). El tag sigue necesitando que el
  mantenedor lo pida.
- **PR #27 integrado, 2026-10-21** (merge `c64aef5`): spec del hito 5
  APROBADA.
- **Spec del hito 5 aprobada, 2026-10-21** (PR #27): el mantenedor acepta
  las cinco recomendaciones de §11 sin cambios; se anota como mejora futura
  aprobar comandos por prefijo (spec §1.3).
- **Spec del hito 5 propuesta, 2026-10-21** (rama
  `docs/spec-hito-5-permisos`):
  - contrato de aprobación: `ApprovalRequest`, `Decision`, puerto
    `ApprovalGate` y `Tool.approval()`; una herramienta `effect` siempre
    pregunta;
  - "toda la sesión" por ámbito: todas las escrituras, todas las ediciones
    o cada comando exacto; fuera del directorio y secretos, siempre uno a
    uno;
  - una negativa termina el turno; lo ejecutado consta en el historial
    aunque falle o se cancele (revisa el turno atómico del hito 4);
  - `write_file`, `edit_file` (texto exacto, con diff) y `run_command`
    (grupo de procesos propio, tiempo límite, salida acotada y sin
    credenciales en el entorno);
  - sin terminal, se deniega todo; `refusal` entra como texto;
  - corrige DESIGN §5 y §10.

  Hechos comprobados ese día en la documentación de Python 3.14
  (`asyncio` subprocess, `process_group`, `os.killpg`, `difflib`) y con una
  prueba local de grupos de procesos.
- **Parada del mantenedor para entender el código, 2026-10-21:** el agente
  le señaló dónde están las herramientas (`adapters/tools/files.py`, puerto
  `ports/tools.py`, registro `application/tools.py`) y el bucle
  (`application/agent.py`, `Agent.run()` y `_execute()`); el mantenedor los
  leyó y dio paso al hito 5.
- **`v0.4.0` publicada, 2026-10-21.** Tag anotado sobre el merge del PR #25
  (`ee632f9`), con el CI de `main` en verde; creado y publicado por el
  agente a petición del mantenedor. `release.yml` creó la release en 11 s:
  título "v0.4.0 — Tool calling y bucle agéntico", las notas del tag y la
  lista de PRs #18 a #25. `uvx --from
  git+https://github.com/ManexMartikorena/m-harness@v0.4.0 maha --version`
  → `maha 0.4.0`.
- **Hito 4, PR 6 (#25) integrado, 2026-10-21** (merge `ee632f9`).
- **Hito 4, PR 6 (cierre), 2026-10-21** (#25):
  versión 0.4.0, nota `docs/guia/04-tool-calling.md`, spec en IMPLEMENTADA
  y README, MAPA y ESTADO al día. Verificación a mano de la spec §7 por el
  agente en pty con el modelo real: los 9 puntos en verde (spec §12.12).
- **Hito 4, PR 5 (#24) integrado, 2026-10-21** (merge `c903c65`; piezas
  22 a 25): la terminal usa `Agent` (se borra `Chat`) y muestra cada
  llamada; `bootstrap` da las cuatro herramientas a `maha`; prueba de punta
  a punta con un fichero real. Probado en pty con el modelo real (spec
  §12.11). En verde: 327 tests.
- **Hito 4, PR 4 (#23) integrado, 2026-10-21** (merge `eec3d5a`; piezas 16
  a 21): `is_secret()` y las herramientas `read_file`,
  `list_dir`, `glob` y `grep`, dentro del directorio de trabajo, sin
  secretos, con topes y sin hilos. Dos fallos encontrados y fijados con
  test (spec §12.6). En verde: 324 tests.
- **Hito 4, PR 3 (#22) integrado, 2026-10-21** (merge `3b52bad`; piezas 9 a
  15): puerto `Tool`, `ToolRegistry` (rechaza las de efecto), eventos del
  agente y el bucle `Agent` (25 pasos, en orden, errores devueltos al
  modelo, turno atómico). Probado con fakes: 264 tests en verde. Lo
  aprendido, en la spec §12.
- **Hito 4, PR 2 (#21) integrado, 2026-10-21** (merge `a158037`; piezas 5
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

Al abrir en otro PC: `git switch main && git pull`, `uv sync` (por si
acaso; no hay dependencias nuevas) y comprobar los tests, mypy y
lint-imports en verde; después, el primer punto sin hacer.

1. **Mantenedor:** dar paso al hito 6 (pidió parar aquí el 2026-10-23).
2. **Agente:** proponer la spec del hito 6 (sesiones e historial) en
   `docs/spec-hito-6-<slug>`, tras leer DESIGN §5, §6 y §14. Entran los
   pendientes que DESIGN y las specs asignan al hito 6 (abajo).
3. **Agente, si se puede desde el Ubuntu de casa:** lo que sigue POR
   VERIFICAR del hito 3 (cortar la red a mitad de una respuesta); anotarlo
   en la spec 3 §12.

### Al abrir el agente en otro PC

Los dos PCs ya están preparados: el WSL del PC de Windows y el Ubuntu de
casa. No hace falta repetir la puesta a punto. Si un pull cambia
dependencias, basta con `uv sync`.

Lo primero, en cualquiera de los dos: `cd` al clon, `git fetch` y contrastar
con GitHub (`gh pr list`) en qué punto de "Siguiente paso" se está. Después,
borrar en ese PC las ramas locales ya integradas:
`git fetch --prune` y
`git branch --merged main | grep -v '^\*\|main' | xargs -r git branch -d`.

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
   verde, y `uv run maha --version` → la versión del último tag (hoy,
   `maha 0.5.1`).
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
- ~~**`refusal` del stream se ignora**~~ **Resuelto** en el hito 5
  (`89e0fec`): llega como texto. Sigue POR VERIFICAR en OpenCode, que no la
  ha mandado nunca (spec 5, §10).
- **Respuesta cortada con Ctrl+C:** queda en pantalla, pero el modelo no la
  recuerda. Guardarla marcada como cortada: hito 6 (spec 3, §1.6).
- **Sin reintentos** ante 429 o 5xx: se valoran en el hito 7 o el 8 (spec 3,
  §1.9).
- **Lo que se teclea mientras gira el spinner se mezcla con él** en pantalla
  (solo visual). Hito 19, con prompt_toolkit (spec 3, §12.10).
- **POR VERIFICAR:** el formato de un error a mitad de stream en OpenCode
  (no se pudo provocar; el código lo lee de forma defensiva) y cortar la red
  a mitad de respuesta a mano (punto 9 de la verificación, no provocado en
  WSL; lo cubren los tests). Siguen POR VERIFICAR: la verificación del
  hito 4 se hizo también desde el PC de Windows. Se miran si aparecen, o
  desde el Ubuntu de casa.

**Pendientes del hito 4** (anotados en su spec; cada uno con el hito que lo
resuelve):
- ~~**Turno atómico:** un fallo o Ctrl+C no guarda nada del turno. Vale porque
  ninguna herramienta tiene efecto; **el hito 5 lo revisa**, porque una
  edición ya hecha sí debe constar (spec 4, §1.7).~~ **Resuelto** en el
  hito 5, pieza 4 (`a9acbab`): lo ejecutado consta aunque falle el modelo o
  se cancele (spec 5, §1.5 y §12).
- **Leer fuera del directorio de trabajo y secretos con otro nombre**
  (`credenciales.txt`): hoy se deniega, o no se detecta. Aprobación en el
  hito 5 (spec 4, §1.6 y §10). **Leer fuera y los secretos conocidos,
  resuelto** en el hito 5, pieza 6 (`7e39cfb`): preguntan, una a una (spec
  5, §1.6 y §12.6). Los secretos con otro nombre siguen sin detectarse:
  se mantiene así por decisión del mantenedor; mirar el contenido es otra
  pieza (hito 14; mejora `2026-10-23`, E5).
- **Tokens:** cada llamada al modelo cuesta ~700 tokens de entrada solo por
  las cuatro herramientas; un turno de dos pasos llegó a 4111. Coste: hito
  7; compactación: hito 11 (spec 4, §12.14).
- **Límites de tokens y de tiempo por turno:** hito 8, con el modo no
  interactivo (spec 4, §11, duda 3).
- **Las descripciones de las herramientas son prompts:** primeras candidatas
  a la batería de evals del hito 8 (spec 4, §5).
- **Llamadas en paralelo:** hito 15 (spec 4, §11, duda 5).
- ~~**`.gitignore`**~~ **Resuelto** (`eb675f1`, spec
  `mejora-2026-10-23-deuda-hito-5`, E6): `glob` y `grep` lo leen.
- **POR VERIFICAR:** si OpenCode llega a partir los argumentos de una
  llamada o a mandar JSON inválido (el código y los tests cubren los dos
  casos; spec 4, §10).
- **Detalles visuales:** el eco de `^C` y lo que se teclea durante un turno
  se mezclan con la salida. Hito 19 (spec 4, §12.13).

**Pendientes del hito 5** (anotados en su spec; cada uno con el hito que lo
resuelve):
- ~~**Excepciones no previstas tras una ejecución**~~ **Resuelto**
  (`e084fbd`, spec `mejora-2026-10-23-deuda-hito-5`, E4): el turno se
  guarda ante cualquier excepción.
- ~~**Una FIFO bloquea `read_file` y `grep` al recorrer**~~ **Resuelto**
  (`85c9e26`, spec 5, §12.11).
- ~~**Pieza 14: sanear la pregunta**~~ **Resuelto** (`ea93db2`, con `clean()`
  de la mejora, A2).
- ~~**`.git/config` se lee sin preguntar**~~ **Resuelto** (`c64207b`, mejora
  E3): es secreto.
- ~~**Límites conocidos de `write_file` y `edit_file`**~~ **Resueltos**
  (spec `mejora-2026-10-23-deuda-hito-5`, PR 3), salvo lo que decidió el
  mantenedor: D7 aceptado, D14 se mantiene, D5 no es un fallo (Linux) y
  D11 va al hito 7.
- ~~**Un comando que sale de su grupo** (`setsid`) sobrevive~~ **Resuelto**
  (`96db36c`, `v0.5.1`): subreaper.
- **Por decisión del mantenedor** (mejora `2026-10-23`): el fallo del
  `fsync` de la carpeta no deja rastro → hito 7 (D11).
- **Comandos interactivos** (un editor, `git commit` sin `-m`): sin stdin,
  terminan o llegan al tiempo límite. Es el diseño (spec 5, §10); la
  descripción pide comandos no interactivos.

**Por medir:**
- Línea base de las evals (hito 8).
- Ahorro de tokens de la memoria (hito 13).

## Versiones

Fase de desarrollo (DESIGN §14), un tag por hito:

- [x] 1. Esqueleto. `v0.1.0` (2026-10-20)
- [x] 2. Primera conversación. `v0.2.0` (2026-10-20)
- [x] 3. Streaming. `v0.3.0` (2026-10-21)
- [x] 4. Tool calling y bucle agéntico. `v0.4.0` (2026-10-21)
- [x] 5. Permisos y herramientas con efecto. `v0.5.0` (2026-10-23) y el
  arreglo `v0.5.1` (2026-10-23)
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
