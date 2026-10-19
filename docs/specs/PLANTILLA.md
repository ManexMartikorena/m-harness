Estado: PROPUESTA (AAAA-MM-DD)

<!--
Plantilla de spec. Se copia como docs/specs/hito-N-<slug>.md o
docs/specs/mejora-AAAA-MM-DD-<slug>.md y se borra este comentario.

La primera línea cuenta la historia del estado, sin borrar la anterior:
  PROPUESTA (fecha) → APROBADA (fecha, por el humano, con o sin cambios)
  → IMPLEMENTADA y VERIFICADA (fecha, tag, commit de cierre)
No se escribe código hasta APROBADA. La spec se propone en su propio PR
(rama docs/spec-hito-N-<slug>); integrarlo es la aprobación (DESIGN §15).

Escribir corto y directo (AGENTS.md, "Explicar al mantenedor").
-->

# Spec — <Hito N | Mejora>: <título>

Referencias: `docs/DESIGN.md` §…, `docs/ANALISIS.md` §… si aplica, specs
relacionadas, `AGENTS.md` (reglas no negociables).

## 0. Alcance

**El problema.** Qué pasa hoy y por qué hace falta esto, en dos o tres frases.

**Lo que hace este cambio.** En dos o tres frases, visto desde fuera.

Dentro de alcance:
- …

**Fuera de alcance** (y por qué):
- …

## 1. Decisiones de fondo

Una subsección por decisión: qué se decide, por qué, y qué alternativas se
descartaron y por qué. Si cambia el alcance, DESIGN se corrige en el mismo
commit que esta spec, anotado en el sitio con fecha y referencia a esta spec.

## 2. En la industria

Cómo se resuelve esto normalmente: librerías, frameworks o patrones, qué hace
cada uno en una línea, y cuándo se elegiría en lugar de lo que hace M-Harness.
Es la base de la sección "En la industria" de la nota de `docs/guia/`.

## 3. … (diseño de detalle)

Contratos, interfaces, ficheros y capa en la que vive cada uno, configuración
nueva, prompts y skills que se crean o cambian.

## N. Plan de tests

Numerado. Qué se prueba con fakes, qué contra respuestas HTTP simuladas o
recursos temporales, y qué decisión queda fijada con un test.

## N+1. Evals

Si el cambio toca el comportamiento del agente:
- métricas que se miran y umbral de aceptación;
- línea base contra la que se compara;
- muestra o batería completa.

El resultado se anota aquí al implementar: experimento, números y comparación.

## N+2. Orden de piezas para el implementador

Cada punto es un commit pequeño, con tests y lint en verde antes de
commitear. Se indica qué puntos van en cada PR de implementación.

**PR 1**
1. **…** *Commit:* "…"
2. **…** *Commit:* "…"

## N+3. Verificación a mano

Qué se comprueba en el puesto, paso a paso. Las herramientas con efecto, en un
directorio desechable.

## N+4. Lo que no viaja por git y lo que necesita la release

Variables de entorno, pasos manuales y ficheros que cambian en `docs/MAPA.md`.
Lo mismo va a `docs/PUESTA_EN_MARCHA.md` y, si afecta a la release, a "Para la
release" de `docs/ESTADO.md`.

## N+5. Guía

Nota de `docs/guia/` que acompaña al cierre del hito: título y los tres o
cuatro puntos que tiene que explicar.

## N+6. Riesgos

## N+7. Decisiones

Del humano (fecha):
1. …

Propuestas del agente, aprobadas por el humano (fecha):
2. …

## N+8. Aprendido al implementar (fecha)

Se añade al implementar. Nunca reescribe lo anterior: si algo de arriba
resultó ser distinto, se dice aquí y se corrige arriba con una nota
"*(Corregido al implementarlo: …)*".
