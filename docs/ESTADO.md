# Estado del proyecto

Última actualización: 2026-11-12. **Hito 10 cerrado: `v0.10.0` (system
prompt por capas) y `v0.10.1` (la auditoría tras el hito 10). `v0.10.2`
(su segunda y tercera revisión, cero deuda) está commiteada en su rama,
sin publicar. Lo siguiente: cerrar `v0.10.2`; después, el hito 11
(gestión del contexto), cuando el mantenedor lo diga.**

Lo primero al abrir: "Siguiente paso", más abajo. El detalle de lo hecho
está en [`HISTORIAL_DESARROLLO.md`](HISTORIAL_DESARROLLO.md).

## Fase actual

**Desarrollo. Hitos 1 a 10 cerrados, con la auditoría tras el hito 10
(`v0.10.1`) y su segunda revisión (`v0.10.2`). Lo siguiente, el hito 11
(gestión del contexto). Plan: 23 hitos hasta la 1.0 (DESIGN §14).**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: **`v0.10.1` — Auditoría tras el hito 10** (2026-11-11):
  https://github.com/ManexMartikorena/m-harness/releases/tag/v0.10.1
- Ramas abiertas: `fix/cierre-auditoria-hito-10` (la segunda y la tercera
  revisión de la auditoría, R17 a R43, sin PR todavía). Las integradas se
  conservan en GitHub.

## Para la release

Aquí va solo lo que el workflow de release no hace solo: una variable nueva o
un paso fuera de lo normal.

- Nada pendiente.

## Hecho

Un resumen por hito; el detalle, en
[`HISTORIAL_DESARROLLO.md`](HISTORIAL_DESARROLLO.md), y cada hito con su
spec, su nota de la guía y su release.

| Hito | Qué | Versión |
|---|---|---|
| 1 | Esqueleto, CI y reglas de arquitectura | `v0.1.0` (2026-10-20) |
| 2 | Primera conversación con un modelo | `v0.2.0` (2026-10-20) |
| 3 | Streaming | `v0.3.0` (2026-10-21) |
| 4 | Tool calling y bucle agéntico | `v0.4.0` (2026-10-21) |
| 5 | Permisos y herramientas con efecto | `v0.5.0` (2026-10-23), `v0.5.1`, `v0.5.2` (cero deuda) |
| 6 | Sesiones e historial | `v0.6.0` (2026-10-26), `v0.6.1` |
| 7 | Trazas y coste, con tres revisiones independientes | `v0.7.0` (2026-10-27), `v0.7.1` |
| 8 | Evals (20 tareas, dos modelos, línea base), `maha -p`, reintentos con respaldo y comandos de línea; auditoría con tres revisiones independientes | `v0.8.0` (2026-10-30), `v0.8.1` (2026-11-03) |
| 9 | Formato de Anthropic (Claude, MiniMax y Qwen por OpenCode; la API directa), el formato de cada modelo, razonamiento devuelto intacto, effort y caché del prompt; auditoría profunda con cinco revisores y una revisión de los arreglos | `v0.9.0` (2026-11-03), `v0.9.1` (2026-11-04) |
| 10 | System prompt por capas (`AGENTS.md`, entorno, `maha prompt`), `todo_write`, `ask_user`, `/init`, títulos de sesión y `/rename`; evals con 24 tareas y líneas base nuevas; auditoría con cinco revisores, mejoras de producto y dos revisiones independientes de los arreglos | `v0.10.0` (2026-11-10), `v0.10.1` y `v0.10.2` (2026-11-11) |

## Siguiente paso

Al abrir: contrastar con GitHub (`gh pr list`, `gh release list`) y
trabajar desde `main` al día (`git switch main && git pull`, `uv sync`).

0. **Agente, en `fix/cierre-auditoria-hito-10`:** cerrar `v0.10.2`. La
   tercera revisión (R26 a R43, spec de la auditoría) está arreglada y
   commiteada, con sus tests; verificada a mano en una pty y en `bash -i`.
   Falta, en este orden: (a) encontrar el test inestable: el 2026-11-12,
   una pasada de `uv run pytest` dio 1 fallo y las tres siguientes, 2574
   en verde; pasar la suite unas 10 veces, encontrarlo y arreglarlo (test
   primero); (b) una revisión independiente corta de `Hangup` (el último
   commit de código), por el patrón de esta auditoría: cada tanda de
   arreglos trajo fallos nuevos; (c) las evals, con todo dentro
   (`maha eval --models glm-5.3-flash,kimi-k2.7-code,claude-haiku-5-5
   --repeat 5 --retry-errors`; cambia `edit_file`, R26 a R28), anotadas en
   la spec, sección "Evals", y en HISTORIAL; (d) "Aprendido al
   implementar" de la tercera revisión en la spec; HISTORIAL, PROYECTO y
   los README si hace falta; (e) versión 0.10.2 en `pyproject.toml` y
   `uv.lock`; (f) PR, merge con el CI en verde, tag `v0.10.2` y release
   (permiso del mantenedor del 2026-11-11); (g) ESTADO sin esta rama.
