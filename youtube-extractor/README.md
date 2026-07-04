# YouTube Transcript & Comments Extractor

Script Python care extrage transcriptul si comentariile pentru unul sau mai
multe video-uri YouTube, primite ca link-uri (sau ID-uri) intr-o singura
rulare.

## Instalare

```bash
cd youtube-extractor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Cheie API pentru comentarii (optional)

Transcriptul functioneaza fara nicio cheie. Pentru comentarii ai nevoie de
o cheie YouTube Data API v3 (gratuita, din
[Google Cloud Console](https://console.cloud.google.com/) -> activezi
"YouTube Data API v3" -> creezi o API key):

```bash
export YOUTUBE_API_KEY="cheia_ta"
```

Daca nu setezi cheia, scriptul extrage doar transcriptul si sare peste
comentarii.

## Utilizare

Unul sau mai multe link-uri deodata, ca argumente:

```bash
python extractor.py "https://www.youtube.com/watch?v=VIDEO_ID_1" "https://youtu.be/VIDEO_ID_2"
```

Dintr-un fisier cu un link pe linie:

```bash
python extractor.py --file urls.txt
```

Sau prin stdin:

```bash
cat urls.txt | python extractor.py
```

### Optiuni utile

| Argument | Descriere |
|---|---|
| `--output-dir DIR` | Director de iesire (implicit `output/`) |
| `--langs ro,en` | Limbi preferate pentru transcript, in ordinea preferintei |
| `--max-comments N` | Numar maxim de comentarii de top per video (implicit 200) |
| `--comments-order relevance\|time` | Ordinea comentariilor |
| `--no-transcript` | Sare peste transcript |
| `--no-comments` | Sare peste comentarii |

## Rezultat

Pentru fiecare video se creeaza un folder `output/<video_id>_<titlu>/` cu:

- `transcript.txt` - transcript cu timestamp-uri `[mm:ss]`
- `transcript.json` - transcript brut (text, start, durata)
- `comments.json` - comentarii + raspunsuri, structurat
- `comments.csv` - comentarii intr-un tabel (autor, text, likes, data)
- `comments.txt` - comentarii lizibile, cu raspunsurile indentate

La final se afiseaza un sumar cu statusul pentru fiecare video procesat.

## Limitari

- Transcriptul functioneaza doar daca YouTube ofera subtitrari
  (automate sau manuale) pentru acel video.
- Comentariile necesita o cheie YouTube Data API v3 si sunt supuse
  cotei zilnice gratuite a Google (10.000 unitati/zi implicit).
- Video-urile private, restrictionate pe varsta sau cu comentarii
  dezactivate nu vor returna date pentru sectiunea respectiva.
