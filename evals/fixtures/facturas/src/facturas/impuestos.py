"""Impuestos de una factura: IVA por tipo, recargos y retenciones."""

TIPOS_IVA = {"general": 21, "reducido": 10, "superreducido": 4}


def retencion_actividad_001(base: float) -> float:
    """Retención de la actividad 1 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_002(base: float) -> float:
    """Retención de la actividad 2 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_003(base: float) -> float:
    """Retención de la actividad 3 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_004(base: float) -> float:
    """Retención de la actividad 4 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_005(base: float) -> float:
    """Retención de la actividad 5 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_006(base: float) -> float:
    """Retención de la actividad 6 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_007(base: float) -> float:
    """Retención de la actividad 7 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_008(base: float) -> float:
    """Retención de la actividad 8 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_009(base: float) -> float:
    """Retención de la actividad 9 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_010(base: float) -> float:
    """Retención de la actividad 10 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_011(base: float) -> float:
    """Retención de la actividad 11 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_012(base: float) -> float:
    """Retención de la actividad 12 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_013(base: float) -> float:
    """Retención de la actividad 13 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_014(base: float) -> float:
    """Retención de la actividad 14 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_015(base: float) -> float:
    """Retención de la actividad 15 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_016(base: float) -> float:
    """Retención de la actividad 16 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_017(base: float) -> float:
    """Retención de la actividad 17 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_018(base: float) -> float:
    """Retención de la actividad 18 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_019(base: float) -> float:
    """Retención de la actividad 19 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_020(base: float) -> float:
    """Retención de la actividad 20 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_021(base: float) -> float:
    """Retención de la actividad 21 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_022(base: float) -> float:
    """Retención de la actividad 22 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_023(base: float) -> float:
    """Retención de la actividad 23 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_024(base: float) -> float:
    """Retención de la actividad 24 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_025(base: float) -> float:
    """Retención de la actividad 25 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_026(base: float) -> float:
    """Retención de la actividad 26 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_027(base: float) -> float:
    """Retención de la actividad 27 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_028(base: float) -> float:
    """Retención de la actividad 28 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_029(base: float) -> float:
    """Retención de la actividad 29 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_030(base: float) -> float:
    """Retención de la actividad 30 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_031(base: float) -> float:
    """Retención de la actividad 31 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_032(base: float) -> float:
    """Retención de la actividad 32 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_033(base: float) -> float:
    """Retención de la actividad 33 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_034(base: float) -> float:
    """Retención de la actividad 34 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_035(base: float) -> float:
    """Retención de la actividad 35 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_036(base: float) -> float:
    """Retención de la actividad 36 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_037(base: float) -> float:
    """Retención de la actividad 37 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_038(base: float) -> float:
    """Retención de la actividad 38 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_039(base: float) -> float:
    """Retención de la actividad 39 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_040(base: float) -> float:
    """Retención de la actividad 40 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_041(base: float) -> float:
    """Retención de la actividad 41 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_042(base: float) -> float:
    """Retención de la actividad 42 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_043(base: float) -> float:
    """Retención de la actividad 43 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_044(base: float) -> float:
    """Retención de la actividad 44 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_045(base: float) -> float:
    """Retención de la actividad 45 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_046(base: float) -> float:
    """Retención de la actividad 46 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_047(base: float) -> float:
    """Retención de la actividad 47 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_048(base: float) -> float:
    """Retención de la actividad 48 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_049(base: float) -> float:
    """Retención de la actividad 49 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_050(base: float) -> float:
    """Retención de la actividad 50 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_051(base: float) -> float:
    """Retención de la actividad 51 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_052(base: float) -> float:
    """Retención de la actividad 52 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_053(base: float) -> float:
    """Retención de la actividad 53 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_054(base: float) -> float:
    """Retención de la actividad 54 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_055(base: float) -> float:
    """Retención de la actividad 55 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_056(base: float) -> float:
    """Retención de la actividad 56 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_057(base: float) -> float:
    """Retención de la actividad 57 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_058(base: float) -> float:
    """Retención de la actividad 58 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_059(base: float) -> float:
    """Retención de la actividad 59 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_060(base: float) -> float:
    """Retención de la actividad 60 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_061(base: float) -> float:
    """Retención de la actividad 61 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_062(base: float) -> float:
    """Retención de la actividad 62 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_063(base: float) -> float:
    """Retención de la actividad 63 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_064(base: float) -> float:
    """Retención de la actividad 64 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_065(base: float) -> float:
    """Retención de la actividad 65 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_066(base: float) -> float:
    """Retención de la actividad 66 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_067(base: float) -> float:
    """Retención de la actividad 67 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_068(base: float) -> float:
    """Retención de la actividad 68 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_069(base: float) -> float:
    """Retención de la actividad 69 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_070(base: float) -> float:
    """Retención de la actividad 70 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_071(base: float) -> float:
    """Retención de la actividad 71 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_072(base: float) -> float:
    """Retención de la actividad 72 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_073(base: float) -> float:
    """Retención de la actividad 73 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_074(base: float) -> float:
    """Retención de la actividad 74 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_075(base: float) -> float:
    """Retención de la actividad 75 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_076(base: float) -> float:
    """Retención de la actividad 76 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_077(base: float) -> float:
    """Retención de la actividad 77 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_078(base: float) -> float:
    """Retención de la actividad 78 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_079(base: float) -> float:
    """Retención de la actividad 79 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_080(base: float) -> float:
    """Retención de la actividad 80 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_081(base: float) -> float:
    """Retención de la actividad 81 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_082(base: float) -> float:
    """Retención de la actividad 82 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_083(base: float) -> float:
    """Retención de la actividad 83 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_084(base: float) -> float:
    """Retención de la actividad 84 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_085(base: float) -> float:
    """Retención de la actividad 85 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_086(base: float) -> float:
    """Retención de la actividad 86 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_087(base: float) -> float:
    """Retención de la actividad 87 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_088(base: float) -> float:
    """Retención de la actividad 88 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_089(base: float) -> float:
    """Retención de la actividad 89 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_090(base: float) -> float:
    """Retención de la actividad 90 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_091(base: float) -> float:
    """Retención de la actividad 91 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_092(base: float) -> float:
    """Retención de la actividad 92 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_093(base: float) -> float:
    """Retención de la actividad 93 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_094(base: float) -> float:
    """Retención de la actividad 94 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_095(base: float) -> float:
    """Retención de la actividad 95 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_096(base: float) -> float:
    """Retención de la actividad 96 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_097(base: float) -> float:
    """Retención de la actividad 97 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


# Recargo de equivalencia de cada tipo de IVA, en puntos.
RECARGOS = {"general": 5.2, "reducido": 1.4, "superreducido": 0.5}


def recargo_equivalencia(base: float, tipo: str) -> float:
    """El recargo de equivalencia de `base` con el tipo de IVA `tipo`."""
    if tipo not in RECARGOS:
        raise ValueError(f"tipo desconocido: {tipo}")
    puntos = RECARGOS[tipo]
    return round(base * puntos / 10, 2)


def retencion_actividad_098(base: float) -> float:
    """Retención de la actividad 98 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_099(base: float) -> float:
    """Retención de la actividad 99 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_100(base: float) -> float:
    """Retención de la actividad 100 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_101(base: float) -> float:
    """Retención de la actividad 101 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_102(base: float) -> float:
    """Retención de la actividad 102 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_103(base: float) -> float:
    """Retención de la actividad 103 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_104(base: float) -> float:
    """Retención de la actividad 104 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_105(base: float) -> float:
    """Retención de la actividad 105 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_106(base: float) -> float:
    """Retención de la actividad 106 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_107(base: float) -> float:
    """Retención de la actividad 107 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_108(base: float) -> float:
    """Retención de la actividad 108 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_109(base: float) -> float:
    """Retención de la actividad 109 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_110(base: float) -> float:
    """Retención de la actividad 110 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_111(base: float) -> float:
    """Retención de la actividad 111 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_112(base: float) -> float:
    """Retención de la actividad 112 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_113(base: float) -> float:
    """Retención de la actividad 113 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_114(base: float) -> float:
    """Retención de la actividad 114 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_115(base: float) -> float:
    """Retención de la actividad 115 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_116(base: float) -> float:
    """Retención de la actividad 116 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_117(base: float) -> float:
    """Retención de la actividad 117 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_118(base: float) -> float:
    """Retención de la actividad 118 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_119(base: float) -> float:
    """Retención de la actividad 119 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_120(base: float) -> float:
    """Retención de la actividad 120 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_121(base: float) -> float:
    """Retención de la actividad 121 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_122(base: float) -> float:
    """Retención de la actividad 122 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_123(base: float) -> float:
    """Retención de la actividad 123 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_124(base: float) -> float:
    """Retención de la actividad 124 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_125(base: float) -> float:
    """Retención de la actividad 125 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_126(base: float) -> float:
    """Retención de la actividad 126 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_127(base: float) -> float:
    """Retención de la actividad 127 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_128(base: float) -> float:
    """Retención de la actividad 128 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_129(base: float) -> float:
    """Retención de la actividad 129 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_130(base: float) -> float:
    """Retención de la actividad 130 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_131(base: float) -> float:
    """Retención de la actividad 131 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_132(base: float) -> float:
    """Retención de la actividad 132 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_133(base: float) -> float:
    """Retención de la actividad 133 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_134(base: float) -> float:
    """Retención de la actividad 134 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_135(base: float) -> float:
    """Retención de la actividad 135 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_136(base: float) -> float:
    """Retención de la actividad 136 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_137(base: float) -> float:
    """Retención de la actividad 137 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_138(base: float) -> float:
    """Retención de la actividad 138 sobre `base`, al 19 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 19
    return round(base * porcentaje / 100, 2)


