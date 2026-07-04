#!/usr/bin/env python3
"""Extrage transcriptul si comentariile pentru unul sau mai multe video-uri YouTube.

Exemple:
    python extractor.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
    python extractor.py URL1 URL2 URL3 --output-dir output
    python extractor.py --file urls.txt --max-comments 300
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from urllib.parse import urlparse, parse_qs

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

YOUTUBE_COMMENTS_ENDPOINT = "https://www.googleapis.com/youtube/v3/commentThreads"
YOUTUBE_OEMBED_ENDPOINT = "https://www.youtube.com/oembed"


def extract_video_id(url: str) -> str:
    """Extrage ID-ul video-ului dintr-un URL YouTube in orice format uzual."""
    url = url.strip()
    if not url:
        raise ValueError("URL gol")

    # Deja e doar un ID (11 caractere, litere/cifre/-/_)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url

    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "").replace("m.", "")

    if host in ("youtu.be",):
        video_id = parsed.path.lstrip("/").split("/")[0]
        if video_id:
            return video_id

    if host in ("youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        for prefix in ("/embed/", "/shorts/", "/v/", "/live/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix):].split("/")[0]
                if video_id:
                    return video_id

    raise ValueError(f"Nu am putut extrage video ID din: {url}")


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    name = re.sub(r"[\s]+", "_", name)
    return name[:80] or "video"


def get_video_title(video_id: str) -> str:
    try:
        resp = requests.get(
            YOUTUBE_OEMBED_ENDPOINT,
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10,
        )
        if resp.ok:
            return resp.json().get("title", video_id)
    except requests.RequestException:
        pass
    return video_id


def format_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fetch_transcript(video_id: str, languages):
    """Returneaza (lista_segmente, limba_folosita, eroare)."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except (TranscriptsDisabled, VideoUnavailable) as e:
        return None, None, str(e)
    except Exception as e:  # noqa: BLE001 - raportam orice eroare neasteptata
        return None, None, str(e)

    try:
        transcript = transcript_list.find_transcript(languages)
    except NoTranscriptFound:
        try:
            # nicio limba ceruta -> luam prima disponibila si o traducem daca se poate
            transcript = next(iter(transcript_list))
            if languages:
                try:
                    transcript = transcript.translate(languages[0])
                except Exception:  # noqa: BLE001
                    pass
        except StopIteration:
            return None, None, "Niciun transcript disponibil pentru acest video"

    try:
        data = transcript.fetch()
    except Exception as e:  # noqa: BLE001
        return None, None, str(e)

    return data, transcript.language_code, None


def save_transcript(segments, out_dir):
    txt_path = os.path.join(out_dir, "transcript.txt")
    json_path = os.path.join(out_dir, "transcript.json")

    with open(txt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"[{format_timestamp(seg['start'])}] {seg['text']}\n")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)

    return txt_path, json_path


def fetch_comments(video_id: str, api_key: str, max_comments: int, order: str):
    """Descarca comentariile (+ raspunsuri) folosind YouTube Data API v3."""
    comments = []
    page_token = None

    while len(comments) < max_comments:
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "key": api_key,
            "maxResults": min(100, max_comments - len(comments)),
            "order": order,
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(YOUTUBE_COMMENTS_ENDPOINT, params=params, timeout=15)
        if not resp.ok:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise RuntimeError(f"Eroare API comentarii ({resp.status_code}): {detail}")

        data = resp.json()
        for item in data.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            entry = {
                "author": top.get("authorDisplayName"),
                "text": top.get("textDisplay"),
                "like_count": top.get("likeCount"),
                "published_at": top.get("publishedAt"),
                "reply_count": item["snippet"].get("totalReplyCount", 0),
                "replies": [],
            }
            for reply in item.get("replies", {}).get("comments", []):
                r = reply["snippet"]
                entry["replies"].append(
                    {
                        "author": r.get("authorDisplayName"),
                        "text": r.get("textDisplay"),
                        "like_count": r.get("likeCount"),
                        "published_at": r.get("publishedAt"),
                    }
                )
            comments.append(entry)

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.1)

    return comments[:max_comments]


