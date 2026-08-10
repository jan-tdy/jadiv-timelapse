# Jadiv-Timelapse

Jednoduchý nástroj na vytvorenie timelapse videa zo sekvencie fotiek (napr. z fotoaparátu na statíve alebo z kamery). Vyberieš priečinok s fotkami, nastavíš snímkovú frekvenciu a cieľové rozlíšenie a nástroj z nich poskladá výsledné video.

Projekt obsahuje tri nezávislé varianty s rovnakou funkcionalitou — vyber si podľa toho, čo ti vyhovuje:

| Súbor | Popis | Vyžaduje |
|---|---|---|
| `jadiv-timelapse.py` | Jednoduché desktopové GUI (Tkinter) | Python 3, OpenCV |
| `jadiv-timelapse_plus.py` | Pokročilejšie desktopové GUI s tmavým vzhľadom (PyQt5) | Python 3, OpenCV, PyQt5 |
| `jadiv-timelapse_web.html` | Webová verzia bežiaca priamo v prehliadači, bez inštalácie | Moderný prehliadač (Chrome/Edge/Firefox) |

## Funkcie

- Vytvorenie timelapse videa z `.jpg` / `.jpeg` / `.png` fotiek (aj veľké JPG z fotoaparátov)
- Nastaviteľná snímková frekvencia (FPS)
- Voliteľné cieľové rozlíšenie (4K, Full HD, HD, SD, nízka kvalita alebo originálne rozlíšenie) so zachovaním pomeru strán
- Zobrazenie priebehu spracovania a možnosť spracovanie kedykoľvek zrušiť
- Spracovanie beží na pozadí (GUI/stránka nezamrzne)

## Požiadavky a inštalácia (desktopové verzie)

Potrebuješ Python 3.8+ a nasledovné knižnice:

```bash
pip install -r requirements.txt
```

`jadiv-timelapse.py` navyše používa `tkinter`, ktorý je súčasťou štandardnej inštalácie Pythonu na Windows aj macOS. Na Linuxe ho môžeš doinštalovať cez balíčkovací systém, napr.:

```bash
# Debian / Ubuntu
sudo apt install python3-tk
```

## Použitie

### Desktopová verzia (Tkinter)

```bash
python3 jadiv-timelapse.py
```

### Desktopová verzia Plus (PyQt5)

```bash
python3 jadiv-timelapse_plus.py
```

### Webová verzia

Stačí otvoriť `jadiv-timelapse_web.html` v prehliadači (dvojklikom, alebo cez `File > Open`). Fotky sa spracúvajú lokálne v prehliadači, nikam sa neposielajú. Výstupom je video vo formáte `.webm`.

V oboch desktopových verziách stačí:

1. Vybrať priečinok s fotkami.
2. Vybrať, kam a pod akým názvom sa má uložiť výsledné video (`.mp4`).
3. Nastaviť FPS a cieľové rozlíšenie.
4. Kliknúť na **VYTVORIŤ TIMELAPSE** (alebo stlačiť Enter).

Spracovanie je možné kedykoľvek prerušiť tlačidlom **Zrušiť**.

## Poznámky

- Fotky sa zoraďujú podľa názvu súboru pomocou tzv. prirodzeného (numerického) triedenia — `frame2.jpg` sa teda zoradí pred `frame10.jpg`, aj bez núl na začiatku čísla. Napriek tomu sa oplatí používať konzistentný formát názvov (napr. `IMG_0001.jpg`, `IMG_0002.jpg`, ...).
- Poškodené alebo nečitateľné fotky sa pri spracovaní preskočia a do videa sa nezahrnú.
- Kodeky pre MP4/WebM vyžadujú párnu šírku aj výšku videa — nástroj to rieši automaticky.

## Licencia

Tento projekt je dostupný pod licenciou uvedenou v súbore [LICENSE](LICENSE).
