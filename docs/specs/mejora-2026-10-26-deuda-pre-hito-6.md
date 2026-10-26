Estado: PROPUESTA (2026-10-26) → APROBADA (2026-10-26, por el humano, sin
cambios)

# Spec — Mejora: cero deuda antes del hito 6

Referencias: `docs/DESIGN.md` §5 y §10; spec del hito 5 (§1.9, §1.10 y
§10); spec `mejora-2026-10-23-deuda-hito-5` (A6, D, E3 y E6); `AGENTS.md`
(ningún fallo conocido se deja sin arreglar por decisión del agente).

## 0. Alcance

**El problema.** Antes de empezar el hito 6, el mantenedor pidió asegurar
que no queda deuda técnica. El 2026-10-26, dos auditorías independientes del
código (una del bucle, la aplicación y la terminal; otra de las
herramientas, los comandos y el adaptador de OpenAI) encontraron fallos que
las tres auditorías del 2026-10-23 no vieron. Los más graves dejan que un
secreto llegue al modelo sin preguntar, o que se apruebe algo que no se ve.

**Lo que hace este cambio.** Arregla todos los fallos, cada uno con un test
que lo reproduce primero, en dos PRs. Después el hito 6 sigue por su spec.

Dentro de alcance: todo lo de §1 (A1–A6, B1–B8 y C1).

**Fuera de alcance:** lo que DESIGN asigna a hitos futuros, que es plan y no
deuda (mismo criterio que la mejora del 2026-10-23). Y:
- `ModelClient.complete()` sin uso en producción: se queda en el puerto por
  decisión del mantenedor (spec 3, §11, duda 1). No es deuda.
- Detectar secretos mirando su contenido: hito 14 (mejora 2026-10-23, E5).
  Aquí solo se completa la lista de **nombres** conocidos (A5).

## 1. Decisiones de fondo

Lo encontrado por las auditorías, verificado por el agente en el código. Lo
marcado "reproducido" se reprodujo con un script en un directorio desechable,
con datos inventados.

### A. Seguridad

1. **Un secreto detrás de un enlace se lee sin preguntar** (reproducido).
   `read_file`, `grep` de un fichero, `list_dir`, `write_file` y
   `edit_file` miran si es secreta la ruta **resuelta**, no la pedida. Con
   `.env -> config/app.env`, `read_file(".env")` no pregunta y devuelve la
   clave. `_Walk` (recorrer) ya mira las dos. **Arreglo:** `Workspace`
   avisa si es secreta la ruta pedida (relativa a la raíz) **o** la
   resuelta, en todas las herramientas.
2. **Una línea guardada responde a la pregunta** (reproducido en una
   pseudoterminal). `StdinLines` guarda en su búfer lo que se pegó o tecleó
   antes de tiempo. Si pegas `borra los temporales\ny\n`, la `y` contesta la
   siguiente pregunta y la herramienta se ejecuta. **Arreglo:** antes de
   cada pregunta, `TerminalApproval` descarta el búfer de `StdinLines` y la
   entrada pendiente de la terminal (`termios.tcflush(fd, TCIFLUSH)`). Si
   descartó algo, lo dice: `(discarded typed input)`. Solo se descarta lo
   tecleado **antes** de ver la pregunta.
3. **Lo que se aprueba no se ve entero** (reproducido). La pregunta corta
   cada línea a 200 caracteres, y `run_command` pone el comando solo en el
   título. Un `; curl … | sh` tras 200 caracteres no se ve. Con más de 60
   líneas (un diff), el resto tampoco. **Arreglo:**
   - ninguna línea de la pregunta se corta: se parte en varias (las líneas
     de continuación empiezan con `│ ↪`);
   - si el detalle pasa de 60 líneas, se enseñan 60 y se ofrece
     `[v] view all`, que lo pinta entero y vuelve a preguntar.
4. **Al cerrar la ventana o con `kill`, el comando sigue vivo**
   (reproducido). Solo se atiende SIGINT. El comando corre en su propio
   grupo y no recibe el SIGHUP de la terminal. **Arreglo:** SIGHUP y SIGTERM
   cancelan la tarea igual que Ctrl+C (el runner mata el grupo), y `maha`
   sale con `128 + señal`. Sin preguntar ni volver al prompt.
5. **Faltan secretos conocidos** (reproducido: todos dan `False`). DESIGN
   §10 promete "credenciales de la nube y similares". **Arreglo:**
   - nombres: `id_ecdsa*`, `id_dsa*`, `*.p12`, `*.pfx`, `*.env`
     (`prod.env`), `.envrc`, `.npmrc`, `.pypirc`, `.vault-token`,
     `.terraformrc`, `credentials.tfrc.json`;
   - carpetas: `.azure`;
   - rutas: `.config/gh`, `.config/gcloud`, `.cargo/credentials*` y
     `config` dentro de `.git/modules/` (mismo motivo que E3: la URL del
     remoto puede llevar un token);
   - `.env.example` sigue sin ser secreto; se añade `*.env.example`.
