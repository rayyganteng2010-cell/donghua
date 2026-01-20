from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper V6")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8"
}

BASE_URL = "https://v1.samehadaku.how"

def get_soup(url: str):
    try:
        session = requests.Session()
        req = session.get(url, headers=HEADERS, timeout=15)
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

# --- FUNGSI BANTUAN PARSE ITEM (Biar Rapi & Lengkap) ---
def parse_anime_item(node):
    """Mengambil data detail dari sebuah elemen anime (thumbnail, sinopsis, dll)"""
    try:
        # 1. Title
        title_tag = node.find("div", class_="title") or node.find("a")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"
        
        # 2. Link
        a_tag = node.find("a")
        link = a_tag['href'] if a_tag else "#"
        
        # 3. Image (Cek Lazyload data-src juga)
        img_tag = node.find("img")
        thumb = None
        if img_tag:
            thumb = img_tag.get('src')
            if not thumb or "data:image" in thumb: # Handle lazy load
                thumb = img_tag.get('data-src') or img_tag.get('srcset')

        # 4. Score / Rating
        score_tag = node.find("div", class_="score") or node.find("span", class_="score")
        score = score_tag.get_text(strip=True) if score_tag else "?"
        
        # 5. Sinopsis / Deskripsi
        # (Biasanya di samehadaku ada di class 'ttls' atau hidden 'desc')
        desc = "-"
        desc_tag = node.find("div", class_="ttls") or node.find("div", class_="desc") or node.find("p")
        if desc_tag:
            # Bersihkan text dari newlines aneh
            desc = desc_tag.get_text(strip=True).replace("\n", " ")
        
        # 6. Genres
        genres = []
        genre_tags = node.select(".genres a") or node.select(".genre a")
        genres = [g.get_text(strip=True) for g in genre_tags]

        return {
            "title": title,
            "link": link,
            "thumbnail": thumb,
            "score": score,
            "synopsis": desc,
            "genres": genres
        }
    except:
        return None

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API V6 - Schedule English & Complete"}

# --- 1. JADWAL (ENG & LENGKAP) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False, "message": "Gagal fetch data"}
    
    # Init structure Hari Inggris
    schedule_data = {
        "Monday": [], "Tuesday": [], "Wednesday": [], "Thursday": [], 
        "Friday": [], "Saturday": [], "Sunday": []
    }
    
    # Mapping dari Indo -> Inggris
    day_map_en = {
        "senin": "Monday", "monday": "Monday",
        "selasa": "Tuesday", "tuesday": "Tuesday",
        "rabu": "Wednesday", "wednesday": "Wednesday",
        "kamis": "Thursday", "thursday": "Thursday",
        "jumat": "Friday", "friday": "Friday",
        "sabtu": "Saturday", "saturday": "Saturday",
        "minggu": "Sunday", "sunday": "Sunday"
    }

    # Cari area konten utama biar gak nyasar ke sidebar
    content_area = soup.find("div", class_="entry-content") or soup.find("div", class_="schedule") or soup
    
    # Ambil semua kemungkinan header hari
    headers = content_area.find_all(["h3", "h4", "div", "span"])
    
    current_day_en = None
    
    for tag in headers:
        text_clean = tag.get_text(strip=True).lower()
        
        # Cek apakah teks elemen ini adalah Nama Hari
        found_day = None
        for k, v in day_map_en.items():
            if k in text_clean:
                found_day = v
                break
        
        if found_day:
            current_day_en = found_day
            
            # --- LOGIC RAKUS (Greedy Fetch) ---
            # Kita cari elemen sibling SETELAH header hari ini, sampai ketemu header hari berikutnya.
            # Ini memastikan kalau ada banyak anime, semuanya keambil.
            
            curr = tag.find_next_sibling()
            
            while curr:
                # Stop kalau ketemu Header Hari Berikutnya (misal ketemu "Selasa" pas lagi scan "Senin")
                if curr.name in ["h3", "h4"] and any(d in curr.get_text(strip=True).lower() for d in day_map_en):
                    break
                
                items = []
                
                # Tipe 1: Grid View (Ada gambar & sinopsis - class animepost)
                if curr.name == "div" and ("animepost" in curr.get("class", []) or curr.find("div", class_="animepost")):
                    posts = curr.select(".animepost") if "animepost" not in curr.get("class", []) else [curr]
                    for post in posts:
                        parsed = parse_anime_item(post)
                        if parsed: items.append(parsed)

                # Tipe 2: List View (ul/li - biasanya cuma link text)
                elif curr.name == "ul":
                    for li in curr.find_all("li"):
                        parsed = parse_anime_item(li)
                        if parsed: items.append(parsed)

                # Tipe 3: Div Wrapper Biasa
                elif curr.name == "div":
                    # Cek dalemnya ada list atau animepost
                    sub_posts = curr.select(".animepost")
                    if sub_posts:
                        for p in sub_posts: 
                            parsed = parse_anime_item(p)
                            if parsed: items.append(parsed)
                    else:
                        # Coba cari list biasa
                        sub_lis = curr.select("li")
                        for l in sub_lis:
                            parsed = parse_anime_item(l)
                            if parsed: items.append(parsed)

                # Masukkan ke dictionary jadwal
                for item in items:
                    # Filter duplikat (kadang ada item double di HTML)
                    if not any(x['title'] == item['title'] for x in schedule_data[current_day_en]):
                        schedule_data[current_day_en].append(item)
                
                # Lanjut ke elemen html berikutnya
                curr = curr.find_next_sibling()

    return JSONResponse(content={"success": True, "data": schedule_data})

