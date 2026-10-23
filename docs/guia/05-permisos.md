# 05. Permisos: el modelo propone, el código decide

Hito 5 (`v0.5.0`). Specs: `docs/specs/hito-5-permisos.md` y
`docs/specs/mejora-2026-10-23-deuda-hito-5.md`. Diseño: `docs/DESIGN.md` §5,
§6, §8 y §10.

## El problema

Hasta el hito 4, `maha` solo mira. Un agente de código tiene que escribir,
editar y ejecutar comandos. Eso tiene efecto en tu máquina:
- un `rm` o una edición mala no se deshacen solos;
- lo que el modelo lee acaba en el servidor del proveedor;
- un comando puede mandar tus claves al modelo con un simple `env`.

La regla: **nada con efecto pasa sin que tú lo apruebes**, y eso lo decide
el código, no una frase en el prompt.

## Cómo lo resuelve M-Harness

### 1. Leer frente a efecto

Cada herramienta declara su permiso:
- `read`: se ejecuta sin preguntar, salvo que la ruta pida pregunta (fuera
  del directorio o un secreto);
- `effect`: **siempre** pregunta.

Antes de ejecutar, el bucle llama a `tool.approval(params)`. La herramienta
dice qué preguntar, porque solo ella sabe calcular el diff o ver si una ruta
sale del directorio. El bucle pregunta y decide.

```python
class Tool[P: BaseModel](Protocol):
    async def approval(self, params: P) -> ApprovalRequest | None: ...
    async def run(self, params: P) -> str: ...
```

Una herramienta `effect` cuyo `approval()` devuelve `None` **no se
ejecuta**: el bucle lo trata como un fallo nuestro. Falla cerrado: ante la
duda, no se hace.

### 2. La pregunta

Salida real con `glm-5.3-flash`:

```
> Cambia la segunda línea de notas.txt por 'tres' con edit_file.
  → edit_file(new_string="tres", old_string="dos", path="notas.txt")
  ┌ edit notas.txt
  │ @@ -1,2 +1,2 @@
  │  uno
  │ -dos
  │ +tres
  └ Allow? [y] yes · [a] always this session · [n] no: n
  ✗ error: the user denied this call
  [denied: tell maha how to continue]
```

- `y`: una vez. `a`: toda la sesión, para su **ámbito**. `n`: no.
- **Una negativa termina el turno.** Si dices que no, quieres decir algo; si
  el bucle siguiera, el modelo probaría otra cosa y volvería a preguntar.
  Escribes tú.
- El modelo se entera: en el turno siguiente contestó "la edición fue
  denegada, así que `notas.txt` sigue conteniendo 'uno' y 'dos'".

**Ámbitos de "toda la sesión":**

| Herramienta | Qué cubre `a` |
|---|---|
| `write_file`, `edit_file` | Todas las escrituras, o todas las ediciones |
| `run_command` | Solo **ese comando exacto** (`ls -la`, no `ls`) |

### 3. Lo que nunca es "para la sesión"

Sin opción `a`, una a una:
- **Fuera del directorio de trabajo**, también para leer.
- **Secretos:** `.env`, claves, `~/.ssh`… sin distinguir mayúsculas
  (`.ENV` en `/mnt/c` es el mismo fichero), y también `.git/config`, que
  puede llevar un token en la URL.
- **Lo que ejecuta código solo:** `.git`, `.github`, `.husky`, `.vscode`,
  `.pre-commit-config.yaml`, `.envrc` y la configuración `.maha`.

```
  ┌ read /etc/hostname
  │ /etc/hostname
  │ ! outside the working directory
  └ Allow? [y] yes · [n] no:
```

**Con aviso, la pregunta va antes que el contenido.** Si `edit_file` dijera
"old_string not found" antes de preguntar, el modelo podría adivinar un
secreto letra a letra sin que nadie se enterara.

**La pregunta no puede mentir.** Todo lo que viene del modelo o de un
fichero se limpia antes de pintarlo: los caracteres de control (ESC, `\r`)
y los de dirección del texto (bidi) salen escapados, como `\x1b`. Si no, un
fichero podría repintar la pantalla justo encima de la pregunta. El título
va siempre en **una línea**: un comando con 80 saltos de línea dejaría su
principio fuera de la pantalla, y con `a` lo aprobarías para la sesión.

**Sin terminal, se deniega todo.** Con `maha < notas.txt`, la "respuesta"
sería la línea siguiente del fichero, y una `y` aprobaría un comando:

```
  → write_file(content="hola", path="prohibido.txt")
  (denied: input is not a terminal)
```

### 4. Escribir sin romper nada

- **Atómico:** se escribe un temporal en la misma carpeta, se lleva al disco
  (`fsync`) y se renombra encima (`os.replace`). Quien lee ve el fichero
  viejo o el nuevo, nunca medio.
  - *`fsync`:* obliga al sistema a escribir en el disco lo que tiene en
    memoria.
- El nuevo fichero conserva **modo, propietario, grupo y atributos
  extendidos** (en Linux, las ACL son atributos extendidos).
  - *ACL:* permisos más finos que el `rwx` de siempre.
- Si el fichero tiene **enlaces duros**, o algo de eso no se puede copiar,
  se escribe **en el sitio**: se pierde la atomicidad, pero no se rompe el
  enlace. Si falla a medias, se vuelven a poner los bytes viejos.
  - *Enlace duro:* dos nombres para el mismo fichero; renombrar encima de
    uno lo separa del otro.