6. **Falta código que se ejecuta solo** (leído en el código).
   `change_warning` protege `.github`, pero no otros sitios que ejecutan lo
   que se escribe en ellos. **Arreglo:** pregunta siempre, sin "toda la
   sesión", también en `.gitlab-ci.yml`, `.circleci`, `.forgejo`, `.gitea`,
   `.githooks`, `.devcontainer`, `.idea` y `.claude`.

### B. Corrección

1. **Un error no previsto tira `maha`** (reproducido). `_answer` solo
   captura `ModelError`. Un `OSError` al leer la respuesta de la pregunta
   acaba en traceback, aunque el `Agent` ya guardó el turno. **Arreglo:**
   `_answer` captura `Exception`, pinta `error: internal: <tipo>: <mensaje>`
   y vuelve al prompt.
2. **Los argumentos de más se aceptan en silencio** (leído). Ningún modelo
   de parámetros prohíbe campos extra: `{"command": "…",
   "timeout_seconds": 600}` ignora el segundo, y la línea `→` lo enseña como
   si contara. **Arreglo:** `extra="forbid"` en todos los parámetros (el
   JSON Schema lleva `additionalProperties: false`). Un test de arquitectura
   recorre las siete herramientas.
3. **Un resultado que no es texto corta el turno** (leído). En `Agent._run`,
   `ToolResultBlock(...)` va fuera del `try`: una herramienta que devuelva
   `None` lanza `ValidationError`. **Arreglo:** si `run()` no devuelve
   `str`, es un `internal error` de la herramienta.
4. **Se reemplaza un fichero de solo lectura** (reproducido). La escritura
   atómica renombra encima de un fichero `0444` sin avisar. **Arreglo,
   decisión del mantenedor:** `write_file` y `edit_file` dan
   `ToolError("read-only file: …")` en `approval()`, antes de preguntar. Para
   cambiarlo, `run_command` (`chmod`), que pregunta.
5. **No se edita un fichero escribible en una carpeta que no lo es**
   (reproducido). Crear el temporal da `EACCES` y no se pasa a la escritura
   en el sitio, que ya existe. **Arreglo:** ante `PermissionError` al crear
   el temporal, escribir en el sitio.
6. **Un fichero enorme congela el bucle** (reproducido: 200 MB lo paran
   0,18 s). `read_file` lee entero un fichero de una sola línea o uno largo
   con un `offset` alto, sin tope; `list_dir` ordena la carpeta entera antes
   de cortar a 500. **Arreglo:** `read_file` lee por trozos y para en cuanto
   tiene lo que va a devolver, con un tope de bytes leídos
   (`READ_MAX_SCAN_BYTES`, 64 MiB) que da un error claro al pasarlo;
   `list_dir` usa `os.scandir` y deja de leer pasado el tope, diciendo que
   hay más.
