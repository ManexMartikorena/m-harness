# Préstamos

Cuentas de los préstamos de la biblioteca del barrio.

## Funciones

- `dias_retraso(entregado, limite)`: los días que pasaron del límite, o 0.
- `multa(dias)`: lo que se paga por esos días, a 0,50 € el día.
- `multa_de_prestamo(entregado, limite)`: la multa de un préstamo.

## Tests

    python3 -m unittest -q test_prestamos