1. **Mantenedor:** decir cuándo se empieza el hito 11 (gestión del
   contexto). Hasta entonces, el agente no empieza su spec (decisión del
   mantenedor, 2026-11-11).
2. **Agente, cuando el mantenedor lo diga:** la spec del hito 11, en su
   rama `docs/spec-hito-11-<slug>`, con lo que ya tiene asignado (ver
   "Con hito asignado", más abajo).
3. **Agente, si se puede desde el Ubuntu de casa:** lo que sigue POR
   VERIFICAR del hito 3 (cortar la red a mitad de una respuesta); anotarlo
   en la spec 3 §12.

Una pasada de `maha eval` deja ya su informe en `report.txt`, junto a
`runs.json` (desde `9a9333d`): no hace falta `tee`.

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
   `maha 0.10.1` hasta publicar `v0.10.2`).
6. Para conversar: `cp .env.example .env` con la clave de OpenCode Go, y
   `~/.config/maha/config.toml` (`PUESTA_EN_MARCHA` §2 y §3.1). La clave no
   viaja por git: se copia de la consola de opencode.ai (o se crea otra para
   ese PC). Probar con `uv run --env-file .env maha`: dos turnos y `/exit`.
7. Desde el hito 8, las evals (llamadas reales, unos 0,60 $ y 12 minutos
   la pasada completa): `PUESTA_EN_MARCHA` §4.1. La línea base viaja por
   git (`evals/baselines/`); las sesiones y trazas de cada `maha eval` se
   quedan en el PC donde se lanzó (`~/.local/state/maha/evals/`).

Después, lanzar el agente desde el clon. Él lee `AGENTS.md` y este fichero,
y sigue por el primer punto de "Siguiente paso" que no esté hecho. Para
saber cuál es, el agente lo contrasta con GitHub (`gh pr list`, `gh release
list`). Si hay un PR abierto, se trabaja en su rama:
`git switch <rama> && git pull`.

Regla: no trabajar en los dos PCs a la vez sin push entre medias.

## Pendientes / decisiones abiertas

**Puestos de trabajo:**
- Los dos listos, con clave y configuración: el WSL del PC de Windows
  (Ubuntu 26.04.1) y el Ubuntu de casa (24.04.5).
- **Proveedor de modelos: OpenCode Go**, funcionando desde el 2026-10-20.

**Decisiones del mantenedor para hitos futuros** (todas del 2026-10-27):
- **Producto profesional** (ANALISIS §4): lo más completo posible e
  intuitivo; las 17 piezas son el mínimo.
- **El plan de 23 hitos** de DESIGN §14, a partir de
  `docs/COMPARATIVA.md`. Después de la 1.0: LSP y formateadores, plugins,
  API y SDK, editores, GitHub Action, las APIs de Responses de OpenAI y de
  Google, *worktrees*, tareas programadas y voz.
- **Hito 21, una TUI completa**, bonita y fácil para cualquier persona:
  todos los comandos, descubribles en un menú de comandos (como la paleta
  `ctrl+p` de OpenCode), con `/help`, `/` y atajos. La interfaz de línea se
  conserva.
- **Distribución pública en la 1.0** (hito 23), con documentación de
  usuario.
- **Dos caras en GitHub**, al día en cada cierre de hito (AGENTS.md).

**Se deciden en la spec de su hito:**
- búsqueda en la memoria (hito 14);
- tecnología del sandbox (hito 15);
- cliente MCP a mano o con el SDK oficial (hito 17);
- proveedor de búsqueda web (hito 19);
- tratamiento de PDFs (hito 20);
- librería y pantallas de la TUI (hito 21);
- canal de distribución (hito 23).

