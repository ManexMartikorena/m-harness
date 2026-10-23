Estado: PROPUESTA (2026-10-23) → APROBADA (2026-10-23, por el humano, sin cambios)

# Spec — Mejora: cero deuda antes de cerrar el hito 5

Referencias: `docs/DESIGN.md` §3, §5, §6 y §10; spec del hito 5
(`docs/specs/hito-5-permisos.md`, §10 y §12); `docs/ESTADO.md`
("Pendientes"); `AGENTS.md` (regla nueva: ningún fallo conocido se deja sin
arreglar por decisión del agente).

## 0. Alcance

**El problema.** El hito 5 arrastra fallos conocidos: los "límites
aceptados" que anotó el agente (spec 5, §12.10), riesgos de §10, pendientes
de ESTADO y lo que encontró una auditoría del código el 2026-10-23. El
mantenedor quiere cerrar el hito 5 con cero deuda técnica y la arquitectura
hexagonal limpia, antes del hito 6.

**Lo que hace este cambio.** Arregla todos los fallos, limpia la
arquitectura y el código, y deja anotado, con la decisión del mantenedor, lo
poco que no es un fallo o no se puede cerrar.

Dentro de alcance: todo lo de §1 (A1–A7, B1–B4, C, D, E).

**Fuera de alcance** (decisión del mantenedor, 2026-10-23): lo que DESIGN
asigna a hitos futuros, que no es deuda sino plan: coste y tokens de
razonamiento (7), reintentos (7-8), límites por turno y evals (8),
compactación (11), sandbox (14), llamadas en paralelo (15) e interfaz (19).

## 1. Decisiones de fondo

Todas propuestas por el agente y aprobadas por el mantenedor el 2026-10-23.

### A. Fallos de la auditoría (se arreglan todos, test primero)

1. **Argumentos muy anidados tumban la terminal.** `_call` (en
   `adapters/cli/conversation.py`) captura `ValueError` pero no
   `RecursionError`. Se captura y se enseñan los argumentos tal cual.
2. **Texto no confiable con caracteres de control en la terminal.** El
   nombre y los argumentos de la llamada, el `summary`, el texto del modelo y
   la pregunta se pintan con ESC, `\r` y similares. Pueden falsear lo que ves
   justo antes de aprobar. Un solo saneador, `adapters/cli/text.py`
   (`clean()`): los caracteres de control (categoría Unicode `Cc`, salvo
   `\n` y `\t`) y los de dirección bidi (U+202A–U+202E, U+2066–U+2069)
   salen como `\x1b`, `‮`… Lo usa toda la salida de texto no confiable,
   y `TerminalApproval` (pieza 14).
3. **`write_file` y `edit_file` también tienen la carrera de la FIFO.**
   `_current_bytes` hace `stat` y luego `read_bytes()`. Se abre con
   `_open_regular()` y el tamaño sale de `fstat`. Corrige spec 5, §12.11,
   que decía que no les afectaba.
4. **`grep` sobre un solo fichero grande o binario dice `(no matches)`.**
   Pasa a `ToolError`: `file too large to search (N.N MiB, max M MiB)` y
   `binary file, not searchable`. El tamaño es metadato (antes de preguntar);
   binario depende del contenido (después de aprobar, como fix 1 del PR 2).
   Al recorrer se siguen saltando sin error.
5. **Una ruta con NUL da `internal error`.** `Workspace.resolve()` da
   `ToolError("invalid path: <ruta>")` ante el `ValueError`.
6. **`is_secret` distingue mayúsculas.** En `/mnt/c` (WSL) o macOS, `.ENV`
   o `ID_RSA` son el mismo fichero. Se compara con `casefold()`.
7. **`complete()` deja escapar errores de `httpx`.** Captura
   `httpx.RequestError` (no solo `TransportError`) y pasa el motivo por
   `_safe()`, como `stream()`.

### B. Arquitectura

