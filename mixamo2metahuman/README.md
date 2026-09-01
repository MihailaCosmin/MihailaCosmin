# Mixamo -> MetaHuman (UE5)

Aplicatie desktop cu interfata simpla care pregateste personajele si animatiile
descarcate de pe [Mixamo](https://www.mixamo.com) pentru Unreal Engine 5 si
pentru retargeting pe MetaHuman.

Problema pe care o rezolva: scheletul Mixamo (`mixamorig:Hips`, `LeftUpLeg`, ...)
nu seamana cu cel UE5/MetaHuman (`pelvis`, `thigh_l`, ...), nu are os `root`,
deci nu are root motion, iar in editor trebuie mapate manual zeci de oase pentru
fiecare animatie. Aplicatia face automat partea repetitiva.

## Ce face

- Redenumeste oasele in conventia UE5 Mannequin / MetaHuman (`pelvis`,
  `spine_01..03`, `clavicle_l`, `upperarm_l`, `thigh_r`, `ball_r`,
  `thumb_01_l` ... ) - astfel IK Retargeter-ul din UE5 potriveste lanturile
  automat, fara mapare manuala.
- Adauga osul `root` la origine si il pune parinte peste `pelvis`.
- **Root motion**: muta deplasarea orizontala de pe solduri pe `root`
  (calculata pe matricile din spatiul armaturii, nu prin copiere naiva de
  curbe), sau, daca preferi, fixeaza animatia **in place** pentru blendspace-uri.
- Exporta FBX cu setarile pe care le asteapta Unreal (fara leaf bones, axe
  corecte, animatie bake-uita).
- Proceseaza un fisier sau un folder intreg (batch).
- Genereaza optional un script Python pentru UE5 care importa tot ce a produs
  si poate rula si retargetul in bloc pe MetaHuman.

## Cerinte

| Ce | De ce |
|---|---|
| Python 3.9+ (cu `tkinter`) | interfata. Pe Windows/macOS vine cu installerul de pe python.org; pe Linux: `sudo apt install python3-tk` |
| [Blender](https://www.blender.org) 3.x sau 4.x | face importul/exportul FBX in fundal |
| Unreal Engine 5.0+ | destinatia; pentru scriptul generat activeaza "Python Editor Script Plugin" |

Nu instalezi nimic cu `pip` - aplicatia foloseste doar biblioteca standard.

## Pornire

```bash
python run.py
```

Aplicatia cauta singura Blender-ul in PATH si in locurile uzuale de instalare.
Daca nu il gaseste, apesi "Alege..." si ii dai calea (sau setezi variabila de
mediu `BLENDER_PATH`).

## Cum descarci corect de pe Mixamo

1. **Personajul**: alege-l, `Download` -> Format **FBX Binary (.fbx)**,
   Pose **T-pose**. Iese un FBX cu mesh + schelet.
2. **Animatiile**: cu personajul selectat, `Download` -> FBX Binary,
   Skin **Without Skin**, Frames per Second **30**, Keyframe Reduction **none**.
   Bifeaza **In Place** doar daca vrei tu animatia pe loc; daca vrei root
   motion, las-o nebifata si lasa aplicatia sa extraga deplasarea.

## Fluxul complet

**1. Personajul** - in aplicatie: adaugi FBX-ul personajului, alegi
`Export: Personaj (mesh + schelet)`, `Root motion: Lasa asa`, Converteste.

**2. Animatiile** - adaugi FBX-urile (sau folderul), alegi
`Export: Doar animatie` si `Root motion: Extrage pe osul root`, Converteste.

**3. Import in UE5** - tragi FBX-ul personajului in Content Browser
(Skeletal Mesh). Apoi importi animatiile alegand scheletul rezultat la pasul
anterior. Sau rulezi scriptul generat: `Tools > Execute Python Script...` ->
`unreal_import.py` din folderul de iesire (editeaza intai `SKELETON_PATH`).

**4. Retarget pe MetaHuman**
- Click-dreapta pe skeletal mesh-ul Mixamo -> `Create > IK Rig`. In IK Rig
  seteaza `Retarget Root = pelvis` si adauga lanturile (Spine, Head, LeftArm,
  RightArm, LeftLeg, RightLeg). Butonul "Auto Generate Retarget Chains"
  le gaseste singur, pentru ca oasele au deja nume UE5.
- Pentru MetaHuman foloseste `IK_Metahuman` (vine cu personajul) sau creeaza un
  IK Rig pe `m_med_nrw_body` / skeletal mesh-ul corpului.
- Click-dreapta -> `Animation > IK Retargeter`. Sursa = rigul Mixamo,
  tinta = rigul MetaHuman. Verifica in fereastra de preview ca lanturile sunt
  mapate; daca personajul e strambat, ajusteaza **Retarget Pose** pe ambele
  parti (Mixamo e in T-pose, MetaHuman in A-pose) - se face o singura data.
- Selectezi animatiile in Content Browser -> `Retarget Animation Assets`, sau
  completezi `RETARGETER_PATH`, `SOURCE_MESH_PATH`, `TARGET_MESH_PATH` in
  `unreal_import.py` si il rulezi pentru retarget in bloc.

**5. Root motion in UE5** - in AnimSequence bifezi `Enable Root Motion`
(sectiunea Root Motion) si, daca folosesti Animation Blueprint, `Root Motion
Mode = Root Motion from Montages/Everything`.

## Executabil (.exe) si folder gata de copiat

Ca sa nu ai nevoie de Python pe calculatorul unde folosesti aplicatia:

```bat
build_exe.bat                 :: construieste in dist\Mixamo2MetaHuman
build_exe.bat D:\Proiecte      :: si copiaza folderul pe D:\Proiecte
```

Pe Linux/macOS: `./build_exe.sh [destinatie]`.

Scriptul isi face singur un mediu virtual, instaleaza PyInstaller, ruleaza
testele si abia apoi construieste. Rezulta un folder cu:

```
Mixamo2MetaHuman/
    Mixamo2MetaHuman.exe        aplicatia cu interfata (dublu-click)
    mixamo2mh-cli.exe           aceleasi optiuni, din linia de comanda
    Citeste-ma.txt              pornire rapida
    README.md                   manualul asta
    Exemple/                    model de script de import pentru UE5
```

Un `.exe` de Windows se construieste **pe Windows** - PyInstaller nu face
cross-compile. Acelasi script ruleaza si pe Linux/macOS, dar produce
executabilul pentru sistemul pe care l-ai rulat.

Blender ramane necesar si langa executabil. Daca vrei folderul complet
portabil, pune un Blender portabil in subfolderul `Blender/` de langa `.exe` -
aplicatia il gaseste automat, inaintea celui instalat in sistem.

## Linia de comanda

Aceleasi optiuni, fara interfata:

```bash
# un folder intreg de animatii, cu root motion, si scriptul pentru UE5
python -m mixamo2mh ~/Downloads/mixamo -o ~/UE5_Export \
    --mode animation --root-motion extract --unreal-script

# personajul
python -m mixamo2mh ~/Downloads/Character.fbx -o ~/UE5_Export --mode character

# animatii pe loc, pentru blendspace
python -m mixamo2mh ~/Downloads/mixamo -o ~/UE5_Export --root-motion inplace
```

`python -m mixamo2mh --help` arata toate optiunile.

## Structura

```
mixamo2mh/
  bone_map.py       maparea Mixamo -> UE5 (fara dependinte, testabila)
  settings.py       optiunile unei conversii + validare
  blender.py        gaseste Blender-ul si conduce procesele de conversie
  blender_ops.py    scriptul care ruleaza INAUNTRUL Blender-ului
  unreal_script.py  genereaza scriptul de import/retarget pentru UE5
  gui.py            interfata tkinter
  cli.py            interfata din linia de comanda
tests/              teste pentru tot ce nu are nevoie de Blender
run.py              pornire rapida
```

Fiecare FBX e procesat intr-un proces Blender separat, ca un fisier stricat sa
nu darame tot batch-ul; erorile ajung in jurnalul din interfata.

## Teste

```bash
python -m unittest discover -s tests -v
```

Suita are doua parti:

- **teste unitare** - maparea oaselor, validarea setarilor, generarea scriptului
  pentru UE5, parsarea argumentelor. Ruleaza oriunde, fara Blender.
- **teste de integrare** - construiesc un FBX cu structura Mixamo, il trec prin
  conversie si verifica rezultatul: numele oaselor, ierarhia `root -> pelvis`,
  faptul ca traiectoria soldurilor in lume ramane identica dupa extragerea root
  motion (verificat sub 1 mm), ca `In place` blocheaza doar deplasarea
  orizontala, ca modul personaj pastreaza mesh-ul si grupurile de vertecsi
  redenumite, ca scala se aplica, si ca o a doua conversie peste acelasi fisier
  nu strica nimic. Se sar automat daca Blender nu e disponibil ca modul;
  pentru a le rula: `pip install bpy` (necesita Python 3.11).

## Daca ceva nu iese bine

| Simptom | Cauza uzuala |
|---|---|
| Personajul e de 100x mai mare/mic in UE5 | pune `Scala` pe `0.01` sau `100` la conversie, ori schimba Import Uniform Scale la import |
| Personajul aluneca sau ramane pe loc | ai ales `Extrage pe osul root` dar animatia era deja "In Place" de pe Mixamo (sau invers) |
| Retargetul iese strambat | ajusteaza Retarget Pose in IK Retargeter (T-pose vs A-pose), nu lanturile |
| Degetele nu se misca | animatia de pe Mixamo nu contine degete - normal, nu e o eroare de conversie |
| "Nu gasesc osul pelvis" | ai debifat "Redenumeste oasele"; root motion are nevoie de redenumire |
| Oase raportate ca "fara corespondent UE5" | oase extra (par, fusta, arme) - raman cu numele lor, nu strica nimic |
| Animatia are translatii si pe alte oase decat soldurile si se pierd | debifeaza "Orientare automata a oaselor": la import Blender conecteaza oasele si ignora canalele de translatie ale celor conectate |
