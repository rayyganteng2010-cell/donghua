from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper V7")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8"
}

BASE_URL = "https://v1.samehadaku.how"

# pakai 1 session global (lebih cepat + koneksi reuse)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_soup(url: str):
    try:
        r = SESSION.get(url, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def parse_schedule_row(row) -> dict | None:
    """
    Parser khusus halaman jadwal-rilis:
    - cari link anime (/anime/...)
    - cari jam (HH:MM) di row yang sama
    - ambil type/score/genre kalau kebaca dari teks, tapi ga maksa
    """
    a = row.select_one('a[href*="/anime/"]')
    if not a:
        return None

    link = a.get("href")
    txt = _clean_text(a.get_text(" ", strip=True))

    # cari jam di seluruh row text (sering jam itu elemen terpisah)
    row_txt = _clean_text(row.get_text(" ", strip=True))
    m_time = re.search(r"\b([01]\d|2[0-3]):[0-5]\d\b", row_txt)
    time_str = m_time.group(0) if m_time else None

    # coba tebak type + score dari awal teks: "TV 6.68 Judul ..."
    anime_type = None
    score = None
    title_guess = txt

    m = re.match(r"^(TV|Movie|ONA|OVA|Special)\s+([0-9]+(?:\.[0-9]+)?)\s+(.*)$", txt, re.IGNORECASE)
    if m:
        anime_type = m.group(1)
        score = m.group(2)
        title_guess = m.group(3).strip()

    # genres kadang muncul di anchor text setelah judul,
    # tapi pola tiap saat bisa berubah, jadi ambil kalau ada container genre
    genres = [ _clean_text(x.get_text(strip=True)) for x in row.select(".genres a, .genre a") ] or []

    return {
        "title": title_guess,
        "link": link,
        "time": time_str,
        "type": anime_type,
        "score": score,
        "genres": genres
    }

@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup:
        return JSONResponse(content={"success": False, "error": "failed_to_fetch"}, status_code=502)

    final_schedule = {
        "Monday": [], "Tuesday": [], "Wednesday": [], "Thursday": [],
        "Friday": [], "Saturday": [], "Sunday": []
    }

    # Indo -> Eng (Jumat punya alias 'Jumaat' di halaman)
    indo_to_eng = {
        "senin": "Monday",
        "selasa": "Tuesday",
        "rabu": "Wednesday",
        "kamis": "Thursday",
        "jumat": "Friday",
        "jumaat": "Friday",
        "sabtu": "Saturday",
        "minggu": "Sunday",
    }

    # 1) Ambil tab hari + target pane dari nav tabs (paling stabil buat halaman tab)
    # contoh: <a href="#senin">Senin</a>
    tab_links = soup.select(".nav-tabs a[href^='#'], ul li a[href^='#'], a[href^='#']")
    tabs = []
    for a in tab_links:
        day_txt = _clean_text(a.get_text(strip=True)).lower()
        href = a.get("href") or ""
        if not href.startswith("#"):
            continue
        if day_txt in indo_to_eng:
            tabs.append((day_txt, href.lstrip("#")))

    # fallback kalau selector tab ga ketemu (ya namanya juga web)
    if not tabs:
        # cari list hari yang tampil di halaman (minimal yang kelihatan)
        for day_txt in indo_to_eng.keys():
            el = soup.find(lambda t: t and t.get_text(strip=True).lower() == day_txt)
            if el:
                # coba tebak pane: cari elemen dengan id=day_txt
                tabs.append((day_txt, day_txt))

    # 2) Parse isi tiap pane
    for indo_day, pane_id in tabs:
        eng = indo_to_eng.get(indo_day)
        if not eng:
            continue

        pane = soup.find(id=pane_id)
        if not pane:
            # fallback: cari section/tab-pane yang mengandung teks hari tsb
            pane = soup.find(lambda t: t.name in ["div", "section"] and t.get("class") and "tab-pane" in t.get("class", []) and indo_day in _clean_text(t.get_text(" ", strip=True)).lower())

        if not pane:
            continue

        # row item bisa <li>, <div>, atau apapun. kita ambil kandidat yang punya link anime.
        candidates = pane.select("li, .animepost, div, article")
        items = []
        for row in candidates:
            if not row.select_one('a[href*="/anime/"]'):
                continue
            parsed = parse_schedule_row(row)
            if parsed:
                items.append(parsed)

        # buang duplikat judul+time (kadang markup dobel)
        seen = set()
        dedup = []
        for it in items:
            key = (it.get("title"), it.get("time"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(it)

        final_schedule[eng] = dedup

    return JSONResponse(content={"success": True, "data": final_schedule})