1. **Las reglas de permisos de ruta van al dominio.** Hoy viven en
   `adapters/tools/files.py`. Pasan a `domain/paths.py` como funciones puras
   sobre rutas ya resueltas: qué avisos lleva leer y qué avisos lleva
   escribir (fuera, secreto, directorio que ejecuta código). El adaptador
   solo resuelve rutas y mira el disco. Las reutilizarán `run_command`, MCP y
   el sandbox.
2. **`Tool.approval()` pasa a `async`.** Corrige DESIGN §5 y spec 5, §1.2.
   Por qué: una pregunta puede necesitar E/S (leer el fichero, o un servidor
   MCP en el hito 16) y no debe ser síncrona en el bucle. El coste del diff
   se acota en D12.
3. **Un solo lector de la entrada.** `StdinLines` se crea en `bootstrap` y
   se inyecta en `converse` y en `TerminalApproval` (pieza 17). Dos lectores
   sobre el mismo descriptor perderían líneas.
4. **Qué variables del entorno llegan a un comando lo decide el dominio.**
   `domain/environment.py` (`command_env()`, función pura). El puerto recibe
   el entorno ya filtrado: `CommandRunner.run(command, *, cwd, timeout,
   env)`, como ya dice DESIGN §6. Va en las piezas 10 a 12.

### C. Limpieza

- Un solo mecanismo para "lo que se preguntó" (`_Asked` y `_Shown` se
  unen) y un solo texto para `changed after the question`.
- Los `summary` de `list_dir`, `glob` y `grep` comparten función.
- El nombre `m-harness` en un solo sitio.
- Comentarios desfasados al día (`ports/model.py`, `domain/tools.py`,
  `domain/paths.py`, `conversation.py`).
- El aviso de escribir un secreto deja de decir "its content goes to the
  model provider" (eso es leer): `secret file: it may hold credentials`.
- DESIGN §3 y §5 con los nombres reales (`ports/tools.py`,
  `application/agent.py`, `domain/agent_events.py`, `ToolSpec` en
  `domain/model.py`, `Tool.params`, `summary()`).

### D. Escritura de ficheros (spec 5, §12.10)

1. **Enlaces duros** y 2. **propietario, grupo, atributos extendidos y
   ACL.** El temporal copia propietario y grupo (`fchown`) y los atributos
   extendidos (en Linux, las ACL son atributos extendidos). Si el fichero
   tiene más de un enlace duro, o algo de eso no se puede copiar, se escribe
   **en el sitio** (abrir el original y reescribirlo, con `fsync`). Se pierde
   la atomicidad solo en ese caso, a cambio de no romper el enlace ni los
   permisos.
3. **Carpetas creadas antes de un fallo:** se borran, de dentro afuera, si
   quedan vacías.
4. **`fsync` de las carpetas padre nuevas:** también.
5. **Solo POSIX:** no es un fallo. La plataforma es Linux (spec 1; en
   Windows, WSL). Se anota en DESIGN §7.
6. **Nombres largos:** el temporal pasa a `.maha-<16 hex>.tmp`, de longitud
   fija.
7. **Hueco entre la última comprobación y el reemplazo:** POSIX no tiene
   "comparar y cambiar" para ficheros; no se puede cerrar del todo. Se reduce
   al mínimo: la comparación lee del mismo descriptor y el reemplazo va justo
   después. Queda **aceptado por el mantenedor** (2026-10-23).
8. **Apariciones solapadas:** `old_string` cuenta también las solapadas
   (`"aa"` en `"aaa"` son 2). Si hay más de una y no hay `replace_all`, es
   ambiguo: error `appears N times`.
9. y 10. **Saltos de línea mezclados y `\r` solos.** La adaptación a CRLF se
   generaliza: si no hay coincidencia exacta, cada salto de línea de
   `old_string` coincide con `\r\n`, `\n` o `\r`. Los saltos de `new_string`
   se escriben con el estilo del primer salto del texto encontrado (o del
   fichero, si el encontrado no tiene). Sustituye a la regla 9b del PR 2.
11. **Un fallo del `fsync` de la carpeta no deja rastro:** hito 7 (trazas),
   decisión del mantenedor.
