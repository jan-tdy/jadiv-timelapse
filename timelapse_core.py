"""Zdieľaná, testovateľná logika používaná oboma desktopovými GUI variantami
(jadiv-timelapse.py aj jadiv-timelapse_plus.py): prirodzené triedenie súborov
podľa názvu a výpočet cieľového rozlíšenia videa so zachovaním pomeru strán.
"""
import re


def natural_sort_key(path):
    """Rozdelí cestu na text/čísla, aby sa fotky triedili číselne (napr. 2 pred 10), nie čisto abecedne."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', path)]


def compute_target_resolution(width, height, resolution_choice):
    """Vypočíta cieľové rozlíšenie videa podľa výberu v UI (`resolution_choice`),
    so zachovaním pomeru strán, a zaokrúhli výsledok na párne čísla (vyžadujú to video kodeky).

    "Full HD"/"4K" udávajú dlhšiu (vodorovnú) stranu videa. Pri fotke na výšku (portrét)
    sa preto aplikujú na výšku, nie na šírku - inak by vyšlo absurdne vysoké video namiesto
    rozumného zvislého formátu. "720p"/"480p"/"240p" udávajú počet riadkov (výšku) a platí
    to bez ohľadu na orientáciu fotky. Ak výber nezodpovedá žiadnej z týchto značiek
    (napr. "Originál"), vráti sa pôvodné rozlíšenie (zaokrúhlené na párne čísla).
    """
    target_width = width
    target_height = height
    is_portrait = height > width

    if "Full HD" in resolution_choice:
        long_side = 1920
        if is_portrait:
            target_height = long_side
            target_width = int((long_side / height) * width)
        else:
            target_width = long_side
            target_height = int((long_side / width) * height)
    elif "4K" in resolution_choice:
        long_side = 3840
        if is_portrait:
            target_height = long_side
            target_width = int((long_side / height) * width)
        else:
            target_width = long_side
            target_height = int((long_side / width) * height)
    elif "720p" in resolution_choice:
        target_height = 720
        target_width = int((720 / height) * width)
    elif "480p" in resolution_choice:
        target_height = 480
        target_width = int((480 / height) * width)
    elif "240p" in resolution_choice:
        target_height = 240
        target_width = int((240 / height) * width)

    # Kodeky MP4 vyžadujú, aby šírka aj výška boli párne čísla, inak zlyhajú
    target_width -= target_width % 2
    target_height -= target_height % 2

    return target_width, target_height
