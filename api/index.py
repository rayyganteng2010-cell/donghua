from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper V10 - Tooltip Miner")

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

# --- PARSER SAKTI (TOOLTIP MINER) ---
def parse_anime_node(node):
    """
    Mengambil data detail dari node animepost.
    Mencari data tersembunyi di tooltip/metadata.
    """
    try:
        # 1. Judul & Link
        a_tag = node.find("a")
        if not a_tag: return None
        
        title = "Unknown"
        title_tag = node.find("div", class_="title") or node.find("a")
        if title_tag: title = title_tag.get_text(strip=True)
        if len(title) < 2: title = a_tag.get("title", "Unknown")
            
        url = a_tag['href']

        # 2. Image (Handling Lazy Load)
        img_tag = node.find("img")
        image = "https://dummyimage.com/300x400/000/fff&text=No+Image"
        if img_tag:
            image = img_tag.get('src')
            if not image or "data:image" in image:
                image = img_tag.get('data-src') or img_tag.get('srcset') or image
            if image and "?" in image: image = image.split("?")[0]

        # 3. TYPE (TV/Movie)
        # Biasanya ada label type di pojok gambar
        type_anime = "TV"
        type_tag = node.find("div", class_="type")
        if type_tag: type_anime = type_tag.get_text(strip=True)

        # 4. SCORE, TIME, GENRE (Gali dari Tooltip/Hidden Info)
        score = "?"
        genre_str = "-"
        time_release = "??"
        
        # Coba ambil dari elemen Score luar dulu
        score_out = node.find("div", class_="score")
        if score_out: score = score_out.get_text(strip=True)

        # GALI TOOLTIP (class 'ttls', 'dtla', atau 'tooltip')
        tooltip = node.find("div", class_="ttls") or node.find("div", class_="dtla") or node.find("div", class_="entry-content")
        
        if tooltip:
            # Parse text di dalam tooltip baris per baris
            tooltip_text = tooltip.get_text(" | ", strip=True) # Gabung pake separator biar gampang regex
            
            # Regex untuk cari info spesifik
            # Contoh data: "Genre: Action, Comedy | Durasi: 24 min | Skor: 8.5"
            
            # Cari Score (kalau di luar kosong)
            if score == "?":
                m_score = re.search(r'(?:Skor|Score)\s*:\s*([\d\.]+)', tooltip_text, re.I)
                if m_score: score = m_score.group(1)

            # Cari Genre
            # Genre biasanya list a href di dalam tooltip
            g_links = tooltip.find_all("a")
            # Filter link yang bukan link anime (biasanya genre linknya /genre/)
            g_list = [g.get_text(strip=True) for g in g_links if "/genre/" in g.get('href', '')]
            if g_list:
                genre_str = ", ".join(g_list)
            else:
                # Fallback regex
                m_genre = re.search(r'(?:Genre|Genres)\s*:\s*([^|]+)', tooltip_text, re.I)
                if m_genre: genre_str = m_genre.group(1).strip()

            # Cari Time / Durasi / Rilis
            # Di jadwal, biasanya jam tayang gak eksplisit, tapi kadang ada di 'Released' atau custom text
            m_time = re.search(r'(?:Pukul|Jam|Time)\s*:\s*([\d\:]+)', tooltip_text, re.I)
            if m_time: 
                time_release = m_time.group(1)
            else:
                # Coba cari elemen khusus time di luar tooltip
                time_tag = node.find("span", class_="time") or node.find("div", class_="btime")
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
    except Exception as e:
        # print(f"Error parsing item: {e}") 
        return None

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API V10 - Detail Miner"}

