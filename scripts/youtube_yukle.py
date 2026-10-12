#!/usr/bin/env python3
"""video_olustur.py'nin ürettiği videoyu YouTube'a yükler. Sadece videoyu izleyip onayladıktan sonra çalıştır.

İlk kurulum (bir kez):
  1. https://console.cloud.google.com → yeni proje → "YouTube Data API v3"ü etkinleştir.
  2. OAuth izin ekranı: "External", kendi e-postanı "Test users" listesine ekle.
  3. Kimlik bilgileri → OAuth istemci kimliği → "Masaüstü uygulaması" → JSON'u indir,
     proje köküne client_secret.json adıyla koy (git'e girmez).

Kullanım:
  python scripts/youtube_yukle.py cikti/gun01_2026-10-12.json               # gizli (private) yükler
  python scripts/youtube_yukle.py cikti/gun01_2026-10-12.json --durum unlisted
"""
import argparse
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

KOK = Path(__file__).resolve().parent.parent
KAPSAM = ["https://www.googleapis.com/auth/youtube.upload"]


def kimlik():
    token = KOK / "token.json"
    cred = Credentials.from_authorized_user_file(str(token), KAPSAM) if token.exists() else None
    if cred and cred.expired and cred.refresh_token:
        cred.refresh(Request())
    if not cred or not cred.valid:
        cred = InstalledAppFlow.from_client_secrets_file(str(KOK / "client_secret.json"), KAPSAM).run_local_server(port=0)
    token.write_text(cred.to_json())
    return cred


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bilgi", type=Path, help="video_olustur.py'nin yazdığı .json dosyası")
    ap.add_argument("--durum", choices=["private", "unlisted", "public"], default="private")
    args = ap.parse_args()

    bilgi = json.loads(args.bilgi.read_text(encoding="utf-8"))
    video = Path(bilgi["video"])
    if not video.exists():
        video = args.bilgi.with_suffix(".mp4")
    print(f"Yüklenecek: {video.name}\nBaşlık: {bilgi['baslik']}\nGörünürlük: {args.durum}")
    if input("Onaylıyor musun? (e/h): ").strip().lower() not in {"e", "evet", "y"}:
        print("İptal edildi.")
        return

    youtube = build("youtube", "v3", credentials=kimlik())
    istek = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": bilgi["baslik"][:100], "description": bilgi["aciklama"][:5000],
                        "tags": bilgi["etiketler"], "categoryId": "17", "defaultLanguage": "tr"},
            "status": {"privacyStatus": args.durum, "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True),
    )
    yanit = None
    while yanit is None:
        durum, yanit = istek.next_chunk()
        if durum:
            print(f"  %{int(durum.progress() * 100)}")
    print(f"Yüklendi: https://youtu.be/{yanit['id']}")


if __name__ == "__main__":
    main()