def save_comments(comments, out_dir):
    json_path = os.path.join(out_dir, "comments.json")
    csv_path = os.path.join(out_dir, "comments.csv")
    txt_path = os.path.join(out_dir, "comments.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["author", "text", "like_count", "published_at", "is_reply", "parent_author"])
        for c in comments:
            writer.writerow([c["author"], c["text"], c["like_count"], c["published_at"], False, ""])
            for r in c["replies"]:
                writer.writerow([r["author"], r["text"], r["like_count"], r["published_at"], True, c["author"]])

    with open(txt_path, "w", encoding="utf-8") as f:
        for c in comments:
            f.write(f"{c['author']} ({c['like_count']} likes): {c['text']}\n")
            for r in c["replies"]:
                f.write(f"    -> {r['author']} ({r['like_count']} likes): {r['text']}\n")
            f.write("\n")

    return json_path, csv_path, txt_path


def read_urls(args) -> list:
    urls = list(args.urls)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    if not urls and not sys.stdin.isatty():
        urls.extend(line.strip() for line in sys.stdin if line.strip())
    return urls


def main():
    parser = argparse.ArgumentParser(description="Extractor transcript + comentarii YouTube")
    parser.add_argument("urls", nargs="*", help="Unul sau mai multe URL-uri/ID-uri video YouTube")
    parser.add_argument("--file", help="Fisier text cu un URL pe linie")
    parser.add_argument("--output-dir", default="output", help="Director de iesire (default: output)")
    parser.add_argument("--langs", default="ro,en", help="Limbi preferate pentru transcript, separate prin virgula")
    parser.add_argument("--max-comments", type=int, default=200, help="Numar maxim de comentarii de top de descarcat per video")
    parser.add_argument("--comments-order", default="relevance", choices=["relevance", "time"], help="Ordinea comentariilor")
    parser.add_argument("--no-transcript", action="store_true", help="Sari peste extragerea transcriptului")
    parser.add_argument("--no-comments", action="store_true", help="Sari peste extragerea comentariilor")
    args = parser.parse_args()

    urls = read_urls(args)
    if not urls:
        parser.error("Nu ai dat niciun URL. Foloseste argumente, --file sau stdin.")

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not args.no_comments and not api_key:
        print("[!] YOUTUBE_API_KEY nu este setat - comentariile vor fi sarite pentru toate video-urile.", file=sys.stderr)

    languages = [l.strip() for l in args.langs.split(",") if l.strip()]
    os.makedirs(args.output_dir, exist_ok=True)

    summary = []

    for raw_url in urls:
        print(f"\n=== {raw_url} ===")
        try:
            video_id = extract_video_id(raw_url)
        except ValueError as e:
            print(f"[eroare] {e}")
            summary.append({"url": raw_url, "video_id": None, "transcript": "eroare", "comments": "eroare"})
            continue

        title = get_video_title(video_id)
        folder_name = f"{video_id}_{sanitize_filename(title)}"
        out_dir = os.path.join(args.output_dir, folder_name)
        os.makedirs(out_dir, exist_ok=True)
        print(f"Video: {title} ({video_id})")

        transcript_status = "sarit"
        if not args.no_transcript:
            segments, lang, error = fetch_transcript(video_id, languages)
            if error:
                transcript_status = f"eroare: {error}"
                print(f"[transcript] {transcript_status}")
            else:
                txt_path, json_path = save_transcript(segments, out_dir)
                transcript_status = f"ok ({lang}, {len(segments)} segmente)"
                print(f"[transcript] salvat in {txt_path}")

        comments_status = "sarit"
        if not args.no_comments:
            if not api_key:
                comments_status = "sarit (fara YOUTUBE_API_KEY)"
            else:
                try:
                    comments = fetch_comments(video_id, api_key, args.max_comments, args.comments_order)
                    save_comments(comments, out_dir)
                    comments_status = f"ok ({len(comments)} comentarii de top)"
                    print(f"[comentarii] salvate in {out_dir}")
                except RuntimeError as e:
                    comments_status = f"eroare: {e}"
                    print(f"[comentarii] {comments_status}")

        summary.append(
            {
                "url": raw_url,
                "video_id": video_id,
                "title": title,
                "transcript": transcript_status,
                "comments": comments_status,
            }
        )

    print("\n=== Sumar ===")
    for s in summary:
        print(f"- {s.get('title', s['url'])}: transcript={s['transcript']} | comentarii={s['comments']}")


if __name__ == "__main__":
    main()