def retencion_actividad_139(base: float) -> float:
    """Retención de la actividad 139 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_140(base: float) -> float:
    """Retención de la actividad 140 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_141(base: float) -> float:
    """Retención de la actividad 141 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_142(base: float) -> float:
    """Retención de la actividad 142 sobre `base`, al 1 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 1
    return round(base * porcentaje / 100, 2)


def retencion_actividad_143(base: float) -> float:
    """Retención de la actividad 143 sobre `base`, al 7 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 7
    return round(base * porcentaje / 100, 2)


def retencion_actividad_144(base: float) -> float:
    """Retención de la actividad 144 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_145(base: float) -> float:
    """Retención de la actividad 145 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_146(base: float) -> float:
    """Retención de la actividad 146 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_147(base: float) -> float:
    """Retención de la actividad 147 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_148(base: float) -> float:
    """Retención de la actividad 148 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def retencion_actividad_149(base: float) -> float:
    """Retención de la actividad 149 sobre `base`, al 15 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 15
    return round(base * porcentaje / 100, 2)


def retencion_actividad_150(base: float) -> float:
    """Retención de la actividad 150 sobre `base`, al 2 %."""
    if base < 0:
        raise ValueError("base negativa")
    porcentaje = 2
    return round(base * porcentaje / 100, 2)


def iva(base: float, tipo: str) -> float:
    """El IVA de `base` con el tipo `tipo`."""
    return round(base * TIPOS_IVA[tipo] / 100, 2)