**Con hito asignado** (salieron de hitos anteriores; cada uno, de su spec):
- **Hito 11:** los `AGENTS.md` de subcarpetas, cargados al leer un fichero
  de allí (spec 10, decisión 6); el coste en tokens de las
  herramientas en cada llamada (~700 con las cuatro del hito 4; hoy son
  siete, por medir) y compactar (spec 4, §12.14); en la batería de evals, tareas con historial previo y la marca
  `[interrupted by the user]` (spec 6, §5; pasa del hito 8 por decisión
  del mantenedor, spec 8, §11.8).
- **Hito 12:** bifurcar una sesión (spec 8, §11.8).
- **Hito 13:** las reglas de instrucciones por ruta, como `.claude/rules/`
  con `paths` (spec 10, decisión 6).
- **Hito 15:** que un comando no llegue a los *sockets* de la sesión de la
  persona (D-Bus, el agente SSH): quitar `XDG_RUNTIME_DIR` de su entorno
  es una defensa más, no una frontera, porque un comando corre como la
  persona y puede rehacer la ruta; la frontera es el sandbox (segunda
  revisión de la auditoría tras el hito 10).
- **Hito 15:** detectar secretos con otro nombre (`credenciales.txt`)
  mirando el contenido (mejora `2026-10-23`, E5); con el sandbox,
  `run_command` en las evals y tareas de "ejecuta y arregla" (spec 8,
  §11.2).
- **Hito 15:** (también) que una comprobación de las evals no se pueda
  engañar con un módulo que tapa uno de la biblioteca estándar
  (`unittest.py` en la copia): el aislamiento completo de las comprobaciones
  (auditoría profunda tras el hito 9, I14 e I5; decisión del mantenedor,
  2026-11-03).
- **Hito 16:** llamadas a herramientas en paralelo (spec 4, §11); comandos
  que esperan entrada, con los comandos en segundo plano (spec 5, §10);
  varios comandos a la vez, hoy uno a uno por el subreaper (spec 8, §12.10).
- **Hito 17:** que `main()` no calle un `BrokenPipeError` que no sea de
  stdout: los procesos hijo de MCP tratan sus propias tuberías, con su
  test (spec 8, §12.56; decisión del mantenedor, 2026-11-03).
- **Hito 21:** tras Ctrl+Z y `fg` en el prompt, repintar `> ` y la línea
  tecleada, en modo raw (decisión del mantenedor, 2026-11-12; auditoría
  tras el hito 10, R42).
- **Hito 21:** lo que se teclea mientras gira el spinner y el eco de `^C`
  se mezclan con la salida (spec 3, §12.10; spec 4, §12.13); ver el texto
  del razonamiento (spec 7); con el selector de modelo, que un id que no
  está en el catálogo (`-m kimi`, `model = "kimi"`) sugiera los parecidos
  y que el error del proveedor diga qué hacer (`/model`, `maha models`):
  hoy da solo `HTTP 400 … Model is unavailable` (prueba del mantenedor,
  2026-11-03).
- **Con la batería más larga (hito 11):** volver a medir cuándo usan los
  modelos `todo_write`. Hoy solo la 12 (train) y la 23 (validación) son
  trabajo largo; la guía se ajustó con la 12 y una tarea a mano (spec 10,
  §5, "Resultados (PR 2)").
- **Mejora posible:** refrescar los precios desde models.dev a una caché, a
  petición, si mantener a mano 113 modelos pesa (spec 7, §11). Hoy, con
  OpenCode Go, el coste que vale es el del proveedor.

**POR VERIFICAR** (observaciones de proveedor o de entorno, no deuda: el
código y los tests cubren los dos casos):
- cortar la red a mitad de una respuesta, a mano (spec 3, punto 9 de la
  verificación): no se pudo provocar en WSL; desde el Ubuntu de casa;
- un turno con la API directa de Anthropic (`provider = "anthropic"`):
  probada con respx; la llamada real, cuando haya `ANTHROPIC_API_KEY`
  (spec 9, decisión 1);
- el formato de un error a mitad de stream en OpenCode (spec 3, §10);
- si OpenCode llega a partir los argumentos de una llamada o a mandar JSON
  inválido (spec 4, §10);
- un `refusal` de OpenCode, que no ha mandado nunca (spec 5, §10);
- qué campos de coste manda OpenCode Zen; la cuenta es de Go (spec 7, §10);
- el coste que cobra OpenCode Go por `claude-haiku-5-5` es unas 3-4 veces
  el que sale con los precios de `models.toml` (una llamada del
  2026-11-10: 2.867 de entrada, 2.863 de ellos escritos en caché, y 95 de
  salida; OpenCode cobró 0,0016 $ y el catálogo da unos 0,0004 $; encaja
  con 0,50/2,50 $ sin descuento de caché). Comprobado el 2026-11-11: la
  documentación de Go da los precios del catálogo (0,10/0,50 $ hasta 100K),
  así que la diferencia es de lo que cobra OpenCode, no del catálogo; con
  Go vale el coste del proveedor (auditoría tras el hito 10, M7);
