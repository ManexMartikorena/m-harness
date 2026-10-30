# Estado del proyecto

Última actualización: 2026-10-30. **Hito 8 en curso: PRs 1 a 4 de 6
integrados (núcleo sin persona, evals, `maha -p` y reintentos con
respaldo); el PR 5, comandos de línea, en su rama. Cero deuda conocida.**

Lo primero al abrir: "Siguiente paso", más abajo. El detalle de lo hecho
está en [`HISTORIAL_DESARROLLO.md`](HISTORIAL_DESARROLLO.md).

## Fase actual

**Desarrollo. Hitos 1 a 7 cerrados; en curso: hito 8 (evals y modo no
interactivo), spec `docs/specs/hito-8-evals-no-interactivo.md` APROBADA,
PRs 1 a 4 de 6 integrados; el 5, en su rama. Plan: 23 hitos hasta la 1.0
(DESIGN §14).**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: **`v0.7.1` — Comandos sin terminal** (2026-10-27):
  https://github.com/ManexMartikorena/m-harness/releases/tag/v0.7.1
- Ramas abiertas: `feature/hito-8-comandos`, el PR 5 del hito 8. Las
  integradas se conservan en GitHub.

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
| 8 | *En curso.* Evals y modo no interactivo: PR 1 (#91) núcleo sin persona, PR 2 (#92) evals con la primera línea base, PR 3 (#95) `maha -p`, PR 4 (#96) reintentos y respaldo y PR 5 (comandos de línea, en su rama) | — |

Después del hito 7 (2026-10-27, todo de documentación, decidido por el
mantenedor):
- **Segundo objetivo:** un producto profesional, lo más completo posible e
  intuitivo (ANALISIS §4); la distribución pública entra en la 1.0.
- **Plan ampliado** con la comparativa de OpenCode y Claude Code
  (`docs/COMPARATIVA.md`): hitos ampliados, dos nuevos (12 deshacer, 18
  hooks) y la 1.0 en el hito 23.
- **El hito 21 es una TUI completa**, con OpenCode como referencia.
- **Dos caras en GitHub:** `README.md` (inglés) y `README.es.md` como
  producto; `docs/PROYECTO.md` como proyecto.
- **ESTADO ordenado:** el historial pasa a `HISTORIAL_DESARROLLO.md`.
- **GitHub ordenado:** descripción y temas del repositorio al día; un
  milestone por hito, los 1 a 7 cerrados con sus PRs y los 8 a 23 abiertos
  con su descripción (AGENTS.md: cada PR, al de su hito).

## Siguiente paso

Al abrir en otro PC: `git switch main && git pull`, `uv sync` y comprobar los
tests, mypy y lint-imports en verde; después, el primer punto sin hacer.

1. Hecho el 2026-10-27: la spec del hito 8 (`docs/specs/hito-8-evals-no-interactivo.md`,
   APROBADA, PR #90; las dudas, respondidas con "la opción más profesional
   y que más valor aporte", §11) y su PR 1, núcleo sin persona (#91:
   límites del turno, `AllowList`, `run_once`).
2. Hecho el 2026-10-27: el PR 2, las evals (`maha eval`, 20 tareas tras
   la decisión del mantenedor de añadir diez difíciles, y la primera línea
   base: `glm-5.3-flash` 94/100, `kimi-k2.7-code` 99/100, 0,60 $ y 12
   minutos por pasada completa; spec §5 y §12).
3. Hecho el 2026-10-28, en `feature/hito-8-print` (PR #95, abierto): el PR 3,
   el modo no interactivo (`maha -p` con `text`, `json` y `stream-json`,
   stdin, `-c`, `-r`, `-m`, `--allow`, límites por opción y códigos de
   salida 0 a 4). Verificado a mano con OpenCode Go. Sin evals: no cambia
   lo que mide la batería (spec §5). Lo aprendido, en la spec §12.14–25.
4. Hecho el 2026-10-30: revisado el PR #95 (un fallo, `--max-cost 0`
   junto a un subcomando, arreglado con su test) e integrado.
5. Hecho el 2026-10-30, en `feature/hito-8-reintentos` (PR #96): el PR 4,
   reintentos ante 429 y 5xx (`RetryPolicy`, `Retry-After`) y modelo de
   respaldo (`fallback_model`, `--fallback-model`), en la terminal, en
   `-p` y en la traza. Verificado a mano con un servidor que responde 503.
   Evals: `glm-5.3-flash` 95/100 (base 94), `kimi-k2.7-code` 99/100
   (igual), con 0 reintentos en las 200 ejecuciones; tres ⚠ de glm
   (tareas 14, 16 y 20). Spec §5 y §12.26–35.
6. Hecho el 2026-10-30: el mantenedor acepta las tres ⚠ del PR 4 (el
   código nuevo no actuó; spec §5), y el PR se integra.
7. Hecho el 2026-10-30, en `feature/hito-8-comandos`: el PR 5, `maha
   models`, `sessions` (y `delete`), `trace`, `stats`, `export` e
   `import`, y `/new` y `/export` en la conversación; el error de `-r` sin
   id nombra `maha sessions`. Verificado a mano. Sin evals: no cambia lo
   que mide la batería (spec §5). Lo aprendido, en la spec §12.36–46.
8. **Agente:** abrir el PR 5 e integrarlo con el CI en verde; después, el
   PR 6, de cierre (`feature/hito-8-cierre`): versión 0.8.0, nota de la
   guía, spec IMPLEMENTADA, los dos README, PROYECTO, HISTORIAL y MAPA.
9. **Humano:** tras el PR 6, el tag `v0.8.0` (o pedírselo al agente).
10. **Agente, si se puede desde el Ubuntu de casa:** lo que sigue POR
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
   `maha 0.7.1`: el hito 8 sube a 0.8.0 al cerrarse).
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
- **Hito 8:** todo hecho. En el PR 5, que el error de `-r` sin id nombre
  también `maha sessions` (spec 8, §12.22); en el PR 4, los reintentos
  ante 429 y 5xx (spec 7, §11); en el PR 3, `--continue`/`--resume` al
  arrancar (spec 6, §11); antes, los límites de tokens y de tiempo por
  turno (spec 4, §11; PR #91) y las descripciones de las herramientas
  medidas en la línea base (spec 4, §5; PR #92).
- **Hito 10:** el modelo no sabe en qué directorio trabaja tras retomar una
  sesión de otro (spec 6, §1.8).
- **Hito 11:** el coste en tokens de las herramientas en cada llamada (~700
  con las cuatro del hito 4; hoy son siete, por medir) y compactar (spec 4,
  §12.14); en la batería de evals, tareas con historial previo y la marca
  `[interrupted by the user]` (spec 6, §5; pasa del hito 8 por decisión
  del mantenedor, spec 8, §11.8).
- **Hito 12:** bifurcar una sesión (spec 8, §11.8).
- **Hito 15:** detectar secretos con otro nombre (`credenciales.txt`)
  mirando el contenido (mejora `2026-10-23`, E5); con el sandbox,
  `run_command` en las evals y tareas de "ejecuta y arregla" (spec 8,
  §11.2).
- **Hito 16:** llamadas a herramientas en paralelo (spec 4, §11); comandos
  que esperan entrada, con los comandos en segundo plano (spec 5, §10);
  varios comandos a la vez, hoy uno a uno por el subreaper (spec 8, §12.10).
- **Hito 21:** lo que se teclea mientras gira el spinner y el eco de `^C`
  se mezclan con la salida (spec 3, §12.10; spec 4, §12.13); ver el texto
  del razonamiento (spec 7).
- **Mejora posible:** refrescar los precios desde models.dev a una caché, a
  petición, si mantener a mano 113 modelos pesa (spec 7, §11). Hoy, con
  OpenCode Go, el coste que vale es el del proveedor.

**POR VERIFICAR** (observaciones de proveedor o de entorno, no deuda: el
código y los tests cubren los dos casos):
- cortar la red a mitad de una respuesta, a mano (spec 3, punto 9 de la
  verificación): no se pudo provocar en WSL; desde el Ubuntu de casa;
- el formato de un error a mitad de stream en OpenCode (spec 3, §10);
- si OpenCode llega a partir los argumentos de una llamada o a mandar JSON
  inválido (spec 4, §10);
- un `refusal` de OpenCode, que no ha mandado nunca (spec 5, §10);
- qué campos de coste manda OpenCode Zen; la cuenta es de Go (spec 7, §10);
- qué mantuvo abierta casi cinco minutos una llamada de Kimi sin contenido
  (probablemente comentarios SSE); ya se corta a los 120 s sin datos (spec
  8, §12.9).

**Límites aceptados por el mantenedor** (cada uno, con su decisión en su
spec; los cuatro, confirmados de nuevo el 2026-10-27):
- los secretos con otro nombre no se detectan hasta el hito 15 (mejora
  `2026-10-23`, E5);
- D7 y D14 de `write_file`/`edit_file` (mejora `2026-10-23`);
- la rotación de `maha.log` no se coordina entre varios `maha` a la vez
  (spec 7, §12.48).

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
- [ ] 8. Evals y modo no interactivo. `v0.8.0`
- [ ] 9. Adaptador de Anthropic. `v0.9.0`
- [ ] 10. System prompt por capas. `v0.10.0`
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
