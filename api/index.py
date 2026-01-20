from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper V9 - Scanner Mode")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
}

BASE_URL = "https://v1.samehadaku.how"

def get_soup(url: str):
    try:
        session = requests.Session()
        req = session.get(url, headers=HEADERS, timeout=20)
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

# --- PARSER ITEM (Format JSON Request) ---
def parse_item(node):
    try:
        # Cari elemen link (<a>)
        a_tag = node.find("a")
        if not a_tag: return None
        
        url = a_tag['href']
        
        # Title: Prioritas text di dalam tag judul, kalau gak ada ambil dari atribut title
        title = "Unknown"
        title_node = node.find("div", class_="title") or node.find("div", class_="dtla") or a_tag
        if title_node: title = title_node.get_text(strip=True)
        if not title or len(title) < 2: title = a_tag.get("title", "Unknown")

        # Image
        img_tag = node.find("img")
        image = "https://dummyimage.com/300x400/000/fff&text=No+Image"
        if img_tag:
            image = img_tag.get('src')
            if not image or "data:image" in image:
                image = img_tag.get('data-src') or img_tag.get('srcset') or image
        if image: image = image.split("?")[0] # Clean URL

        # Type (TV/Movie)
        type_anime = "TV"
        type_tag = node.find("div", class_="type")
        if type_tag: type_anime = type_tag.get_text(strip=True)

        # Score
        score = "?"
        score_tag = node.find("div", class_="score") or node.find("span", class_="score")
        if score_tag: score = score_tag.get_text(strip=True)

        # Genre (String)
        genres_list = []
        # Coba cari genre di dalam node ini
        g_tags = node.select(".genres a") or node.select(".genre a")
        if g_tags:
            genres_list = [g.get_text(strip=True) for g in g_tags]
        genre_str = ", ".join(genres_list) if genres_list else "-"

        # Time
        time_release = "??"
        time_tag = node.find("span", class_="time") or node.find("div", class_="btime") or node.find("span", class_="date")
        if time_tag: time_release = time_tag.get_text(strip=True)

        return {
            "title": title,
            "url": url,
            "image": image,
            "type": type_anime,
            "score": score,
            "genre": genre_str,
            "time": time_release
        }
    except:
        return None

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API V9 - Full Scanner"}

# --- 1. JADWAL (ALGORITMA SCANNER) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False, "message": "Gagal fetch data"}
    
    # Template Data
    schedule_data = {
        "monday": {"dayName": "Senin", "totalItems": 0, "items": []},
        "tuesday": {"dayName": "Selasa", "totalItems": 0, "items": []},
        "wednesday": {"dayName": "Rabu", "totalItems": 0, "items": []},
        "thursday": {"dayName": "Kamis", "totalItems": 0, "items": []},
        "friday": {"dayName": "Jumat", "totalItems": 0, "items": []},
        "saturday": {"dayName": "Sabtu", "totalItems": 0, "items": []},
        "sunday": {"dayName": "Minggu", "totalItems": 0, "items": []}
    }
    
    # Mapping Regex biar lebih fleksibel (case insensitive)
    # Key harus sama dengan keys di schedule_data
    day_patterns = {
        "monday": re.compile(r"senin", re.I),
        "tuesday": re.compile(r"selasa", re.I),
        "wednesday": re.compile(r"rabu", re.I),
        "thursday": re.compile(r"kamis", re.I),
        "friday": re.compile(r"jumat", re.I),
        "saturday": re.compile(r"sabtu", re.I),
        "sunday": re.compile(r"minggu", re.I)
    }

    # Cari area konten. Kalau entry-content gak ketemu, pake body aja sekalian.
    content = soup.find("div", class_="entry-content") or soup.find("main") or soup.find("body")
    
    # Ambil SEMUA elemen yang relevan secara berurutan
    # Kita ambil header (h3/h4/span/b) dan container anime (div/li)
    all_elements = content.find_all(["h3", "h4", "div", "span", "b", "strong", "li"])
    
    current_day_key = None
    
    for el in all_elements:
        text = el.get_text(strip=True)
        
        # 1. CEK APAKAH INI HEADER HARI?
        # Syarat: Teksnya pendek (misal "Senin" atau "Hari Senin"), bukan kalimat panjang
        if len(text) < 20: 
            found_new_day = False
            for key, pattern in day_patterns.items():
                if pattern.search(text):
                    current_day_key = key
                    found_new_day = True
                    break
            if found_new_day:
                continue # Skip elemen header ini, lanjut ke bawah

        # 2. KALAU LAGI DI DALAM HARI, CARI ANIME
        if current_day_key:
            # Cek ciri-ciri anime item:
            # - Punya class 'animepost'
            # - ATAU elemen 'li' yang punya link
            classes = el.get("class", [])
            is_anime = False
            
            if "animepost" in classes:
                is_anime = True
            elif el.name == "li" and el.find("a"):
                # Filter biar gak ngambil menu navigasi
                if not el.find_parent("nav") and "menu" not in str(el.get("class")):
                    is_anime = True
            
            if is_anime:
                parsed = parse_item(el)
                if parsed and parsed['url'] and "anime/" in parsed['url']:
                    # Cek duplikat judul di hari yang sama
                    existing_titles = [x['title'] for x in schedule_data[current_day_key]['items']]
                    if parsed['title'] not in existing_titles:
                        schedule_data[current_day_key]['items'].append(parsed)

    # Hitung total items terakhir
    for k in schedule_data:
        schedule_data[k]['totalItems'] = len(schedule_data[k]['items'])

    return JSONResponse(content={"success": True, "data": schedule_data})

# --- 2. LATEST (SELECTOR LENGKAP) ---
@app.get("/api/latest")
def get_latest():
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False}
    data = []
    
    # Ambil semua animepost
    posts = soup.select(".post-show li") or soup.select(".animepost") or soup.select("div.post-article")
    
    for post in posts:
        parsed = parse_item(post) # Reuse fungsi parser yang sama
        if parsed:
            # Tambahan khusus latest
            ep = "New"
            ep_tag = post.find("span", class_="episode") or post.find("div", class_="dtla")
            if ep_tag: ep = ep_tag.get_text(strip=True)
            
            # Format output latest sedikit beda (sesuai request awal)
            data.append({
                "title": parsed['title'],
                "link": parsed['url'],
                "thumbnail": parsed['image'],
                "episode": ep,
                "posted": parsed['time']
            })
    return JSONResponse(content={"success": True, "data": data})

# --- 3. DETAIL & SEARCH (STANDARD) ---
@app.get("/api/detail")
def get_detail(url: str):
    soup = get_soup(url)
    if not soup: return {"success": False}
    result = {}
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        img = soup.find("div", class_="thumb").find("img")['src']
        
        desc = "-"
        desc_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        if desc_div: desc = desc_div.get_text(strip=True)
        
        episodes = []
        for li in soup.select(".lstepsiode li"):
            episodes.append({
                "title": li.find("a").get_text(strip=True),
                "url": li.find("a")['href'],
                "date": li.find("span", class_="date").get_text(strip=True) if li.find("span", class_="date") else "?"
            })
        return {"success": True, "result": {"title": title, "cover": img, "synopsis": desc, "episodes": episodes}}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/search")
def search(query: str):
    soup = get_soup(f"{BASE_URL}/?s={query}")
    data = []
    if soup:
        for item in soup.select(".animepost"):
            parsed = parse_item(item)
            if parsed: data.append(parsed)
    return {"success": True, "results": data}
