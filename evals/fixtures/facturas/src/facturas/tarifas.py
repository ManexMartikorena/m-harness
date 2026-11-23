"""Tarifas de envío por zona: una función por zona."""


def tarifa_zona_001(peso_kg: float) -> float:
    """Precio del envío a la zona 1 para un paquete de `peso_kg`."""
    base = 8.11
    por_kg = 0.39
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_002(peso_kg: float) -> float:
    """Precio del envío a la zona 2 para un paquete de `peso_kg`."""
    base = 6.04
    por_kg = 1.06
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_003(peso_kg: float) -> float:
    """Precio del envío a la zona 3 para un paquete de `peso_kg`."""
    base = 8.7
    por_kg = 0.66
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_004(peso_kg: float) -> float:
    """Precio del envío a la zona 4 para un paquete de `peso_kg`."""
    base = 3.38
    por_kg = 0.95
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_005(peso_kg: float) -> float:
    """Precio del envío a la zona 5 para un paquete de `peso_kg`."""
    base = 6.02
    por_kg = 0.8
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_006(peso_kg: float) -> float:
    """Precio del envío a la zona 6 para un paquete de `peso_kg`."""
    base = 6.75
    por_kg = 0.32
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_007(peso_kg: float) -> float:
    """Precio del envío a la zona 7 para un paquete de `peso_kg`."""
    base = 2.83
    por_kg = 0.43
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_008(peso_kg: float) -> float:
    """Precio del envío a la zona 8 para un paquete de `peso_kg`."""
    base = 7.05
    por_kg = 1.13
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_009(peso_kg: float) -> float:
    """Precio del envío a la zona 9 para un paquete de `peso_kg`."""
    base = 4.8
    por_kg = 1.32
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_010(peso_kg: float) -> float:
    """Precio del envío a la zona 10 para un paquete de `peso_kg`."""
    base = 6.07
    por_kg = 0.4
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_011(peso_kg: float) -> float:
    """Precio del envío a la zona 11 para un paquete de `peso_kg`."""
    base = 7.59
    por_kg = 0.72
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_012(peso_kg: float) -> float:
    """Precio del envío a la zona 12 para un paquete de `peso_kg`."""
    base = 8.72
    por_kg = 0.99
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_013(peso_kg: float) -> float:
    """Precio del envío a la zona 13 para un paquete de `peso_kg`."""
    base = 6.79
    por_kg = 1.37
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_014(peso_kg: float) -> float:
    """Precio del envío a la zona 14 para un paquete de `peso_kg`."""
    base = 4.54
    por_kg = 0.87
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_015(peso_kg: float) -> float:
    """Precio del envío a la zona 15 para un paquete de `peso_kg`."""
    base = 4.24
    por_kg = 0.58
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_016(peso_kg: float) -> float:
    """Precio del envío a la zona 16 para un paquete de `peso_kg`."""
    base = 6.94
    por_kg = 1.3
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_017(peso_kg: float) -> float:
    """Precio del envío a la zona 17 para un paquete de `peso_kg`."""
    base = 6.67
    por_kg = 1.16
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_018(peso_kg: float) -> float:
    """Precio del envío a la zona 18 para un paquete de `peso_kg`."""
    base = 8.26
    por_kg = 0.97
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_019(peso_kg: float) -> float:
    """Precio del envío a la zona 19 para un paquete de `peso_kg`."""
    base = 4.51
    por_kg = 0.99
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_020(peso_kg: float) -> float:
    """Precio del envío a la zona 20 para un paquete de `peso_kg`."""
    base = 6.82
    por_kg = 0.68
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_021(peso_kg: float) -> float:
    """Precio del envío a la zona 21 para un paquete de `peso_kg`."""
    base = 5.34
    por_kg = 0.95
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_022(peso_kg: float) -> float:
    """Precio del envío a la zona 22 para un paquete de `peso_kg`."""
    base = 4.75
    por_kg = 1.34
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_023(peso_kg: float) -> float:
    """Precio del envío a la zona 23 para un paquete de `peso_kg`."""
    base = 6.7
    por_kg = 1.3
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_024(peso_kg: float) -> float:
    """Precio del envío a la zona 24 para un paquete de `peso_kg`."""
    base = 7.33
    por_kg = 0.96
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_025(peso_kg: float) -> float:
    """Precio del envío a la zona 25 para un paquete de `peso_kg`."""
    base = 3.97
    por_kg = 1.26
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_026(peso_kg: float) -> float:
    """Precio del envío a la zona 26 para un paquete de `peso_kg`."""
    base = 5.64
    por_kg = 1.26
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_027(peso_kg: float) -> float:
    """Precio del envío a la zona 27 para un paquete de `peso_kg`."""
    base = 5.56
    por_kg = 1.05
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_028(peso_kg: float) -> float:
    """Precio del envío a la zona 28 para un paquete de `peso_kg`."""
    base = 7.32
    por_kg = 0.8
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_029(peso_kg: float) -> float:
    """Precio del envío a la zona 29 para un paquete de `peso_kg`."""
    base = 8.82
    por_kg = 1.38
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_030(peso_kg: float) -> float:
    """Precio del envío a la zona 30 para un paquete de `peso_kg`."""
    base = 3.51
    por_kg = 1.23
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_031(peso_kg: float) -> float:
    """Precio del envío a la zona 31 para un paquete de `peso_kg`."""
    base = 6.26
    por_kg = 1.39
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_032(peso_kg: float) -> float:
    """Precio del envío a la zona 32 para un paquete de `peso_kg`."""
    base = 3.92
    por_kg = 0.63
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_033(peso_kg: float) -> float:
    """Precio del envío a la zona 33 para un paquete de `peso_kg`."""
    base = 4.03
    por_kg = 1.18
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_034(peso_kg: float) -> float:
    """Precio del envío a la zona 34 para un paquete de `peso_kg`."""
    base = 5.98
    por_kg = 1.32
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_035(peso_kg: float) -> float:
    """Precio del envío a la zona 35 para un paquete de `peso_kg`."""
    base = 3.2
    por_kg = 1.0
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_036(peso_kg: float) -> float:
    """Precio del envío a la zona 36 para un paquete de `peso_kg`."""
    base = 6.57
    por_kg = 0.5
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_037(peso_kg: float) -> float:
    """Precio del envío a la zona 37 para un paquete de `peso_kg`."""
    base = 6.75
    por_kg = 1.1
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_038(peso_kg: float) -> float:
    """Precio del envío a la zona 38 para un paquete de `peso_kg`."""
    base = 6.86
    por_kg = 0.89
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_039(peso_kg: float) -> float:
    """Precio del envío a la zona 39 para un paquete de `peso_kg`."""
    base = 5.38
    por_kg = 1.09
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_040(peso_kg: float) -> float:
    """Precio del envío a la zona 40 para un paquete de `peso_kg`."""
    base = 4.09
    por_kg = 0.71
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_041(peso_kg: float) -> float:
    """Precio del envío a la zona 41 para un paquete de `peso_kg`."""
    base = 9.0
    por_kg = 1.23
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_042(peso_kg: float) -> float:
    """Precio del envío a la zona 42 para un paquete de `peso_kg`."""
    base = 4.6
    por_kg = 1.15
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_043(peso_kg: float) -> float:
    """Precio del envío a la zona 43 para un paquete de `peso_kg`."""
    base = 5.35
    por_kg = 0.31
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_044(peso_kg: float) -> float:
    """Precio del envío a la zona 44 para un paquete de `peso_kg`."""
    base = 2.72
    por_kg = 0.81
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_045(peso_kg: float) -> float:
    """Precio del envío a la zona 45 para un paquete de `peso_kg`."""
    base = 6.74
    por_kg = 1.0
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_046(peso_kg: float) -> float:
    """Precio del envío a la zona 46 para un paquete de `peso_kg`."""
    base = 3.89
    por_kg = 0.85
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_047(peso_kg: float) -> float:
    """Precio del envío a la zona 47 para un paquete de `peso_kg`."""
    base = 4.04
    por_kg = 0.67
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_048(peso_kg: float) -> float:
    """Precio del envío a la zona 48 para un paquete de `peso_kg`."""
    base = 2.59
    por_kg = 0.36
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_049(peso_kg: float) -> float:
    """Precio del envío a la zona 49 para un paquete de `peso_kg`."""
    base = 2.9
    por_kg = 1.27
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_050(peso_kg: float) -> float:
    """Precio del envío a la zona 50 para un paquete de `peso_kg`."""
    base = 5.65
    por_kg = 0.45
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_051(peso_kg: float) -> float:
    """Precio del envío a la zona 51 para un paquete de `peso_kg`."""
    base = 2.57
    por_kg = 1.1
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_052(peso_kg: float) -> float:
    """Precio del envío a la zona 52 para un paquete de `peso_kg`."""
    base = 7.8
    por_kg = 0.37
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_053(peso_kg: float) -> float:
    """Precio del envío a la zona 53 para un paquete de `peso_kg`."""
    base = 2.89
    por_kg = 0.95
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_054(peso_kg: float) -> float:
    """Precio del envío a la zona 54 para un paquete de `peso_kg`."""
    base = 2.58
    por_kg = 0.49
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_055(peso_kg: float) -> float:
    """Precio del envío a la zona 55 para un paquete de `peso_kg`."""
    base = 4.28
    por_kg = 1.21
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_056(peso_kg: float) -> float:
    """Precio del envío a la zona 56 para un paquete de `peso_kg`."""
    base = 7.09
    por_kg = 0.77
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_057(peso_kg: float) -> float:
    """Precio del envío a la zona 57 para un paquete de `peso_kg`."""
    base = 4.86
    por_kg = 0.38
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_058(peso_kg: float) -> float:
    """Precio del envío a la zona 58 para un paquete de `peso_kg`."""
    base = 2.78
    por_kg = 1.23
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_059(peso_kg: float) -> float:
    """Precio del envío a la zona 59 para un paquete de `peso_kg`."""
    base = 4.47
    por_kg = 0.62
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_060(peso_kg: float) -> float:
    """Precio del envío a la zona 60 para un paquete de `peso_kg`."""
    base = 7.61
    por_kg = 0.32
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_061(peso_kg: float) -> float:
    """Precio del envío a la zona 61 para un paquete de `peso_kg`."""
    base = 3.79
    por_kg = 0.54
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_062(peso_kg: float) -> float:
    """Precio del envío a la zona 62 para un paquete de `peso_kg`."""
    base = 3.65
    por_kg = 1.24
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_063(peso_kg: float) -> float:
    """Precio del envío a la zona 63 para un paquete de `peso_kg`."""
    base = 4.19
    por_kg = 1.38
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_064(peso_kg: float) -> float:
    """Precio del envío a la zona 64 para un paquete de `peso_kg`."""
    base = 2.84
    por_kg = 1.12
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_065(peso_kg: float) -> float:
    """Precio del envío a la zona 65 para un paquete de `peso_kg`."""
    base = 6.37
    por_kg = 1.4
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_066(peso_kg: float) -> float:
    """Precio del envío a la zona 66 para un paquete de `peso_kg`."""
    base = 4.78
    por_kg = 0.55
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_067(peso_kg: float) -> float:
    """Precio del envío a la zona 67 para un paquete de `peso_kg`."""
    base = 4.58
    por_kg = 1.11
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_068(peso_kg: float) -> float:
    """Precio del envío a la zona 68 para un paquete de `peso_kg`."""
    base = 7.95
    por_kg = 0.61
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_069(peso_kg: float) -> float:
    """Precio del envío a la zona 69 para un paquete de `peso_kg`."""
    base = 5.91
    por_kg = 0.59
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_070(peso_kg: float) -> float:
    """Precio del envío a la zona 70 para un paquete de `peso_kg`."""
    base = 2.51
    por_kg = 1.09
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_071(peso_kg: float) -> float:
    """Precio del envío a la zona 71 para un paquete de `peso_kg`."""
    base = 3.68
    por_kg = 1.31
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_072(peso_kg: float) -> float:
    """Precio del envío a la zona 72 para un paquete de `peso_kg`."""
    base = 8.36
    por_kg = 0.62
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_073(peso_kg: float) -> float:
    """Precio del envío a la zona 73 para un paquete de `peso_kg`."""
    base = 5.72
    por_kg = 0.59
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_074(peso_kg: float) -> float:
    """Precio del envío a la zona 74 para un paquete de `peso_kg`."""
    base = 6.74
    por_kg = 1.3
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_075(peso_kg: float) -> float:
    """Precio del envío a la zona 75 para un paquete de `peso_kg`."""
    base = 3.06
    por_kg = 0.71
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_076(peso_kg: float) -> float:
    """Precio del envío a la zona 76 para un paquete de `peso_kg`."""
    base = 6.71
    por_kg = 0.67
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_077(peso_kg: float) -> float:
    """Precio del envío a la zona 77 para un paquete de `peso_kg`."""
    base = 8.39
    por_kg = 0.5
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_078(peso_kg: float) -> float:
    """Precio del envío a la zona 78 para un paquete de `peso_kg`."""
    base = 5.45
    por_kg = 0.82
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_079(peso_kg: float) -> float:
    """Precio del envío a la zona 79 para un paquete de `peso_kg`."""
    base = 3.68
    por_kg = 0.85
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_080(peso_kg: float) -> float:
    """Precio del envío a la zona 80 para un paquete de `peso_kg`."""
    base = 3.03
    por_kg = 0.78
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_081(peso_kg: float) -> float:
    """Precio del envío a la zona 81 para un paquete de `peso_kg`."""
    base = 6.7
    por_kg = 0.93
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_082(peso_kg: float) -> float:
    """Precio del envío a la zona 82 para un paquete de `peso_kg`."""
    base = 2.77
    por_kg = 1.14
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_083(peso_kg: float) -> float:
    """Precio del envío a la zona 83 para un paquete de `peso_kg`."""
    base = 5.82
    por_kg = 0.79
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_084(peso_kg: float) -> float:
    """Precio del envío a la zona 84 para un paquete de `peso_kg`."""
    base = 3.9
    por_kg = 0.49
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_085(peso_kg: float) -> float:
    """Precio del envío a la zona 85 para un paquete de `peso_kg`."""
    base = 4.24
    por_kg = 0.74
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_086(peso_kg: float) -> float:
    """Precio del envío a la zona 86 para un paquete de `peso_kg`."""
    base = 8.85
    por_kg = 0.9
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_087(peso_kg: float) -> float:
    """Precio del envío a la zona 87 para un paquete de `peso_kg`."""
    base = 6.63
    por_kg = 1.12
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_088(peso_kg: float) -> float:
    """Precio del envío a la zona 88 para un paquete de `peso_kg`."""
    base = 7.75
    por_kg = 0.41
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_089(peso_kg: float) -> float:
    """Precio del envío a la zona 89 para un paquete de `peso_kg`."""
    base = 5.82
    por_kg = 0.55
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_090(peso_kg: float) -> float:
    """Precio del envío a la zona 90 para un paquete de `peso_kg`."""
    base = 7.36
    por_kg = 0.35
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_091(peso_kg: float) -> float:
    """Precio del envío a la zona 91 para un paquete de `peso_kg`."""
    base = 7.03
    por_kg = 1.36
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_092(peso_kg: float) -> float:
    """Precio del envío a la zona 92 para un paquete de `peso_kg`."""
    base = 4.77
    por_kg = 1.05
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_093(peso_kg: float) -> float:
    """Precio del envío a la zona 93 para un paquete de `peso_kg`."""
    base = 4.89
    por_kg = 1.34
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_094(peso_kg: float) -> float:
    """Precio del envío a la zona 94 para un paquete de `peso_kg`."""
    base = 7.06
    por_kg = 0.52
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_095(peso_kg: float) -> float:
    """Precio del envío a la zona 95 para un paquete de `peso_kg`."""
    base = 7.74
    por_kg = 1.13
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_096(peso_kg: float) -> float:
    """Precio del envío a la zona 96 para un paquete de `peso_kg`."""
    base = 5.97
    por_kg = 0.51
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_097(peso_kg: float) -> float:
    """Precio del envío a la zona 97 para un paquete de `peso_kg`."""
    base = 4.3
    por_kg = 0.34
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_098(peso_kg: float) -> float:
    """Precio del envío a la zona 98 para un paquete de `peso_kg`."""
    base = 7.16
    por_kg = 0.36
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_099(peso_kg: float) -> float:
    """Precio del envío a la zona 99 para un paquete de `peso_kg`."""
    base = 8.95
    por_kg = 1.0
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_100(peso_kg: float) -> float:
    """Precio del envío a la zona 100 para un paquete de `peso_kg`."""
    base = 7.24
    por_kg = 1.18
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_101(peso_kg: float) -> float:
    """Precio del envío a la zona 101 para un paquete de `peso_kg`."""
    base = 5.69
    por_kg = 0.36
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_102(peso_kg: float) -> float:
    """Precio del envío a la zona 102 para un paquete de `peso_kg`."""
    base = 3.58
    por_kg = 0.68
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_103(peso_kg: float) -> float:
    """Precio del envío a la zona 103 para un paquete de `peso_kg`."""
    base = 4.87
    por_kg = 0.7
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_104(peso_kg: float) -> float:
    """Precio del envío a la zona 104 para un paquete de `peso_kg`."""
    base = 4.74
    por_kg = 0.44
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_105(peso_kg: float) -> float:
    """Precio del envío a la zona 105 para un paquete de `peso_kg`."""
    base = 4.45
    por_kg = 1.19
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_106(peso_kg: float) -> float:
    """Precio del envío a la zona 106 para un paquete de `peso_kg`."""
    base = 8.66
    por_kg = 0.51
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_107(peso_kg: float) -> float:
    """Precio del envío a la zona 107 para un paquete de `peso_kg`."""
    base = 4.56
    por_kg = 0.43
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_108(peso_kg: float) -> float:
    """Precio del envío a la zona 108 para un paquete de `peso_kg`."""
    base = 5.06
    por_kg = 0.7
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_109(peso_kg: float) -> float:
    """Precio del envío a la zona 109 para un paquete de `peso_kg`."""
    base = 6.19
    por_kg = 0.31
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_110(peso_kg: float) -> float:
    """Precio del envío a la zona 110 para un paquete de `peso_kg`."""
    base = 4.03
    por_kg = 0.77
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_111(peso_kg: float) -> float:
    """Precio del envío a la zona 111 para un paquete de `peso_kg`."""
    base = 4.43
    por_kg = 1.34
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_112(peso_kg: float) -> float:
    """Precio del envío a la zona 112 para un paquete de `peso_kg`."""
    base = 4.84
    por_kg = 0.85
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_113(peso_kg: float) -> float:
    """Precio del envío a la zona 113 para un paquete de `peso_kg`."""
    base = 4.75
    por_kg = 1.11
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_114(peso_kg: float) -> float:
    """Precio del envío a la zona 114 para un paquete de `peso_kg`."""
    base = 5.06
    por_kg = 0.62
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_115(peso_kg: float) -> float:
    """Precio del envío a la zona 115 para un paquete de `peso_kg`."""
    base = 8.04
    por_kg = 0.73
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_116(peso_kg: float) -> float:
    """Precio del envío a la zona 116 para un paquete de `peso_kg`."""
    base = 5.77
    por_kg = 0.8
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_117(peso_kg: float) -> float:
    """Precio del envío a la zona 117 para un paquete de `peso_kg`."""
    base = 7.22
    por_kg = 0.68
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_118(peso_kg: float) -> float:
    """Precio del envío a la zona 118 para un paquete de `peso_kg`."""
    base = 4.64
    por_kg = 1.14
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_119(peso_kg: float) -> float:
    """Precio del envío a la zona 119 para un paquete de `peso_kg`."""
    base = 3.66
    por_kg = 1.24
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_120(peso_kg: float) -> float:
    """Precio del envío a la zona 120 para un paquete de `peso_kg`."""
    base = 4.16
    por_kg = 1.27
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_121(peso_kg: float) -> float:
    """Precio del envío a la zona 121 para un paquete de `peso_kg`."""
    base = 8.5
    por_kg = 1.02
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_122(peso_kg: float) -> float:
    """Precio del envío a la zona 122 para un paquete de `peso_kg`."""
    base = 3.24
    por_kg = 1.13
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_123(peso_kg: float) -> float:
    """Precio del envío a la zona 123 para un paquete de `peso_kg`."""
    base = 5.12
    por_kg = 0.39
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_124(peso_kg: float) -> float:
    """Precio del envío a la zona 124 para un paquete de `peso_kg`."""
    base = 3.55
    por_kg = 1.27
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_125(peso_kg: float) -> float:
    """Precio del envío a la zona 125 para un paquete de `peso_kg`."""
    base = 4.77
    por_kg = 0.56
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_126(peso_kg: float) -> float:
    """Precio del envío a la zona 126 para un paquete de `peso_kg`."""
    base = 3.81
    por_kg = 0.35
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_127(peso_kg: float) -> float:
    """Precio del envío a la zona 127 para un paquete de `peso_kg`."""
    base = 5.31
    por_kg = 1.35
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_128(peso_kg: float) -> float:
    """Precio del envío a la zona 128 para un paquete de `peso_kg`."""
    base = 6.25
    por_kg = 1.28
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_129(peso_kg: float) -> float:
    """Precio del envío a la zona 129 para un paquete de `peso_kg`."""
    base = 5.76
    por_kg = 1.24
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_130(peso_kg: float) -> float:
    """Precio del envío a la zona 130 para un paquete de `peso_kg`."""
    base = 3.19
    por_kg = 0.66
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_131(peso_kg: float) -> float:
    """Precio del envío a la zona 131 para un paquete de `peso_kg`."""
    base = 8.98
    por_kg = 0.43
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_132(peso_kg: float) -> float:
    """Precio del envío a la zona 132 para un paquete de `peso_kg`."""
    base = 5.96
    por_kg = 1.33
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_133(peso_kg: float) -> float:
    """Precio del envío a la zona 133 para un paquete de `peso_kg`."""
    base = 6.81
    por_kg = 0.76
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_134(peso_kg: float) -> float:
    """Precio del envío a la zona 134 para un paquete de `peso_kg`."""
    base = 3.76
    por_kg = 1.13
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_135(peso_kg: float) -> float:
    """Precio del envío a la zona 135 para un paquete de `peso_kg`."""
    base = 6.25
    por_kg = 0.66
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_136(peso_kg: float) -> float:
    """Precio del envío a la zona 136 para un paquete de `peso_kg`."""
    base = 3.76
    por_kg = 1.09
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_137(peso_kg: float) -> float:
    """Precio del envío a la zona 137 para un paquete de `peso_kg`."""
    base = 8.0
    por_kg = 0.74
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_138(peso_kg: float) -> float:
    """Precio del envío a la zona 138 para un paquete de `peso_kg`."""
    base = 3.85
    por_kg = 0.97
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_139(peso_kg: float) -> float:
    """Precio del envío a la zona 139 para un paquete de `peso_kg`."""
    base = 4.29
    por_kg = 0.95
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_140(peso_kg: float) -> float:
    """Precio del envío a la zona 140 para un paquete de `peso_kg`."""
    base = 2.66
    por_kg = 0.86
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_141(peso_kg: float) -> float:
    """Precio del envío a la zona 141 para un paquete de `peso_kg`."""
    base = 4.89
    por_kg = 0.7
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_142(peso_kg: float) -> float:
    """Precio del envío a la zona 142 para un paquete de `peso_kg`."""
    base = 4.67
    por_kg = 1.28
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_143(peso_kg: float) -> float:
    """Precio del envío a la zona 143 para un paquete de `peso_kg`."""
    base = 6.96
    por_kg = 1.2
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_144(peso_kg: float) -> float:
    """Precio del envío a la zona 144 para un paquete de `peso_kg`."""
    base = 4.64
    por_kg = 0.57
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_145(peso_kg: float) -> float:
    """Precio del envío a la zona 145 para un paquete de `peso_kg`."""
    base = 6.6
    por_kg = 0.86
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_146(peso_kg: float) -> float:
    """Precio del envío a la zona 146 para un paquete de `peso_kg`."""
    base = 6.36
    por_kg = 0.98
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_147(peso_kg: float) -> float:
    """Precio del envío a la zona 147 para un paquete de `peso_kg`."""
    base = 7.75
    por_kg = 1.08
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_148(peso_kg: float) -> float:
    """Precio del envío a la zona 148 para un paquete de `peso_kg`."""
    base = 3.11
    por_kg = 0.55
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_149(peso_kg: float) -> float:
    """Precio del envío a la zona 149 para un paquete de `peso_kg`."""
    base = 5.0
    por_kg = 0.88
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_150(peso_kg: float) -> float:
    """Precio del envío a la zona 150 para un paquete de `peso_kg`."""
    base = 6.15
    por_kg = 0.7
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_151(peso_kg: float) -> float:
    """Precio del envío a la zona 151 para un paquete de `peso_kg`."""
    base = 7.69
    por_kg = 0.67
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_152(peso_kg: float) -> float:
    """Precio del envío a la zona 152 para un paquete de `peso_kg`."""
    base = 7.93
    por_kg = 1.01
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_153(peso_kg: float) -> float:
    """Precio del envío a la zona 153 para un paquete de `peso_kg`."""
    base = 4.72
    por_kg = 0.62
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_154(peso_kg: float) -> float:
    """Precio del envío a la zona 154 para un paquete de `peso_kg`."""
    base = 7.65
    por_kg = 1.24
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_155(peso_kg: float) -> float:
    """Precio del envío a la zona 155 para un paquete de `peso_kg`."""
    base = 4.87
    por_kg = 1.35
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_156(peso_kg: float) -> float:
    """Precio del envío a la zona 156 para un paquete de `peso_kg`."""
    base = 4.84
    por_kg = 1.21
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_157(peso_kg: float) -> float:
    """Precio del envío a la zona 157 para un paquete de `peso_kg`."""
    base = 4.64
    por_kg = 0.61
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_158(peso_kg: float) -> float:
    """Precio del envío a la zona 158 para un paquete de `peso_kg`."""
    base = 5.03
    por_kg = 1.1
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_159(peso_kg: float) -> float:
    """Precio del envío a la zona 159 para un paquete de `peso_kg`."""
    base = 4.6
    por_kg = 0.9
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)


def tarifa_zona_160(peso_kg: float) -> float:
    """Precio del envío a la zona 160 para un paquete de `peso_kg`."""
    base = 5.61
    por_kg = 1.28
    if peso_kg <= 0:
        raise ValueError("peso no válido")
    return round(base + por_kg * peso_kg, 2)