12. **`difflib` lento.** Antes de `difflib` se quitan las líneas comunes del
   principio y del final (lineal). Si lo que queda pasa de 4000 líneas entre
   los dos lados, no se calcula el diff: la pregunta enseña `(diff too large:
   lines A–B change, N → M lines)` y las primeras 20 líneas nuevas.
13. **Directorios y ficheros que ejecutan código:** escribir en ellos
   siempre pregunta (`scope=None`), como `.git`. Directorios: `.git`,
   `.github`, `.husky`, `.vscode`, `.maha`. Ficheros:
   `.pre-commit-config.yaml`, `.envrc`. Aviso: `runs code: hooks, CI or
   editor tasks here can run code` (para `.maha`, `maha configuration`).
14. **Con aviso, un `old_string` mal puesto pregunta y luego falla:** se
   mantiene. Es el precio de no filtrar secretos (fix 1 del PR 2, decisión
   del mantenedor).

### E. Riesgos y pendientes

1. **Credenciales en el entorno de un comando:** lista de permitidas, no de
   prohibidas. El comando recibe solo `PATH`, `HOME`, `USER`, `LOGNAME`,
   `SHELL`, `LANG`, `LANGUAGE`, `LC_*`, `TERM`, `COLORTERM`, `NO_COLOR`,
   `TZ`, `TMPDIR`, `PWD`, `XDG_*` y `VIRTUAL_ENV`. Nada más (tampoco
   `SSH_AUTH_SOCK`: da acceso a tus claves SSH). Corrige spec 5, §1.9.
2. **Procesos que salen de su grupo (`setsid`):** hito 14 (sandbox),
   decisión del mantenedor.
3. **`.git/config` y `.git-credentials`:** secretos. Leerlos pregunta.
4. **Una excepción no prevista tras ejecutar pierde el turno:** el bucle
   guarda lo ejecutado ante cualquier `Exception` (además de las de D4), y
   la vuelve a lanzar.
5. **Secretos con otro nombre:** se mantiene la detección por nombre,
   decisión del mantenedor. Mirar el contenido es otra pieza (hito 14).
