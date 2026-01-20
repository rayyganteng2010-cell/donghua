from fastapi import FastAPI, HTTPException
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

def get_soup(url: str):
    try:
        session = requests.Session()
        req = session.get(url, headers=HEADERS, timeout=15)
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

# --- PARSER ITEM HELPER ---
def parse_anime_item(node):
    try:
        # 1. Title
        title_tag = node.find("div", class_="title") or node.find("a")
        if not title_tag: return None
        title = title_tag.get_text(strip=True)
        
        # 2. Link
        a_tag = node.find("a")
        link = a_tag['href'] if a_tag else "#"
        
        # 3. Image
        img_tag = node.find("img")
        thumb = None
        if img_tag:
            thumb = img_tag.get('src')
            if not thumb or "data:image" in thumb: 
                thumb = img_tag.get('data-src') or img_tag.get('srcset')
        
        # 4. Score
        score_tag = node.find("div", class_="score") or node.find("span", class_="score")
        score = score_tag.get_text(strip=True) if score_tag else "?"
        
        # 5. Synopsis (Usahakan cari text tersembunyi)
        # Class 'ttls' biasanya tooltip hover
        desc = "-"
        desc_tag = node.find("div", class_="ttls") or node.find("div", class_="desc")
        if desc_tag:
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
    return {"status": "Online", "msg": "Samehadaku API V7 - Schedule Fix"}

# --- LOGIC JADWAL BARU (Targeted Search) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False}
    
    # Template Output Inggris
    final_schedule = {
        "Monday": [], "Tuesday": [], "Wednesday": [], "Thursday": [], 
        "Friday": [], "Saturday": [], "Sunday": []
    }
    
    # Pasangan Nama Hari Indo -> Key Inggris
    # Kita akan cari satu per satu.
    day_targets = [
        ("Senin", "Monday"), ("Selasa", "Tuesday"), ("Rabu", "Wednesday"),
        ("Kamis", "Thursday"), ("Jumat", "Friday"), ("Sabtu", "Saturday"), 
        ("Minggu", "Sunday")
    ]

    for indo_day, eng_key in day_targets:
        # 1. Cari elemen header yang TULISANNYA nama hari (Case Insensitive)
        # Kita cari tag h3, h4, span, atau div
        day_header = soup.find(lambda tag: tag.name in ['h3', 'h4', 'div', 'span'] and tag.get_text(strip=True).lower() == indo_day.lower())
        
        if day_header:
            items_found = []
            
            # STRATEGI 1: Cari Parent Box (Container)
            # Biasanya Header dan List Anime dibungkus div yang sama (misal class="schedule-box")
            parent_box = day_header.find_parent("div", class_="schedule-box") or day_header.find_parent("div", class_="tab-pane")
            
            if parent_box:
                # Ambil semua animepost di dalam box ini
                raw_items = parent_box.select(".animepost") or parent_box.select("li")
                for item in raw_items:
                    parsed = parse_anime_item(item)
                    if parsed: items_found.append(parsed)
            
            # STRATEGI 2: Kalau ga punya parent khusus, ambil Sibling (Elemen sebelahnya)
            else:
                next_elem = day_header.find_next_sibling()
                # Cek apakah siblingnya adalah list atau wrapper anime
                if next_elem:
                     raw_items = next_elem.select(".animepost") or next_elem.find_all("li")
                     for item in raw_items:
                        parsed = parse_anime_item(item)
                        if parsed: items_found.append(parsed)

            # Masukkan ke dictionary final
            # Filter duplikat (kadang HTML ada item ganda)
            seen_titles = set()
            for item in items_found:
                if item['title'] not in seen_titles:
                    final_schedule[eng_key].append(item)
                    seen_titles.add(item['title'])

    return JSONResponse(content={"success": True, "data": final_schedule})


# --- LATEST (Tetap Pakai yang V6 karena sudah bagus) ---
@app.get("/api/latest")
def get_latest():
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False}
    data = []
    
    posts = soup.select(".post-show li") or soup.select(".animepost") or soup.select("div.post-article")
    for post in posts:
        parsed = parse_anime_item(post)
        if parsed:
            # Tambahan data khusus latest
            ep_tag = post.find("span", class_="episode") or post.find("div", class_="dtla")
            parsed['episode'] = ep_tag.get_text(strip=True) if ep_tag else "New"
            date_tag = post.find("span", class_="date") or post.find("span", class_="year")
            parsed['posted'] = date_tag.get_text(strip=True) if date_tag else "?"
            data.append(parsed)
            
    return JSONResponse(content={"success": True, "data": data})

# --- SEARCH ---
@app.get("/api/search")
def search_anime(query: str):
    soup = get_soup(f"{BASE_URL}/?s={query}")
    data = []
    if soup:
        items = soup.select(".animepost") or soup.select("div.relat article")
        for item in items:
            parsed = parse_anime_item(item)
            if parsed: data.append(parsed)
    return {"success": True, "results": data}

# --- DETAIL ---
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
