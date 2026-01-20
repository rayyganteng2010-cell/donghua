from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper Final")

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

# --- HELPER KHUSUS BUAT ITEM JADWAL ---
def parse_schedule_item(node):
    """
    Mengambil data detail sesuai request JSON:
    title, url, image, type, score, genre (string), time
    """
    try:
        # 1. Title & URL
        a_tag = node.find("a")
        if not a_tag: return None
        
        title = a_tag.get_text(strip=True)
        # Fallback title jika kosong
        if not title:
            title_div = node.find("div", class_="title")
            if title_div: title = title_div.get_text(strip=True)
            
        url = a_tag['href']

        # 2. Image (Handle Lazy Load)
        img_tag = node.find("img")
        image = "https://dummyimage.com/300x400/000/fff&text=No+Image"
        if img_tag:
            # Cek src, data-src, atau srcset
            image = img_tag.get('src')
            if not image or "data:image" in image:
                image = img_tag.get('data-src') or img_tag.get('srcset') or image
            # Bersihkan URL (kadang ada query string aneh)
            if image and "?" in image:
                image = image.split("?")[0]

        # 3. Score
        score = "N/A"
        score_tag = node.find("div", class_="score") or node.find("span", class_="score")
        if score_tag:
            score = score_tag.get_text(strip=True)

        # 4. Genre (Harus String: "Action, Adventure")
        # Di halaman jadwal, genre seringkali tidak ditampilkan langsung.
        # Kita coba cari di dalam tooltip atau hidden div, kalau gak ada kosongin dulu.
        genres_list = []
        genre_tags = node.select(".genres a") or node.select(".genre a")
        if genre_tags:
            genres_list = [g.get_text(strip=True) for g in genre_tags]
        genre_str = ", ".join(genres_list) if genres_list else "-"

        # 5. Type (TV/Movie)
        # Biasanya ada di class 'type' atau meta
        anime_type = "TV" # Default Samehadaku kebanyakan TV
        type_tag = node.find("div", class_="type")
        if type_tag:
            anime_type = type_tag.get_text(strip=True)

        # 6. Time (Jam Tayang)
        # Biasanya ada di span class 'time' atau 'date' di jadwal
        time_release = "??"
        time_tag = node.find("span", class_="time") or node.find("div", class_="btime")
        if time_tag:
            time_release = time_tag.get_text(strip=True)

        return {
            "title": title,
            "url": url,
            "image": image,
            "type": anime_type,
            "score": score,
            "genre": genre_str,
            "time": time_release
        }
    except Exception as e:
        return None

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API Final - JSON Structure Fixed"}

# --- 1. JADWAL (STRUKTUR JSON SESUAI REQUEST) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False, "message": "Gagal fetch data"}
    
    # Mapping Hari Inggris (Key) ke Indo (Header di Web)
    day_mapping = {
        "monday": "Senin",
        "tuesday": "Selasa",
        "wednesday": "Rabu",
        "thursday": "Kamis",
        "friday": "Jumat",
        "saturday": "Sabtu",
        "sunday": "Minggu"
    }

    final_data = {}

    # Cari container utama konten
    content_area = soup.find("div", class_="entry-content") or soup.find("div", class_="schedule") or soup

    for eng_key, indo_name in day_mapping.items():
        # Structure default per hari
        day_data = {
            "dayName": indo_name,
            "totalItems": 0,
            "items": []
        }

        # LOGIC PENCARIAN:
        # 1. Cari elemen header yang tulisannya = indo_name (Contoh: "Senin")
        header = content_area.find(lambda tag: tag.name in ['h3', 'h4', 'div', 'span'] and indo_name.lower() == tag.get_text(strip=True).lower())
        
        if header:
            # 2. Cari Container Anime untuk Header ini
            # Biasanya anime dibungkus di div setelah header, atau di dalam parent yang sama
            
            # Coba ambil sibling elemen setelah header (biasanya div berisi list anime)
            anime_container = header.find_next_sibling("div")
            
            # Jika siblingnya bukan container anime, coba cari parent schedule-box
            if not anime_container or ("animepost" not in str(anime_container) and "ul" not in str(anime_container)):
                parent_box = header.find_parent("div", class_="schedule-box")
                if parent_box:
                    anime_container = parent_box
            
            items_found = []
            if anime_container:
                # Ambil semua item anime (bisa format grid .animepost atau list li)
                raw_items = anime_container.select(".animepost") or anime_container.select("li")
                
                for raw in raw_items:
                    # Validasi: Item harus punya Link
                    if raw.find("a"): 
                        parsed = parse_schedule_item(raw)
                        # Filter duplikat judul
                        if parsed and parsed['title'] not in [x['title'] for x in items_found]:
                            items_found.append(parsed)
            
            day_data["items"] = items_found
            day_data["totalItems"] = len(items_found)
        
        # Masukkan ke dictionary utama dengan key lowercase (monday, tuesday...)
        final_data[eng_key] = day_data

    return JSONResponse(content={"success": True, "data": final_data})


# --- 2. LATEST (SELECTOR DIPERBAIKI) ---
@app.get("/api/latest")
def get_latest():
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False}
    
    data = []
    # Selector gabungan biar dapet semua format
    posts = soup.select(".post-show li") or soup.select(".animepost") or soup.select("div.post-article")

    for post in posts:
        # Pake parser yang sama tapi sesuaikan field
        # Kita pakai manual extract disini biar fleksibel buat endpoint latest
        try:
            title_tag = post.find("h2", class_="entry-title") or post.find("div", class_="title") or post.find("a")
            if not title_tag: continue
            
            title = title_tag.get_text(strip=True)
            link = post.find("a")['href']
            
            img_tag = post.find("img")
            thumb = None
            if img_tag:
                thumb = img_tag.get('src')
                if not thumb or "data:image" in thumb:
                    thumb = img_tag.get('data-src')

            ep_tag = post.find("span", class_="episode") or post.find("div", class_="dtla")
            episode = ep_tag.get_text(strip=True) if ep_tag else "New"
            
            date_tag = post.find("span", class_="date") or post.find("span", class_="year")
            posted = date_tag.get_text(strip=True) if date_tag else "?"

            data.append({
                "title": title,
                "link": link,
                "thumbnail": thumb,
                "episode": episode,
                "posted": posted
            })
        except:
            continue
            
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
            try:
                data.append({
                    "title": item.find("div", class_="title").get_text(strip=True),
                    "url": item.find("a")['href'],
                    "image": item.find("img")['src'],
                    "score": item.find("div", class_="score").get_text(strip=True)
                })
            except: continue
    return {"success": True, "results": data}