6. **`.gitignore`:** `glob` y `grep`, al recorrer, saltan lo que ignoran los
   `.gitignore` del árbol (desde la raíz del directorio de trabajo hacia
   abajo) y `.git/info/exclude`. Reglas: comentarios, `!`, `/` final (solo
   carpetas), `/` inicial o en medio (anclado a la carpeta del
   `.gitignore`), `*`, `?`, `**`, `[...]` y `\`. La traducción a regex es
   pura: `domain/gitignore.py`. A mano, sin dependencias (la librería
   habitual es `pathspec`). `list_dir` no filtra.

## 2. En la industria

| Pieza | M-Harness | Alternativas |
|---|---|---|
| Saneado de la terminal | Escapar `Cc` y bidi | `rich` (`Text` sin markup); `repr()` |
| Escritura atómica | Temporal + `os.replace`, en el sitio si hay enlaces | `atomicwrites` (archivada), `python-atomicwrites`; editores: "backupcopy" de Vim |
| Entorno del comando | Lista de permitidas | Herencia con filtros por patrón; contenedores |
| `.gitignore` | Traductor propio | `pathspec`, `ignore` (crate de ripgrep) |

## 3. Diseño de detalle

Ficheros nuevos: `adapters/cli/text.py`, `domain/environment.py`,
`domain/gitignore.py`. Cambian: `domain/paths.py`, `ports/tools.py`,
`application/agent.py`, `adapters/tools/files.py`,
`adapters/cli/conversation.py`, `adapters/models/openai_chat.py` y los
fakes. `docs/MAPA.md` al día en cada PR.

## 4. Plan de tests

Un test por cada fallo, escrito antes del arreglo y visto fallar:
1. A1–A7: uno por punto (anidado en la terminal; ESC y bidi en nombre,
   argumentos, summary y texto; FIFO cambiada en `write_file` y `edit_file`;
   `grep` sobre un fichero grande y uno binario; NUL; `.ENV` e `ID_RSA`;
   `DecodingError` en `complete()`).
2. B1: las reglas de ruta en `tests/unit/test_paths.py`, sin disco. B2: los
   tests del bucle y de las herramientas con `await`.
3. D1–D4, D6, D8–D10, D12, D13: uno por punto, en `tmp_path`.
4. E1: el comando no recibe una variable inventada (`MI_CLAVE`) ni
   `SSH_AUTH_SOCK`; sí `PATH`. E3: `.git/config` pregunta. E4: un `OSError`
   del `gate` tras una ejecución guarda el turno. E6: tabla de casos de
   `domain/gitignore.py` y `grep`/`glob` en un árbol con `.gitignore`.

## 5. Evals

No aplica todavía (hito 8).

## 6. Orden de piezas para el implementador

Cada punto es un commit, en verde.

**PR 1** (`fix/fallos-auditoria`): A1–A7, E3 y E4, un commit cada uno.

**PR 2** (`feature/deuda-arquitectura`): B1, B2 y C, un commit por punto, y
el mapa.

**PR 3** (`feature/deuda-escritura`): D1–D4, D6–D10, D12 y D13, un commit por
punto (D1 y D2 juntos; D9 y D10 juntos).

**PR 4** (`feature/gitignore`): E6, en dos commits (traductor y uso).

Después, el hito 5 sigue por su spec: PR 3 (comandos, con B4 y E1), PR 4
(terminal, con A2 y B3) y PR 5 (cierre y `v0.5.0`).

## 7. Verificación a mano

Dentro de la del hito 5 (spec 5, §7), más:
1. "Lee .ENV" en `/mnt/c/…` → pregunta.
2. "Ejecuta env" → solo las variables de la lista de E1.
3. "Busca X" en un árbol con `.gitignore` → no salen los ignorados.

## 8. Lo que no viaja por git y lo que necesita la release

Nada: ni variables ni configuración.

## 9. Guía

Entra en la nota del hito 5 (`docs/guia/05-permisos.md`): el saneado de la
terminal, la lista de variables permitidas y la escritura en el sitio.

## 10. Riesgos

- **E1 rompe comandos que necesitan otra variable** (`SSH_AUTH_SOCK` para
  `git push` por SSH, o un token de un registro). Es lo buscado: las
  credenciales no llegan al modelo. Si molesta, se valora una lista
  configurable, con su spec.
- **D1/D2, escritura en el sitio:** si se corta a mitad, el fichero queda a
  medias. Solo pasa con enlaces duros o atributos que no se pueden copiar.

## 11. Decisiones

Del humano (2026-10-23): aprueba todas las recomendaciones del agente, sin
cambios, y pide arreglar todo: A1–A7, B1–B4, C, D1–D4, D6, D8–D10, D12, D13,
E1, E3, E4 y E6. Mantener D14 y E5; aceptar D7; D5 no es un fallo; D11 al
hito 7 y E2 al hito 14.

## 12. Aprendido al implementar (2026-10-23)

**PR 1** (`fix/fallos-auditoria`), un commit por punto, cada test visto
fallar antes del arreglo:
1. A1 (`7235142`): `except ValueError, RecursionError`, como el bucle.
2. A2 (`4e908f2`): `clean()` también en `fail()` (`cli/app.py`), porque el
   mensaje puede citar un `.maha/config.toml` ajeno. `\r` sale como
   `\x0d`. `json.dumps` ya escribía ESC como `\u001b` en los argumentos; el
   bidi no lo escapaba.
3. A3 (`b99573b`): el test del `stat` que falla (fix 3 del PR 2) pasa a
   simular el fallo en `os.fstat`, que es donde se mira ahora el tamaño.
4. A4 (`ec235c3`): sin aviso, `approval()` no comprueba nada y los errores
   salen en `run()`. Con aviso, el tamaño sale antes de preguntar
   (`_check_grep`). La FIFO cambiada sobre un fichero suelto da `not a
   regular file` (antes `(no matches)`). `MIB` sube al principio del
   módulo.
5. A6 (`52dc6ba`): los nombres de `SECRET_DIRS`, `SECRET_NAMES` y
   `NOT_SECRET` van en minúsculas y se compara con `casefold()`.
6. E3 (`c64207b`): escribir en `.git/config` lleva ahora tres avisos
   posibles (fuera, secreto, git).
7. E4 (`e084fbd`): `except BaseException`. La llamada en curso recibe
   `cancelled by the user` con Ctrl+C y `interrupted by an internal error`
   con cualquier otra excepción.

**PR 2** (`feature/deuda-arquitectura`):
8. B2 (`f8b38f8`): primero, porque cambia el puerto. Las 116 llamadas a
   `approval()` de los tests se pasaron con un transformador de `ast` (añade
   `await`, con paréntesis si sigue un atributo, y vuelve `async` las
   funciones que las contienen, en cascada). En el bucle, `_prepare()` pasa
   a `async`.
9. B1 (`9d95f18`): `domain/paths.py` gana `is_inside()`, `is_secret_at()`,
   `read_warning()`, `change_warning()` y los textos de los avisos.
   `Workspace` delega en ellas. Tests sin disco en `tests/unit/test_paths.py`.
10. C, en cinco commits: `_Asked` absorbe a `_Shown` (`95014d5`);
    `_count_lines()` para `list_dir`, `glob` y `grep` (`eaddf2f`);
    `DISTRIBUTION` y `__version__` en `mharness/__init__.py`, fuera de las
    capas (`ea20fa2`); comentarios (`397e5e4`); aviso `SECRET_CHANGE` al
    escribir un secreto (`bb98770`). DESIGN §3 y §5 ya se corrigieron con
    la spec (#34).

**PR 3** (`feature/deuda-escritura`):
11. D6 (`689adf7`): `.maha-<16 hex>.tmp`.
12. D3 (`b5bd7d3`) y D4 (`fb79e82`): `_make_folders()` crea las carpetas una
    a una y las apunta; si la escritura falla, `_remove_folders()` las borra
    si siguen vacías; si va bien, `fsync` de la carpeta padre de cada una.
13. D1 y D2 (`bbce66e`): `_copy_identity()` (propietario y grupo antes que
    el modo, porque cambiar el propietario puede quitar los bits setuid; y
    los atributos extendidos). Un sistema de ficheros sin atributos
    extendidos (`ENOTSUP`) no obliga a escribir en el sitio. La escritura en
    el sitio abre con `O_NONBLOCK` (una FIFO falla en vez de bloquear) y,
    si falla, intenta volver a poner los bytes viejos.
14. D7 (`7a871a6`): antes de `os.replace`, se vuelve a leer el fichero y se
    compara con lo que mostró la pregunta; en el sitio, sobre el mismo
    descriptor (`O_RDWR`). Un cambio después de esa comparación sigue
    ganando: el hueco aceptado por el mantenedor.
15. D8 (`552804b`): sustituye la decisión 10 del PR 2 (no contar las
    solapadas); se borra su test. Con `replace_all`, se reemplaza de
    izquierda a derecha sin solapar, y el resultado cuenta los reemplazos
    hechos.
16. D9 y D10 (`909a863`): sustituyen la regla 9b. Cambian dos tests: un
    `old_string` con CRLF ya coincide en un fichero LF, y el caso A1 (saltos
    mezclados) ya coincide.
17. D12 (`d6631a1`): `_shift()` corrige los números de línea de la cabecera
    del diff recortado. El texto usa guion (`lines 2-9`), no raya: ruff
    (RUF001) no la admite en el código.
18. D13 (`9eade8d`): dentro del directorio de trabajo, solo cuentan las
    partes de la ruta por debajo de la raíz. Eso cierra el límite del fix 6
    del PR 2 (un directorio de trabajo dentro de `.git` avisaba en cada
    escritura). Si hay varios, se avisa uno: `.git`, luego lo que ejecuta
    código, luego `.maha`.