- **Lo mostrado es lo escrito:** justo antes de reemplazar, se vuelve a leer
  el fichero. Si alguien lo cambió desde la pregunta → `changed after the
  question; ask again`. POSIX no tiene "comparar y cambiar" para ficheros,
  así que queda un hueco de microsegundos (aceptado).
- `edit_file`: `old_string` tiene que aparecer **una vez**, contando las
  apariciones solapadas (`"aa"` en `"aaa"` está dos veces). Un salto de
  línea de `old_string` vale por cualquier salto del fichero (`\n`, `\r\n`
  o `\r`), porque `read_file` enseña las líneas sin su salto.

### 5. Ejecutar comandos

```
  ┌ run: sleep 10
  │ in /home/ane/proyecto
  │ time limit: 2 s
  │ with your permissions: it can change any file you can
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ timed out
```

- **Grupo de procesos propio.** Ctrl+C en la terminal no llega al comando:
  `maha` decide y mata el grupo entero (`killpg`), nietos incluidos, al pasar
  el tiempo, al cancelar y al terminar. En la verificación, tras Ctrl+C,
  `pgrep sleep` no encontró nada.
  - *Grupo de procesos:* el conjunto de un proceso y sus hijos al que se
    puede mandar una señal de una vez.
- **Salida acotada:** se lee mientras corre (si no, una tubería llena
  bloquearía al hijo), hasta 30 000 caracteres; el resto se lee y se tira.
- **Sin credenciales en el entorno.** El comando recibe solo una **lista de
  variables permitidas** (`PATH`, `HOME`, `LANG`, `LC_*`, `XDG_*`…), no el
  entorno menos las claves conocidas. Una clave con otro nombre
  (`MI_CLAVE`) tampoco llega, ni `SSH_AUTH_SOCK`. En la verificación, `env`
  vio esto: `HOME LANG LOGNAME PATH PWD SHELL TERM USER XDG_DATA_DIRS
  XDG_RUNTIME_DIR`.
- **Un hijo en segundo plano** (`servidor &`) no hace esperar al tiempo
  límite: el comando termina cuando termina su shell, y el hijo se va con
  el grupo.
- **Lo que NO protege:** el comando corre con tus permisos y puede hacer
  `cd ..` o borrar lo que tú puedas borrar. Un proceso que sale de su grupo
  (`setsid`) sobrevive. Hasta el sandbox (hito 14), **la única defensa es que
  leas el comando antes de aprobarlo**.

### 6. La regex del modelo, aparte

`grep` no pregunta dentro del directorio, y ejecuta la regex que escribe el
modelo. Una regex como `(a+)+$` puede tardar un tiempo exponencial (*ReDoS*,
*regular expression denial of service*) y, en el mismo proceso, congelaría
`maha` sin que Ctrl+C respondiera. Por eso `maha` recorre los ficheros (el
perímetro, los secretos y `.gitignore` siguen siendo suyos) y la búsqueda va
a un **proceso hijo** con 30 s de límite, que se mata también con Ctrl+C.

### 7. Lo ejecutado consta

Si `maha` editó un fichero y luego falla la red, o pulsas Ctrl+C, el turno
se guarda **hasta el último resultado completo**. La llamada que corría
recibe `cancelled by the user` (o `interrupted by an internal error`), y
las siguientes, `not run`. Si no, el modelo no sabría que el fichero ya está
editado y lo editaría otra vez:

```
> ¿Qué pasó con el último comando?
El comando `sleep 30` no llegó a completarse: la canceló el usuario mientras
estaba en ejecución.
```

### 8. La regla en el dominio, el disco en el adaptador

Qué pregunta una ruta (fuera, secreto, ejecuta código) es una regla pura:
vive en `domain/paths.py`. Qué variables recibe un comando, en
`domain/environment.py`. Qué ignora git, en `domain/gitignore.py`. Los
adaptadores solo resuelven rutas, leen el disco y lanzan procesos. Así
`run_command`, MCP (hito 16) o el sandbox (hito 14) reutilizan las reglas
sin copiarlas.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Aprobaciones | Una vez / sesión por ámbito / no, en código | Reglas allow/ask/deny por patrón (Claude Code); modos de aprobación (Codex); *human-in-the-loop* de LangGraph (`interrupt`) | Muchos comandos repetidos; flujos sin persona |
| Editar ficheros | `old_string` → `new_string` exacto | Diffs o parches (aider, `apply_patch` de Codex); reescribir el fichero entero | Cambios grandes o en muchos ficheros |
| Escritura atómica | Temporal + `os.replace`; en el sitio si hay enlaces | `atomicwrites` (archivada); editores como Vim (`backupcopy`) | — |
| Ejecutar comandos | Subproceso local con grupo propio, tiempo límite y salida acotada | Contenedor o sandbox (seatbelt, landlock, bubblewrap, Docker, E2B) | Código no confiable: hito 14 |
| Credenciales | Lista de variables permitidas | Herencia con filtros por patrón; gestores de secretos | Equipos y producción |
| Sin terminal | Denegar todo | Política automática configurable | Evals y CI (hito 8) |
| `.gitignore` | Traductor propio | `pathspec`, el crate `ignore` de ripgrep | Siempre que no haya que hacerlo a mano |

Los productos de la industria hacen lo mismo por dentro: el modelo propone
una llamada, el arnés la enseña, pregunta y solo entonces ejecuta. La
diferencia está en cuánta autonomía dan (reglas, modos) y en cómo aíslan lo
que ejecutan.