7. **`.gitignore` difiere de git en casos raros** (reproducido contra `git
   check-ignore`). Clases POSIX (`[[:digit:]]`), `]` escapado en una clase
   (`[\]]`), `[` sin cerrar (git no casa nada), `\` al final y `\\ ` antes
   de un espacio. **Arreglo, decisión del mantenedor:** se arreglan todos.
   Los casos esperados se toman de `git check-ignore` hoy y quedan como
   tabla en el test (el CI no llama a git).
8. **Ctrl+C durante la pregunta deja `[interrupted]` en su misma línea**
   (leído). **Arreglo:** salto de línea si había una pregunta abierta.

### C. Documentación

1. **DESIGN §5 lista `max_tokens` en `ModelRequest`, y no existe.** Se
   aplazó en la spec 2 (§1.6) sin anotarlo en DESIGN. **Arreglo:** la nota,
   con fecha y spec.

## 2. En la industria

| Pieza | M-Harness | Alternativas |
|---|---|---|
| Entrada adelantada | Descartar antes de preguntar (`tcflush`) | `prompt_toolkit` (lee cada pregunta con su propio prompt); `termios` a mano |
| Secretos por nombre | Lista propia en el dominio | `.gitignore` de plantillas (github/gitignore); detectores por contenido (gitleaks, detect-secrets) |
| Señales de cierre | SIGHUP y SIGTERM cancelan como Ctrl+C | `PR_SET_PDEATHSIG` en el hijo (Linux); un supervisor de procesos |

## 3. Diseño de detalle

No hay ficheros nuevos. Cambian: `domain/paths.py`, `domain/gitignore.py`,
`application/agent.py`, `adapters/tools/files.py`, `adapters/tools/shell.py`,
`adapters/cli/approval.py`, `adapters/cli/input.py` y
`adapters/cli/conversation.py`, más sus tests. `docs/MAPA.md` al día en
cada PR.

## 4. Plan de tests

Un test por cada fallo, escrito antes del arreglo y visto fallar:
1. A1: `.env -> config/app.env` y `.ssh -> keys/` preguntan al leer, buscar
   y escribir (en `tmp_path`).
2. A2: con una pseudoterminal, una `y` tecleada antes de la pregunta no
   aprueba; el búfer de `StdinLines` también se descarta.
3. A3: un comando de 300 caracteres sale entero; un detalle de 61 líneas
   ofrece `v`, y `v` lo enseña entero y vuelve a preguntar.
4. A4: SIGTERM y SIGHUP durante un `sleep` aprobado: `maha` sale con 143 y
   129, y el grupo del comando no sobrevive.
5. A5 y A6: un caso por nombre y ruta en `tests/unit/test_paths.py`.
6. B1: un `OSError` del gate → `error: internal: …` y el prompt sigue.
7. B2: argumentos con un campo de más → `invalid arguments`; test de
   arquitectura sobre las siete.
8. B3: `FakeTool` que devuelve `None` → `internal error`, el turno sigue.
9. B4 y B5: en `tmp_path` con `chmod` (se saltan si se corre como root).
10. B6: un fichero de una línea por encima del tope da el error; una carpeta
    con 600 entradas da 500 y "more".
11. B7: la tabla de casos de git.
12. B8: Ctrl+C durante la pregunta (`HangingApproval`): `[interrupted]` en
    su propia línea.

## 5. Evals

No aplica todavía (hito 8).

## 6. Orden de piezas para el implementador

Cada punto es un commit, en verde, con su test primero.

**PR 1** (`fix/seguridad-pre-hito-6`): A1–A6, un commit cada uno, y el mapa.

**PR 2** (`fix/correccion-pre-hito-6`): B1–B8, un commit cada uno, C1 y el
mapa.

Después, el PR de la spec del hito 6 (rama `docs/spec-hito-6-sesiones`, ya
escrita).

## 7. Verificación a mano

En un directorio desechable, con el modelo real:
1. `.env` como enlace a `config/app.env` (inventado): "lee .env" → pregunta
   con aviso de secreto.
2. Pegar "ejecuta ls\ny" de una vez → la pregunta espera; `(discarded typed
   input)`.
3. "Ejecuta echo" con un argumento de 300 caracteres → se ve entero.
4. "Ejecuta sleep 300", aprobar, y cerrar la terminal → `pgrep sleep` no lo
   encuentra.
5. `chmod a-w notas.txt` y "cambia notas.txt" → `read-only file`, sin
   pregunta.

## 8. Lo que no viaja por git y lo que necesita la release

Nada: ni variables ni configuración.

## 9. Guía

Entra en la nota del hito 5 (`docs/guia/05-permisos.md`): la entrada
adelantada que se descarta, la pregunta que nunca corta, el secreto detrás
de un enlace y las señales de cierre.

## 10. Riesgos

- **A2 descarta lo que tecleaste a propósito antes de la pregunta.** Es lo
  buscado: solo cuenta lo que se escribe viendo la pregunta. El aviso lo
  dice.
- **A5 pregunta más:** `*.env` también casa ficheros que no son secretos.
  Se prefiere preguntar de más.
- **A3 con un detalle enorme:** `[v]` puede pintar miles de líneas. Es
  decisión de quien lo pide.

## 11. Decisiones

Del humano (2026-10-26):
1. Se arregla por una spec de mejora, como la del 2026-10-23, antes del PR
   de la spec del hito 6.
2. B4: un fichero de solo lectura da error; no se ofrece aprobarlo.
3. B7: los casos raros de `.gitignore` se arreglan; no son un límite
   aceptado.

Propuestas del agente, aprobadas por el humano (2026-10-26, "acepto"): los
arreglos de A1–A6, B1–B3, B5, B6, B8 y C1, y los dos PRs de §6. El
mantenedor da permiso al agente para push, PRs, integrarlos con el CI en
verde y publicar `v0.5.2` con estos arreglos.

## 12. Aprendido al implementar (2026-10-26)

**PR 1** (`fix/seguridad-pre-hito-6`), un commit por punto, cada test visto
fallar antes del arreglo:
1. A1 (`d284799`): `Workspace.asked()` da la ruta pedida sin resolver
   (`os.path.normpath`), y `read_warning`/`change_warning` miran las dos.
   Vale también para lo que ejecuta código: escribir por un enlace llamado
   `.github` avisa.
2. A2 (`f30a68a`): `StdinLines.discard()`. `select` dice si hay una línea
   entera esperando y `tcflush` tira también la que está a medias. La
   prueba de punta a punta tecleaba la `y` antes de la pregunta: ahora la
   teclea tras el descarte, y comprueba que la de antes se descartó.
3. A3 (`bd87b88`): `v` pinta **el resto** del detalle (no las 60 primeras
   otra vez) y vuelve a preguntar. *(Corregido al implementarlo: §1 decía
   "lo pinta entero".)*
4. A4 (`de7a5da`): sin el arreglo, el SIGTERM del test mataba a pytest
   entero. El test del comando real reutiliza los ayudantes de
   `test_local_runner.py`.
5. A5 (`b3bdcde`): `.envrc` es ahora secreto y además ejecuta código: su
   aviso de escritura lleva los dos motivos. No hizo falta `*.env.example`:
   `*.env` no casa `prod.env.example`. *(Corregido al implementarlo.)*
6. A6 (`f6d9d0a`): también `.gitlab` (plantillas e `include` del CI de
   GitLab), además de `.gitlab-ci.yml`.
