from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="Samehadaku Scraper API", docs_url="/", redoc_url=None)

# Headers biar gak dikira bot jahat
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

BASE_URL = "https://v1.samehadaku.how"

def get_soup(url):
    try:
        req = requests.get(url, headers=HEADERS)
        req.raise_for_status()
        return BeautifulSoup(req.text, "lxml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scraping: {str(e)}")

@app.get("/api/anime-list")
def get_anime_list():
    """Scrape daftar anime: Thumbnail, Rating, Title"""
    url = f"{BASE_URL}/daftar-anime-2/"
    soup = get_soup(url)
    
    data = []
    # NOTE: Ganti selector '.animepost' sesuai class asli di web jika berubah
    anime_nodes = soup.find_all("div", class_="animepost") 
    
    for node in anime_nodes:
        try:
            title = node.find("div", class_="title").get_text(strip=True)
            # Ambil rating
            rating = node.find("div", class_="score").get_text(strip=True) if node.find("div", class_="score") else "N/A"
            # Ambil image
            img_tag = node.find("img")
            thumb = img_tag['src'] if img_tag else None
            # Ambil link detail
            link = node.find("a")['href']
            
            data.append({
                "title": title,
                "rating": rating,
                "thumbnail": thumb,
                "link": link
            })
        except AttributeError:
            continue
            
    return JSONResponse(content={"status": "success", "data": data})

@app.get("/api/schedule")
def get_schedule():
    """Scrape jadwal rilis (Senin-Minggu)"""
    url = f"{BASE_URL}/jadwal-rilis/"
    soup = get_soup(url)
    
    schedule = {}
    # Biasanya struktur jadwal itu per kotak hari
    # Cari container jadwal, misal class 'schedule-section' atau loop div
    schedule_nodes = soup.find_all("div", class_="schedule-box") # Sesuaikan selector
    
    if not schedule_nodes:
        # Fallback logic kalo structure beda, misal pake tab
        schedule_nodes = soup.select(".tab-pane") # Contoh selector tab bootstrap

    for node in schedule_nodes:
        day_name = node.find("h3").get_text(strip=True) if node.find("h3") else "Unknown"
        anime_list = []
        for anime in node.find_all("li"): # Asumsi list item
            title = anime.get_text(strip=True)
            anime_list.append(title)
        
        schedule[day_name] = anime_list

    return JSONResponse(content={"status": "success", "data": schedule})

@app.get("/api/latest")
def get_latest_anime():
    """Scrape anime terbaru"""
    url = f"{BASE_URL}/anime-terbaru/"
    soup = get_soup(url)
    
    data = []
    # Biasanya di homepage atau page terbaru strukturnya mirip 'post-article'
    posts = soup.find_all("div", class_="post-article") 
    
    for post in posts:
        try:
            title = post.find("h3", class_="title").get_text(strip=True)
            episode = post.find("span", class_="episode").get_text(strip=True)
            thumb = post.find("img")['src']
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
def get_anime_detail(url: str):
    """
    Scrape detail anime.
    Param url: Link full anime (e.g., https://v1.samehadaku.how/anime/compass...)
    """
    soup = get_soup(url)
    
    # 1. Info Dasar
    info_div = soup.find("div", class_="infox") # Class umum info
    synopsis = soup.find("div", class_="desc").get_text(strip=True) if soup.find("div", class_="desc") else "No desc"
    
    # 2. Ambil Video/Server (Disini tricky, biasanya iframe)
    # Kita ambil src iframe nya aja
    video_servers = []
    server_nodes = soup.select("#server-list li") # Contoh ID server list
    
    for server in server_nodes:
        server_name = server.get_text(strip=True)
        # Link video mungkin ada di atribut data-video atau dalam tag a
        video_url = server.get("data-video") 
        if video_url:
             video_servers.append({"server": server_name, "url": video_url})

    # 3. List Episode
    episodes = []
    ep_list = soup.find("div", class_="lstepsiode") # Class list episode
    if ep_list:
        for li in ep_list.find_all("li"):
            ep_num = li.find("span", class_="epnum").get_text(strip=True)
            ep_link = li.find("a")['href']
            episodes.append({"episode": ep_num, "link": ep_link})

    result = {
        "title": soup.find("h1", class_="entry-title").get_text(strip=True),
        "synopsis": synopsis,
        "video_servers": video_servers, # Ini mungkin perlu decrypt kalau diprotect
        "episodes": episodes
    }
    
    return JSONResponse(content={"status": "success", "data": result})