- qué mantuvo abierta casi cinco minutos una llamada de Kimi sin contenido
  (probablemente comentarios SSE); ya se corta a los 120 s sin datos (spec
  8, §12.9).

**Límites aceptados por el mantenedor** (cada uno, con su decisión en su
spec; los cuatro primeros, confirmados de nuevo el 2026-10-27):
- los secretos con otro nombre no se detectan hasta el hito 15 (mejora
  `2026-10-23`, E5);
- D7 y D14 de `write_file`/`edit_file` (mejora `2026-10-23`);
- la rotación de `maha.log` no se coordina entre varios `maha` a la vez
  (spec 7, §12.48);
- un error de uso de la línea (código 2) en `-p` con JSON no escribe
  `result`: argparse falla antes de saber el formato (spec 8, §12.56;
  2026-11-03).

Los comandos interactivos (un editor, `git commit` sin `-m`) figuraban aquí
como "terminan o llegan al tiempo límite: es el diseño (spec 5, §10)", pero
no eran una decisión del mantenedor. Arreglados el 2026-10-27: fallan al
momento (spec 5, §10).

**Por medir:**
- Ahorro de tokens de la memoria (hito 14).

**Medido:** la primera línea base de las evals (2026-10-27, `evals/baselines/`;
spec 8, §5). La batería tiene que crecer con tareas exigentes hasta 30 o
más antes de la 1.0 (DESIGN §9): con 20, el éxito ronda el 94-99 %.

## Versiones

Fase de desarrollo (DESIGN §14), un tag por hito:

- [x] 1. Esqueleto. `v0.1.0` (2026-10-20)
- [x] 2. Primera conversación. `v0.2.0` (2026-10-20)
- [x] 3. Streaming. `v0.3.0` (2026-10-21)
- [x] 4. Tool calling y bucle agéntico. `v0.4.0` (2026-10-21)
- [x] 5. Permisos y herramientas con efecto. `v0.5.0` (2026-10-23) y los
  arreglos `v0.5.1` (2026-10-23) y `v0.5.2` (2026-10-26)
- [x] 6. Sesiones e historial. `v0.6.0` (2026-10-26) y el arreglo `v0.6.1`
  (2026-10-27)
- [x] 7. Trazas y coste. `v0.7.0` (2026-10-27) y el arreglo `v0.7.1`
  (2026-10-27)
- [x] 8. Evals y modo no interactivo. `v0.8.0` (2026-10-30) y el arreglo
  `v0.8.1` (2026-11-03, la auditoría)
- [x] 9. Adaptador de Anthropic. `v0.9.0` (2026-11-03) y el arreglo
  `v0.9.1` (2026-11-04, la auditoría profunda)
- [x] 10. System prompt por capas. `v0.10.0` (2026-11-10) y los arreglos
  `v0.10.1` y `v0.10.2` (2026-11-11, la auditoría y su segunda revisión)
- [ ] 11. Gestión del contexto. `v0.11.0`
- [ ] 12. Deshacer y puntos de control. `v0.12.0` *(nuevo, 2026-10-27)*
- [ ] 13. Skills y comandos personalizados. `v0.13.0`
- [ ] 14. Memoria persistente. `v0.14.0`
- [ ] 15. Sandbox y modos de permiso. `v0.15.0`
- [ ] 16. Subagentes y agentes propios. `v0.16.0`
- [ ] 17. MCP. `v0.17.0`
- [ ] 18. Hooks. `v0.18.0` *(nuevo, 2026-10-27)*
- [ ] 19. Web. `v0.19.0`
- [ ] 20. Multimodal. `v0.20.0`
- [ ] 21. Interfaz completa (TUI). `v0.21.0`
- [ ] 22. Exportador OpenTelemetry. `v0.22.0`
- [ ] 23. Versión 1.0 y distribución. `v1.0.0`

*(Plan reordenado el 2026-10-27 por decisión del mantenedor, DESIGN §14 y
`docs/COMPARATIVA.md`.)*

**Mantenimiento.** `v1.N.0` para una mejora y `v1.N.M` para un arreglo.
