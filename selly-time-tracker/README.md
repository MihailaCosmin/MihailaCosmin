# Selly Time Tracker

Program pentru Windows 11 care monitorizează automat orele lucrate la proiectul
**selly**. Urmărește fereastra activă și contorizează timpul petrecut în:

| Aplicație | Cum decide dacă e proiectul selly |
|---|---|
| **Ableton Live** | Doar dacă titlul ferestrei (numele set-ului deschis) conține „selly". Dacă mixezi altă piesă, timpul e trecut separat la „altele". |
| **Unreal Engine** | Tot timpul e contorizat ca selly (configurabil). |
| **Blender** | Tot timpul e contorizat ca selly (configurabil). |
| **DaVinci Resolve** | Tot timpul e contorizat ca selly (configurabil). |

În plus:
- detectează când ești **inactiv** (fără mouse/tastatură peste 3 minute) și oprește cronometrul, ca să nu numere pauzele;
- salvează totul într-o bază de date locală (`selly_tracker.db`) — nimic nu pleacă de pe calculatorul tău;
- nu are nevoie de niciun pachet instalat suplimentar, doar Python.

## Instalare

1. Instalează Python 3 de pe [python.org/downloads](https://www.python.org/downloads/)
   — la instalare **bifează „Add Python to PATH"**.
2. Descarcă folderul `selly-time-tracker` oriunde pe calculator (ex. `D:\selly-time-tracker`).
3. Dublu-click pe **`porneste_tracker.bat`** — trackerul pornește în fundal, fără fereastră.

Opțional: dublu-click pe **`instaleaza_autostart.bat`** (ca Administrator) ca
trackerul să pornească singur la fiecare logare în Windows. Nu mai trebuie să
te gândești la el niciodată.

## Foarte important pentru Ableton

Trackerul își dă seama că lucrezi la selly după **numele set-ului Live**
(care apare în titlul ferestrei). Deci salvează-ți set-urile proiectului cu
„selly" în nume, de exemplu:

- `selly_intro.als` ✔
- `Selly - Main Theme.als` ✔ (nu contează literele mari/mici)
- `piesa_noua.als` ✘ → va fi contorizat la „altele" (mixaje / alte piese)

## Rapoarte

Dublu-click pe **`raport.bat`** pentru raportul săptămânii curente, sau din
terminal (CMD/PowerShell, în folderul programului):

```
python selly_tracker.py report azi
python selly_tracker.py report saptamana
python selly_tracker.py report luna
python selly_tracker.py report tot
python selly_tracker.py report 2026-07-01 2026-07-04
python selly_tracker.py report luna --csv raport.csv   (export pentru Excel)
python selly_tracker.py status                          (ruleaza? + totalul de azi)
```

Exemplu de raport:

```
=== Raport proiect 'selly': 2026-06-29 → 2026-07-04 ===

Total proiect: 14h 22m
  Unreal Engine      6h 40m
  Ableton Live       4h 12m
  Blender            2h 05m
  DaVinci Resolve    1h 25m

In afara proiectului (alte piese / alte fisiere):
  Ableton Live       3h 18m

Pe zile (doar proiect):
  2026-06-30  4h 10m
  2026-07-01  3h 55m
  2026-07-03  6h 17m
```

## Oprire

- **`opreste_tracker.bat`** — oprește trackerul.
- **`dezinstaleaza_autostart.bat`** — îl scoate de la pornirea automată.

## Configurare (`config.json`)

Fișierul se creează automat la prima pornire. Poți modifica:

- `keywords` — cuvintele după care recunoaște proiectul în titlul ferestrei
  (poți adăuga mai multe, ex. `["selly", "sely"]`);
- `idle_seconds` — după câte secunde de inactivitate se oprește cronometrul
  (implicit 180 = 3 minute);
- `apps` → `match` — pentru fiecare aplicație:
  - `"always"` = tot timpul în aplicația respectivă e contorizat ca selly;
  - `"title"` = doar dacă titlul ferestrei conține un cuvânt-cheie (ca la
    Ableton). Dacă începi să folosești Blender/Unreal/DaVinci și pentru alte
    proiecte, schimbă `match` în `"title"` și pune „selly" în numele
    fișierelor/proiectelor.

După orice modificare în `config.json`, repornește trackerul
(`opreste_tracker.bat` apoi `porneste_tracker.bat`).