# --- 1. JADWAL (CONTAINER SEARCH + KEYWORD SEARCH) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False, "message": "Gagal fetch data"}
    
    # Template Data
    final_data = {
        "monday": {"dayName": "Senin", "totalItems": 0, "items": []},
        "tuesday": {"dayName": "Selasa", "totalItems": 0, "items": []},
        "wednesday": {"dayName": "Rabu", "totalItems": 0, "items": []},
        "thursday": {"dayName": "Kamis", "totalItems": 0, "items": []},
        "friday": {"dayName": "Jumat", "totalItems": 0, "items": []},
        "saturday": {"dayName": "Sabtu", "totalItems": 0, "items": []},
        "sunday": {"dayName": "Minggu", "totalItems": 0, "items": []}
    }
    
    # Mapping Nama Hari -> Key Dictionary
    day_map = {
        "senin": "monday", "selasa": "tuesday", "rabu": "wednesday",
        "kamis": "thursday", "jumat": "friday", "sabtu": "saturday", "minggu": "sunday"
    }

    # LOGIC PENCARIAN BARU:
    # Kita cari SEMUA elemen yang berpotensi jadi "Header Hari"
    # Lalu kita ambil elemen "Next Sibling" atau "Parent Container" nya.
    
    # Cari di area konten utama
    main_content = soup.find("div", class_="entry-content") or soup.find("main") or soup
    
    # Ambil semua tag H3/H4/DIV yang teksnya mengandung nama hari
    potential_headers = main_content.find_all(["h3", "h4", "div", "span", "b"])
    
    for header in potential_headers:
        text = header.get_text(strip=True).lower()
        
        # Validasi: Apakah ini header hari yang valid?
        found_key = None
        for indo, key in day_map.items():
            if indo in text and len(text) < 20: # Pastikan teksnya pendek ("Hari Senin", bukan kalimat)
                found_key = key
                break
        
        if found_key:
            # Header Ketemu! Sekarang cari Anime-nya.
            # Kita cari di "Next Sibling" (elemen setelahnya)
            # Karena struktur biasanya: <Header>Senin</Header> <Div class="anime-list">...</Div>
            
            container = header.find_next_sibling()
            
            # Loop cari sibling sampai ketemu container yang ada animenya atau ketemu header lain
            limit = 0
            while container and limit < 3: # Cek 3 elemen ke bawah max
                # Cek apakah container ini punya animepost?
                anime_nodes = container.select(".animepost") or container.select("li a")
                
                # Filter node sampah (misal link navigasi)
                valid_nodes = []
                if anime_nodes:
                    for node in anime_nodes:
                        # Kalau node-nya 'a' doang (list style), kita butuh parent 'li'
                        target_node = node if "animepost" in str(node.get("class")) else node.find_parent("li")
                        if target_node:
                            valid_nodes.append(target_node)

                if valid_nodes:
                    # Parse semua anime di container ini
                    for node in valid_nodes:
                        # Hindari duplikat link navigasi
                        if node.find("a") and "/anime/" in node.find("a").get("href", ""):
                            parsed = parse_anime_node(node)
                            # Cek duplikat judul di hari yang sama
                            if parsed and parsed['title'] not in [x['title'] for x in final_data[found_key]['items']]:
                                final_data[found_key]['items'].append(parsed)
                    break # Dah ketemu, stop loop sibling
                
                container = container.find_next_sibling()
                limit += 1

    # Update Total Items
    for k in final_data:
        final_data[k]['totalItems'] = len(final_data[k]['items'])

    return JSONResponse(content={"success": True, "data": final_data})

# --- 2. LATEST (SAFE PARSER) ---
@app.get("/api/latest")
def get_latest():
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False}
    data = []
    
    posts = soup.select(".post-show li") or soup.select(".animepost") or soup.select("div.post-article")
    
    for post in posts:
        parsed = parse_anime_node(post)
        if parsed:
            # Tambahan khusus latest
            ep = "New"
            ep_tag = post.find("span", class_="episode") or post.find("div", class_="dtla")
            if ep_tag: ep = ep_tag.get_text(strip=True)
            
            # Timpa time dengan 'posted' date
            date_tag = post.find("span", class_="date") or post.find("span", class_="year")
            posted = date_tag.get_text(strip=True) if date_tag else parsed['time']

            data.append({
                "title": parsed['title'],
                "link": parsed['url'],
                "thumbnail": parsed['image'],
                "episode": ep,
                "posted": posted,
                "type": parsed['type']
            })
    return JSONResponse(content={"success": True, "data": data})

# --- 3. DETAIL & SEARCH (STANDARD) ---
@app.get("/api/detail")
def get_detail(url: str):
    soup = get_soup(url)
    if not soup: return {"success": False}
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        img = soup.find("div", class_="thumb").find("img")['src']
        desc = soup.find("div", class_="desc").get_text(strip=True) if soup.find("div", class_="desc") else "-"
        
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
            parsed = parse_anime_node(item)
            if parsed: data.append(parsed)
    return {"success": True, "results": data}
