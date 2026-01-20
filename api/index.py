from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper V5")

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

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API V5 - Dual Lang Schedule"}

# --- 1. JADWAL (SUPPORT INDO & INGGRIS) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False, "message": "Gagal fetch data"}
    
    schedule_data = {}
    
    # Mapping hari Indo & Inggris biar satu output standar
    day_mapping = {
        "senin": "Senin", "monday": "Senin",
        "selasa": "Selasa", "tuesday": "Selasa",
        "rabu": "Rabu", "wednesday": "Rabu",
        "kamis": "Kamis", "thursday": "Kamis",
        "jumat": "Jumat", "friday": "Jumat",
        "sabtu": "Sabtu", "saturday": "Sabtu",
        "minggu": "Minggu", "sunday": "Minggu"
    }

    # Cari container jadwal (biasanya ada di widget atau entry-content)
    # Kita scan semua tag H3, H4, atau DIV yang isinya nama hari
    all_headers = soup.find_all(["h3", "h4", "div", "span"])
    
    current_day = None
    
    for tag in all_headers:
        text = tag.get_text(strip=True).lower()
        
        # Cek apakah teks tag ini adalah nama hari (Indo/Inggris)
        if text in day_mapping:
            current_day = day_mapping[text] # Normalize jadi format Indo (Senin, Selasa...)
            if current_day not in schedule_data:
                schedule_data[current_day] = []
                
            # Logic: Ambil list anime di BAWAH header hari ini
            # Biasanya struktur: Header Hari -> Div/Ul List Anime
            
            # Coba cari sibling (saudara) setelahnya
            sibling = tag.find_next_sibling()
            
            # Kalau siblingnya bukan list, mungkin ada di parent-nya (struktur box)
            if not sibling or sibling.name not in ['div', 'ul']:
                 parent_box = tag.find_parent("div", class_="schedule-box")
                 if parent_box:
                     sibling = parent_box.find("div", class_="schedule-content") or parent_box.find("ul")

            if sibling:
                # Ambil semua item anime di dalam list tersebut
                anime_items = sibling.find_all("li") # Biasanya list item
                if not anime_items: 
                    anime_items = sibling.select(".animepost") # Atau div post
                
                for item in anime_items:
                    title_tag = item.find("a") or item.find("div", class_="title")
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        link = item.find("a")['href'] if item.find("a") else None
                        schedule_data[current_day].append({
                            "title": title,
                            "link": link
                        })

    return JSONResponse(content={"success": True, "data": schedule_data})

# --- 2. LATEST ANIME (SELECTOR LEBIH TAJAM) ---
@app.get("/api/latest")
def get_latest():
    """
    Ambil anime yang baru rilis episode barunya
    """
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False, "message": "Gagal fetch data"}
    
    data = []
    
    # Selector target: List item di dalam post-show atau ul generic
    # Kita cari elemen yang punya class 'animepost' atau 'post-article'
    posts = soup.select(".post-show li") or soup.select(".animepost") or soup.select("div.post-article")

    for post in posts:
        try:
            # Title
            title_tag = post.find("h2", class_="entry-title") or post.find("div", class_="title") or post.find("a", attrs={"title": True})
            if not title_tag: continue
            
            title = title_tag.get_text(strip=True)
            
            # Link
            link_tag = post.find("a")
            link = link_tag['href'] if link_tag else "#"
            
            # Thumbnail
            img_tag = post.find("img")
            thumb = img_tag['src'] if img_tag else None
            # Fix lazy load image (kadang src kosong, adanya data-src)
            if not thumb and img_tag and img_tag.get('data-src'):
                thumb = img_tag['data-src']
            
            # Episode Info
            ep_tag = post.find("span", class_="episode") or post.find("div", class_="dtla") or post.find("span", class_="author")
            episode = ep_tag.get_text(strip=True) if ep_tag else "New"
            
            # Posted By / Time (Optional)
            posted_tag = post.find("span", class_="date") or post.find("span", class_="year")
            posted = posted_tag.get_text(strip=True) if posted_tag else "-"

            data.append({
                "title": title,
                "episode": episode,
                "posted": posted,
                "thumbnail": thumb,
                "link": link
            })
        except Exception as e:
            continue
            
    return JSONResponse(content={"success": True, "data": data})

# --- 3. DETAIL (TETAP SEPERTI YANG BERHASIL KEMARIN) ---
@app.get("/api/detail")
def get_detail(url: str):
    soup = get_soup(url)
    if not soup: return {"success": False, "message": "Gagal load page"}
    
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
            for g in genre_container.find_all("a"):
                genres.append(g.get_text(strip=True))
        result['genres'] = genres
        
        img_tag = soup.find("div", class_="thumb").find("img")
        result['cover'] = img_tag['src'] if img_tag else None

        episodes = []
        ep_list = soup.select(".lstepsiode li") or soup.select(".eps_lst li")
        
        for li in ep_list:
            ep_num_tag = li.find("span", class_="epnum")
            link_tag = li.find("a")
            date_tag = li.find("span", class_="date")
            
            episodes.append({
                "number": ep_num_tag.get_text(strip=True) if ep_num_tag else "?",
                "title": link_tag.get_text(strip=True) if link_tag else "-",
                "url": link_tag['href'] if link_tag else "#",
                "date": date_tag.get_text(strip=True) if date_tag else "-"
            })
        result['episodes'] = episodes
        
        # Stream URL (Iframe)
        iframe = soup.find("iframe")
        result['stream_url'] = iframe['src'] if iframe else None

    except Exception as e:
         return {"success": False, "error": str(e)}

    return JSONResponse(content={"success": True, "result": result})

# --- 4. SEARCH (Tambahan biar lengkap) ---
@app.get("/api/search")
def search_anime(query: str):
    soup = get_soup(f"{BASE_URL}/?s={query}")
    if not soup: return {"success": False}
    data = []
    for item in soup.select(".animepost"):
        try:
            data.append({
                "title": item.find("div", class_="title").get_text(strip=True),
                "link": item.find("a")['href'],
                "cover": item.find("img")['src'],
                "rating": item.find("div", class_="score").get_text(strip=True) if item.find("div", class_="score") else "?"
            })
        except: continue
    return {"success": True, "results": data}
