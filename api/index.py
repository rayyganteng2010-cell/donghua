from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="Samehadaku Scraper API")

# Headers wajib biar gak diblokir sebagai bot
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/"
}

BASE_URL = "https://v1.samehadaku.how"

def get_soup(url: str):
    try:
        req = requests.get(url, headers=HEADERS, timeout=10)
        req.raise_for_status()
        # PENTING: Pakai 'html.parser' jangan 'lxml' buat Vercel
        return BeautifulSoup(req.text, "html.parser")
    except requests.exceptions.RequestException as e:
        print(f"Connection Error: {e}")
        raise HTTPException(status_code=500, detail="Gagal connect ke Samehadaku")
    except Exception as e:
        print(f"Parser Error: {e}")
        raise HTTPException(status_code=500, detail="Error parsing data")

@app.get("/")
def home():
    return {
        "status": "Running",
        "message": "API Samehadaku Siap. Gunakan endpoints di bawah.",
        "endpoints": {
            "List Anime": "/api/anime-list",
            "Jadwal": "/api/schedule",
            "Terbaru": "/api/latest",
            "Detail": "/api/detail?url=LINK_ANIME"
        }
    }

@app.get("/api/anime-list")
def get_anime_list():
    """Scrape halaman Daftar Anime"""
    url = f"{BASE_URL}/daftar-anime-2/"
    soup = get_soup(url)
    data = []
    
    # Selector umum daftar anime (biasanya div dengan class animepost)
    items = soup.find_all("div", class_="animepost")
    
    for item in items:
        try:
            # Ambil Title
            title_tag = item.find("div", class_="title")
            title = title_tag.get_text(strip=True) if title_tag else "No Title"
            
            # Ambil Link
            link_tag = item.find("a")
            link = link_tag['href'] if link_tag else "#"
            
            # Ambil Thumbnail (Handling lazy load biasanya ada di atribut src)
            img_tag = item.find("img")
            thumb = img_tag.get('src') if img_tag else None
            
            # Ambil Rating
            rating_tag = item.find("div", class_="score")
            rating = rating_tag.get_text(strip=True) if rating_tag else "N/A"
            
            data.append({
                "title": title,
                "thumbnail": thumb,
                "rating": rating,
                "link": link
            })
        except Exception:
            continue # Skip item yang error strukturnya
            
    return JSONResponse(content={"status": "success", "total": len(data), "data": data})

@app.get("/api/schedule")
def get_schedule():
    """Scrape halaman Jadwal Rilis (Logic Parsir Hari)"""
    url = f"{BASE_URL}/jadwal-rilis/"
    soup = get_soup(url)
    
    schedule_data = {}
    
    # Cari container utama jadwal
    # Biasanya jadwal dibungkus dalam tab-pane atau widget
    # Kita cari parent-nya dulu
    schedule_area = soup.find("div", class_="schedule") 
    if not schedule_area:
        # Fallback kalau class beda, coba cari container artikel biasa
        schedule_area = soup.find("div", class_="entry-content")
    
    if schedule_area:
        # Logic: Cari nama hari (H3/H4) dan ambil list anime di bawahnya
        current_day = "Unknown"
        
        # Iterasi semua elemen di dalam content
        for element in schedule_area.find_all(["h3", "h4", "div", "ul"]):
            # Jika ketemu Header Hari (Senin, Selasa, dst)
            if element.name in ["h3", "h4"]:
                day_text = element.get_text(strip=True)
                if any(x in day_text.lower() for x in ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]):
                    current_day = day_text
                    schedule_data[current_day] = []
            
            # Jika ketemu List Anime
            elif element.name == "div" and "animepost" in element.get("class", []):
                # Ini kalau formatnya div box
                title = element.find("div", class_="title").get_text(strip=True)
                schedule_data[current_day].append(title)
            elif element.name == "ul" and current_day != "Unknown":
                # Ini kalau formatnya list biasa (li)
                for li in element.find_all("li"):
                    schedule_data[current_day].append(li.get_text(strip=True))

    return JSONResponse(content={"status": "success", "data": schedule_data})

@app.get("/api/latest")
def get_latest():
    """Scrape Anime Terbaru"""
    url = f"{BASE_URL}/anime-terbaru/"
    soup = get_soup(url)
    data = []
    
    # Selector untuk post terbaru
    posts = soup.find_all("div", class_="post-article")
    
    for post in posts:
        try:
            title = post.find("h3", class_="title").get_text(strip=True)
            
            # Info Episode & Posted By
            meta = post.find("div", class_="meta")
            episode = meta.find("span", class_="episode").get_text(strip=True) if meta else "?"
            
            img_tag = post.find("img")
            thumb = img_tag.get('src') if img_tag else None
            
            link = post.find("a")['href']
            
            data.append({
                "title": title,
                "episode": episode,
                "thumbnail": thumb,
                "link": link
            })
        except:
            continue
            
    return JSONResponse(content={"status": "success", "data": data})

@app.get("/api/detail")
def get_detail(url: str = Query(..., description="Full URL anime")):
    """
    Scrape Detail Anime + Video
    Contoh URL: https://v1.samehadaku.how/anime/compass2-0-animation-project/
    """
    if not url.startswith("http"):
        return JSONResponse(status_code=400, content={"error": "URL invalid"})
        
    soup = get_soup(url)
    result = {}
    
    try:
        # 1. Judul & Sinopsis
        result['title'] = soup.find("h1", class_="entry-title").get_text(strip=True)
        
        synopsis_div = soup.find("div", class_="desc")
        result['synopsis'] = synopsis_div.get_text(strip=True) if synopsis_div else "No Synopsis"
        
        # 2. Thumbnail Detail
        img_detail = soup.find("div", class_="thumb").find("img")
        result['thumbnail'] = img_detail.get("src") if img_detail else None

        # 3. List Episode (Scroll list)
        episodes = []
        ep_list_div = soup.find("div", class_="lstepsiode")
        if ep_list_div:
            for li in ep_list_div.find_all("li"):
                ep_num = li.find("span", class_="epnum").get_text(strip=True)
                ep_link = li.find("a")['href']
                episodes.append({"episode": ep_num, "link": ep_link})
        result['episode_list'] = episodes

        # 4. Video Server / Streaming (Bagian Paling Tricky)
        # Biasanya ada di dalam div id="server-list" atau select option
        video_data = []
        
        # Coba cari iframe langsung (cara kasar)
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            src = iframe.get("src")
            if src and "samehadaku" not in src: # Filter iklan internal
                video_data.append({"type": "iframe", "url": src})
        
        # Coba cari list server (tab style)
        server_tabs = soup.select("#server-list ul li")
        for server in server_tabs:
            srv_name = server.get_text(strip=True)
            # Kadang url ada di attribute 'data-video'
            srv_url = server.get("data-video")
            if srv_url:
                video_data.append({"server": srv_name, "url": srv_url})
                
        result['videos'] = video_data

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error parsing detail: {str(e)}"})
        
    return JSONResponse(content={"status": "success", "data": result})
