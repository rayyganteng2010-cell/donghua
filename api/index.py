from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="Samehadaku API Final")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/"
}

BASE_URL = "https://v1.samehadaku.how"

def get_soup(url: str):
    try:
        req = requests.get(url, headers=HEADERS, timeout=15)
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API Ready"}

# --- 1. SEARCH ANIME (Sesuai Request JSON Lu) ---
@app.get("/api/search")
def search_anime(query: str):
    """
    Output sesuai request: Title, Rating, Desc, Type, Status, Genres
    """
    url = f"{BASE_URL}/?s={query}"
    soup = get_soup(url)
    if not soup: return {"success": False, "message": "Gagal fetch data"}

    data = []
    # Selector untuk list hasil search
    items = soup.select(".animepost") or soup.select("div.relat article")

    for item in items:
        try:
            # Title & Link
            title_tag = item.find("div", class_="title") or item.find("h3")
            title = title_tag.get_text(strip=True)
            link = item.find("a")['href']
            
            # Thumbnail
            img_tag = item.find("img")
            thumb = img_tag['src'] if img_tag else None
            
            # Rating
            score = item.find("div", class_="score")
            rating = score.get_text(strip=True) if score else "N/A"
            
            # Meta Info (Type, Status, Genres)
            # Biasanya ada di dalam tooltip atau div hidden content
            type_anime = "Unknown"
            status_anime = "Unknown"
            genres_list = []
            desc = ""

            # Coba ambil data dari elemen 'hint' atau 'metadata'
            # Di Samehadaku, kadang info ini ada di dalam div.type / div.status
            content_div = item.find("div", class_="content") or item.find("div", class_="data")
            
            if content_div:
                type_tag = content_div.find("div", class_="type")
                if type_tag: type_anime = type_tag.get_text(strip=True)
                
                status_tag = content_div.find("div", class_="status")
                if status_tag: status_anime = status_tag.get_text(strip=True)

            # Genres (kadang ada di list search, kadang enggak. Kalau ga ada kita skip)
            genre_tags = item.select(".genres a")
            genres_list = [g.get_text(strip=True) for g in genre_tags]

            # Description (Excerpt)
            desc_tag = item.find("div", class_="ttls") or item.find("div", class_="desc")
            if desc_tag:
                desc = desc_tag.get_text(strip=True)

            data.append({
                "title": title,
                "rating": rating,
                "description": desc,
                "type": type_anime,
                "status": status_anime,
                "genres": genres_list,
                "cover": thumb,
                "url": link
            })
        except Exception:
            continue

    return JSONResponse(content={"success": True, "results": data})


# --- 2. DETAIL ANIME (Sesuai Request JSON Lu) ---
@app.get("/api/detail")
def get_detail(url: str):
    """
    Output Lengkap: Title, Rating, Desc, Genres, Cover, Episodes (Date, Url, Title)
    """
    soup = get_soup(url)
    if not soup: return {"success": False, "message": "Gagal load page"}
    
    result = {}
    try:
        # Header Info
        result['title'] = soup.find("h1", class_="entry-title").get_text(strip=True)
        
        # Rating
        rating_tag = soup.find("span", class_="rating") or soup.find("div", class_="score")
        result['rating'] = rating_tag.get_text(strip=True) if rating_tag else "N/A"
        
        # Description (Pembersihan text)
        desc_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        result['description'] = desc_div.get_text(strip=True) if desc_div else "-"
        
        # Genres
        genres = []
        genre_container = soup.find("div", class_="genre-info") or soup.select_one(".genre")
        if genre_container:
            for g in genre_container.find_all("a"):
                genres.append(g.get_text(strip=True))
        result['genres'] = genres
        
        # Cover Image
        img_tag = soup.find("div", class_="thumb").find("img")
        result['cover'] = img_tag['src'] if img_tag else None

        # Episode List (Dengan Tanggal)
        episodes = []
        # Selector list episode
        ep_list = soup.select(".lstepsiode li") or soup.select(".eps_lst li")
        
        for li in ep_list:
            # Ambil Judul / Nomor
            ep_num_tag = li.find("span", class_="epnum")
            ep_title_tag = li.find("span", class_="epl-title") # Kadang ada judul per episode
            link_tag = li.find("a")
            
            # Ambil Tanggal
            date_tag = li.find("span", class_="date")
            date_text = date_tag.get_text(strip=True) if date_tag else "Unknown"
            
            title_text = link_tag.get_text(strip=True) # Default title dari link
            if ep_title_tag:
                 title_text = ep_title_tag.get_text(strip=True)

            episodes.append({
                "number": ep_num_tag.get_text(strip=True) if ep_num_tag else "?",
                "title": title_text,
                "url": link_tag['href'],
                "date": date_text
            })
            
        result['episodes'] = episodes
        
        # (Optional) Video Stream Link extract
        # Lu bilang videonya nyatu html, kita ambil iframe-nya
        iframe = soup.find("iframe")
        result['stream_url'] = iframe['src'] if iframe else None

    except Exception as e:
         return {"success": False, "error": str(e)}

    return JSONResponse(content={"success": True, "result": result})


# --- 3. ANIME LIST (DEFAULT) ---
@app.get("/api/anime-list")
def get_anime_list():
    soup = get_soup(f"{BASE_URL}/daftar-anime-2/")
    data = []
    items = soup.select(".animepost")
    for item in items:
        try:
            title = item.find("div", class_="title").get_text(strip=True)
            link = item.find("a")['href']
            img = item.find("img")['src']
            rating = item.find("div", class_="score").get_text(strip=True) if item.find("div", class_="score") else "?"
            data.append({"title": title, "rating": rating, "thumbnail": img, "link": link})
        except: continue
    return {"success": True, "data": data}