# --- 2. LATEST (SELECTOR DIPERTAJAM DARI VERSI SEBELUMNYA) ---
@app.get("/api/latest")
def get_latest():
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False}
    
    data = []
    # Selector target: List item di dalam post-show atau animepost umum
    posts = soup.select(".post-show li") or soup.select(".animepost") or soup.select("div.post-article")

    for post in posts:
        parsed = parse_anime_item(post) # Pakai fungsi helper yang sama biar konsisten
        if parsed:
            # Tambahan khusus latest: Info Episode & Posted Time
            ep_tag = post.find("span", class_="episode") or post.find("div", class_="dtla")
            parsed['episode'] = ep_tag.get_text(strip=True) if ep_tag else "New"
            
            date_tag = post.find("span", class_="date") or post.find("span", class_="year")
            parsed['posted'] = date_tag.get_text(strip=True) if date_tag else "?"
            
            data.append(parsed)
            
    return JSONResponse(content={"success": True, "data": data})

# --- 3. DETAIL (TETAP SAMA) ---
@app.get("/api/detail")
def get_detail(url: str):
    soup = get_soup(url)
    if not soup: return {"success": False}
    
    result = {}
    try:
        result['title'] = soup.find("h1", class_="entry-title").get_text(strip=True)
        
        rating_tag = soup.find("span", class_="rating") or soup.find("div", class_="score")
        result['rating'] = rating_tag.get_text(strip=True) if rating_tag else "N/A"
        
        desc_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        result['description'] = desc_div.get_text(strip=True) if desc_div else "-"
        
        genres = []
        genre_container = soup.find("div", class_="genre-info") or soup.select_one(".genre")
        if genre_container:
            genres = [g.get_text(strip=True) for g in genre_container.find_all("a")]
        result['genres'] = genres
        
        img_tag = soup.find("div", class_="thumb").find("img")
        result['cover'] = img_tag['src'] if img_tag else None

        episodes = []
        ep_list = soup.select(".lstepsiode li") or soup.select(".eps_lst li")
        
        for li in ep_list:
            ep_num = li.find("span", class_="epnum")
            link_tag = li.find("a")
            date_tag = li.find("span", class_="date")
            episodes.append({
                "number": ep_num.get_text(strip=True) if ep_num else "?",
                "title": link_tag.get_text(strip=True) if link_tag else "-",
                "url": link_tag['href'] if link_tag else "#",
                "date": date_tag.get_text(strip=True) if date_tag else "-"
            })
        result['episodes'] = episodes
        
        iframe = soup.find("iframe")
        result['stream_url'] = iframe['src'] if iframe else None

    except Exception as e:
         return {"success": False, "error": str(e)}

    return JSONResponse(content={"success": True, "result": result})

# --- 4. SEARCH ---
@app.get("/api/search")
def search_anime(query: str):
    soup = get_soup(f"{BASE_URL}/?s={query}")
    data = []
    if soup:
        items = soup.select(".animepost")
        for item in items:
            parsed = parse_anime_item(item)
            if parsed: data.append(parsed)
    return {"success": True, "results": data}
