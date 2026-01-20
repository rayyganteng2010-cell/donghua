from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku API V15 - All In One")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
}

BASE_URL = "https://v1.samehadaku.how"

# --- HELPERS ---

def get_soup(url: str):
    try:
        session = requests.Session()
        req = session.get(url, headers=HEADERS, timeout=20)
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def extract_id(url):
    """Ambil slug terakhir dari URL"""
    if not url: return ""
    return url.strip("/").split("/")[-1]

def extract_poster(node):
    img = node.find("img")
    if not img: return "https://dummyimage.com/300x400/000/fff&text=No+Image"
    poster = img.get('src')
    if not poster or "data:image" in poster:
        poster = img.get('data-src') or img.get('srcset') or poster
    return poster.split("?")[0] if poster else ""

def parse_genre_list(node):
    genres = []
    # Support selector list page (.genres) dan detail page (.genre-info)
    links = node.select(".genres a") or node.select(".genre-info a") or node.select(".genre a")
    for g in links:
        g_id = extract_id(g['href'])
        genres.append({
            "title": g.get_text(strip=True),
            "genreId": g_id,
            "href": f"/anime/samehadaku/genres/{g_id}",
            "samehadakuUrl": g['href']
        })
    return genres

def get_pagination(soup, current_page):
    pagination = soup.find("div", class_="pagination")
    if not pagination: return None
    
    page_links = pagination.find_all("a", class_="page-numbers")
    total_pages = 1
    if page_links:
        nums = [int(p.get_text(strip=True)) for p in page_links if p.get_text(strip=True).isdigit()]
        if nums: total_pages = max(nums)
    
    has_next = bool(pagination.find("a", class_="next"))
    has_prev = bool(pagination.find("a", class_="prev"))
    
    return {
        "currentPage": current_page,
        "hasPrevPage": has_prev,
        "prevPage": current_page - 1 if has_prev else None,
        "hasNextPage": has_next,
        "nextPage": current_page + 1 if has_next else None,
        "totalPages": total_pages
    }

def parse_anime_item_standard(node):
    """Helper untuk list anime umum (Search, Schedule, Ongoing)"""
    try:
        a_tag = node.find("a")
        if not a_tag: return None
        
        real_url = a_tag['href']
        anime_id = extract_id(real_url)
        title = node.find("div", class_="title").get_text(strip=True) if node.find("div", class_="title") else a_tag.get("title")
        
        # Tooltip Mining (Buat data yg hidden)
        score = "?"
        type_anime = "TV"
        
        # Cek hidden tooltip
        tooltip = node.find("div", class_="ttls") or node.find("div", class_="dtla") or node.find("div", class_="entry-content")
        if tooltip:
            text = tooltip.get_text(" | ", strip=True)
            m_score = re.search(r'(?:Skor|Score)\s*:\s*([\d\.]+)', text, re.I)
            if m_score: score = m_score.group(1)
            
            # Type kadang ada di type tag atau tooltip
            m_type = re.search(r'(?:Type|Tipe)\s*:\s*(\w+)', text, re.I)
            if m_type: type_anime = m_type.group(1)
        
        # Fallback cari tag visual
        if score == "?":
            sc_tag = node.find("div", class_="score")
            if sc_tag: score = sc_tag.get_text(strip=True)
            
        tp_tag = node.find("div", class_="type")
        if tp_tag: type_anime = tp_tag.get_text(strip=True)

        return {
            "title": title,
            "poster": extract_poster(node),
            "score": score,
            "type": type_anime,
            "animeId": anime_id,
            "href": f"/anime/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url,
            "genreList": parse_genre_list(node)
        }
    except: return None

@app.get("/")
def home():
    return {"message": "Samehadaku API V15 - All Endpoints Included"}

# ==========================================
# 1. SEARCH ENDPOINT (YANG HILANG TADI)
# ==========================================
@app.get("/anime/samehadaku/search")
def search_anime(query: str, page: int = 1):
    # Search query
    url = f"{BASE_URL}/page/{page}/?s={query}"
    if page == 1: url = f"{BASE_URL}/?s={query}"
    
    soup = get_soup(url)
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    results = []
    nodes = soup.select(".animepost")
    for node in nodes:
        item = parse_anime_item_standard(node)
        if item: results.append(item)
            
    return JSONResponse({
        "status": "success",
        "data": { "animeList": results },
        "pagination": get_pagination(soup, page)
    })

# ==========================================
# 2. SCHEDULE ENDPOINT (LOGIC V11 DIKEMBALIKAN)
# ==========================================
@app.get("/anime/samehadaku/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    # List Hari Urut
    day_mapping = [
        ("Monday", "Senin"), ("Tuesday", "Selasa"), ("Wednesday", "Rabu"),
        ("Thursday", "Kamis"), ("Friday", "Jumat"), ("Saturday", "Sabtu"), ("Sunday", "Minggu")
    ]
    days_result = []
    
    content = soup.find("div", class_="entry-content") or soup.find("main") or soup

    for eng_day, indo_day in day_mapping:
        anime_list = []
        # Cari Header Hari
        header = content.find(lambda tag: tag.name in ['h3', 'h4', 'div', 'span'] and indo_day.lower() == tag.get_text(strip=True).lower())
        
        if header:
            # Cari Container Anime (Next Sibling Logic V11)
            curr = header.find_next_sibling()
            limit = 0
            while curr and limit < 4:
                if ("animepost" in str(curr)) or (curr.name == "ul"):
                    raw_items = curr.select(".animepost") or curr.select("li")
                    for item in raw_items:
                        # Parse khusus schedule (butuh estimation time dari tooltip)
                        data = parse_anime_item_standard(item)
                        if data:
                            # Tambahin field estimation khusus schedule
                            estimation = "Update"
                            tooltip = item.find("div", class_="ttls") or item.find("div", class_="dtla")
                            if tooltip:
                                text = tooltip.get_text(" | ", strip=True)
                                m_time = re.search(r'(?:Pukul|Jam|Time|Rilis)\s*:\s*([^|]+)', text, re.I)
                                if m_time: estimation = m_time.group(1).strip()
                            
                            data['estimation'] = estimation
                            # Filter duplicate
                            if data['title'] not in [x['title'] for x in anime_list]:
                                anime_list.append(data)
                    if anime_list: break
                curr = curr.find_next_sibling()
                limit += 1

        days_result.append({
            "day": eng_day,
            "animeList": anime_list
        })

    return JSONResponse({
        "status": "success",
        "creator": "Sanka Vollerei",
        "data": { "days": days_result }
    })

# ==========================================
# 3. HOME & LATEST
# ==========================================
@app.get("/anime/samehadaku/home")
def get_home_data():
    soup = get_soup(BASE_URL)
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    data = {}
    
    # Recent
    recent_list = []
    for item in soup.select(".post-show li")[:10] or soup.select(".animepost")[:10]:
        base = parse_anime_item_standard(item)
        if base:
            # Add episodes & released info
            ep_tag = item.find("span", class_="episode") or item.find("div", class_="dtla")
            base['episodes'] = ep_tag.get_text(strip=True).replace("Episode", "").strip() if ep_tag else "?"
            
            date_tag = item.find("span", class_="date") or item.find("span", class_="year")
            base['releasedOn'] = date_tag.get_text(strip=True) if date_tag else "?"
            recent_list.append(base)
    
    data["recent"] = { "href": "/samehadaku/recent", "animeList": recent_list }
    
    # Top 10
    top_list = []
    top_nodes = soup.select(".widget_senction.popular .serieslist li") or soup.select(".serieslist.pop li")
    for idx, item in enumerate(top_nodes, 1):
        base = parse_anime_item_standard(item)
        if base:
            base['rank'] = idx
            top_list.append(base)
    
    data["top10"] = { "href": "/samehadaku/top10", "animeList": top_list }
    data["batch"] = { "href": "/samehadaku/batch", "batchList": [] } # Placeholder
    data["movie"] = { "href": "/samehadaku/movies", "animeList": [] } # Placeholder

    return JSONResponse({"status": "success", "data": data})

@app.get("/anime/samehadaku/latest")
def get_latest(page: int = 1):
    url = f"{BASE_URL}/anime-terbaru/page/{page}/"
    if page == 1: url = f"{BASE_URL}/anime-terbaru/"
    soup = get_soup(url)
    
    results = []
    for item in soup.select(".post-show li") or soup.select(".animepost"):
        base = parse_anime_item_standard(item)
        if base:
            ep_tag = item.find("span", class_="episode")
            base['episodes'] = ep_tag.get_text(strip=True).replace("Episode", "").strip() if ep_tag else "?"
            date_tag = item.find("span", class_="date")
            base['releasedOn'] = date_tag.get_text(strip=True) if date_tag else "?"
            results.append(base)
            
    return JSONResponse({
        "status": "success",
        "data": { "animeList": results },
        "pagination": get_pagination(soup, page)
    })

# ==========================================
# 4. LISTS (ONGOING, COMPLETED, POPULAR, MOVIES)
# ==========================================
@app.get("/anime/samehadaku/ongoing")
def get_ongoing(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Ongoing&order=update")
    results = [parse_anime_item_standard(x) for x in soup.select(".animepost") if parse_anime_item_standard(x)]
    return JSONResponse({"status": "success", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/completed")
def get_completed(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Completed&order=latest")
    results = [parse_anime_item_standard(x) for x in soup.select(".animepost") if parse_anime_item_standard(x)]
    # Force status completed
    for r in results: r['status'] = "Completed"
    return JSONResponse({"status": "success", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/popular")
def get_popular(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-anime-2/page/{page}/?order=popular")
    results = [parse_anime_item_standard(x) for x in soup.select(".animepost") if parse_anime_item_standard(x)]
    return JSONResponse({"status": "success", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/movies")
def get_movies(page: int = 1):
    soup = get_soup(f"{BASE_URL}/anime-movie/page/{page}/")
    results = [parse_anime_item_standard(x) for x in soup.select(".animepost") if parse_anime_item_standard(x)]
    for r in results: r['type'] = "Movie"
    return JSONResponse({"status": "success", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# ==========================================
# 5. BATCH LIST
# ==========================================
@app.get("/anime/samehadaku/batch")
def get_batch_list(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-batch/page/{page}/")
    results = []
    for node in soup.select(".animepost"):
        try:
            item = parse_anime_item_standard(node)
            if item:
                # Modif field biar sesuai batch
                item['batchId'] = item.pop('animeId')
                item['href'] = f"/anime/samehadaku/batch/{item['batchId']}"
                results.append(item)
        except: continue
    return JSONResponse({"status": "success", "data": {"batchList": results}, "pagination": get_pagination(soup, page)})

# ==========================================
# 6. GENRES
# ==========================================
@app.get("/anime/samehadaku/genres/{genre_id}")
def get_anime_by_genre(genre_id: str, page: int = 1):
    soup = get_soup(f"{BASE_URL}/genre/{genre_id}/page/{page}/")
    results = [parse_anime_item_standard(x) for x in soup.select(".animepost") if parse_anime_item_standard(x)]
    return JSONResponse({"status": "success", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# ==========================================
# 7. DETAILS (ANIME & EPISODE)
# ==========================================
@app.get("/anime/samehadaku/anime/{anime_id}")
def get_anime_detail(anime_id: str):
    soup = get_soup(f"{BASE_URL}/anime/{anime_id}/")
    if not soup: return JSONResponse({"status": "failed"}, 404)
    
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        poster = extract_poster(soup.find("div", class_="thumb"))
        
        # Info Parsing
        infos = {}
        for spe in soup.select(".infox .spe span"):
            text = spe.get_text(strip=True)
            if ":" in text:
                key, val = text.split(":", 1)
                infos[key.strip().lower()] = val.strip()

        # Synopsis
        synopsis_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        paragraphs = []
        if synopsis_div:
            ps = synopsis_div.find_all("p")
            paragraphs = [p.get_text(strip=True) for p in ps if p.get_text(strip=True)] if ps else [synopsis_div.get_text(strip=True)]

        # Episode List
        episodes = []
        for li in soup.select(".lstepsiode li"):
            a_tag = li.find("a")
            if a_tag:
                ep_id = extract_id(a_tag['href'])
                episodes.append({
                    "title": li.find("span", class_="epl-title").get_text(strip=True) if li.find("span", class_="epl-title") else a_tag.get_text(strip=True),
                    "episodeId": ep_id,
                    "href": f"/anime/samehadaku/episode/{ep_id}",
                    "date": li.find("span", class_="date").get_text(strip=True) if li.find("span", class_="date") else "?"
                })

        data = {
            "title": title, "poster": poster,
            "score": { "value": infos.get("score", "?"), "users": "N/A" },
            "status": infos.get("status", "Unknown"), "type": infos.get("type", "TV"),
            "synopsis": { "paragraphs": paragraphs },
            "genreList": parse_genre_list(soup.find("div", class_="genre-info")),
            "episodeList": episodes,
            "japanese": infos.get("japanese", "-"), "synonyms": infos.get("synonyms", "-"),
            "english": infos.get("english", "-"), "source": infos.get("source", "-"),
            "duration": infos.get("duration", "-"), "studios": infos.get("studio", "-")
        }
        return JSONResponse({"status": "success", "data": data})
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)

@app.get("/anime/samehadaku/episode/{episode_id}")
def get_episode_detail(episode_id: str):
    soup = get_soup(f"{BASE_URL}/{episode_id}/")
    if not soup: return JSONResponse({"status": "failed"}, 404)
    
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        
        # Navigation
        nav = { "prev": None, "next": None }
        prev_a = soup.find("a", class_="prev")
        next_a = soup.find("a", class_="next")
        if prev_a and "/anime/" not in prev_a['href']: nav["prev"] = f"/anime/samehadaku/episode/{extract_id(prev_a['href'])}"
        if next_a and "/anime/" not in next_a['href']: nav["next"] = f"/anime/samehadaku/episode/{extract_id(next_a['href'])}"

        # Download Links
        download_formats = []
        download_box = soup.find("div", class_="download-eps") or soup.find("div", id="server")
        if download_box:
            for ul in download_box.find_all("ul"):
                format_title = "Unknown"
                prev = ul.find_previous(["p", "h4", "div"])
                if prev: format_title = prev.get_text(strip=True)
                
                if "MKV" in format_title: format_title = "MKV"
                elif "MP4" in format_title: format_title = "MP4"
                elif "x265" in format_title: format_title = "x265"
                
                qualities = []
                for li in ul.find_all("li"):
                    q_name = li.find("strong").get_text(strip=True) if li.find("strong") else "Unknown"
                    urls = [{"title": a.get_text(strip=True), "url": a['href']} for a in li.find_all("a")]
                    qualities.append({"title": q_name, "urls": urls})
                
                if qualities: download_formats.append({"title": format_title, "qualities": qualities})

        return JSONResponse({
            "status": "success", 
            "data": {
                "title": title,
                "streamUrl": soup.find("iframe")['src'] if soup.find("iframe") else "",
                "navigation": nav,
                "downloads": download_formats
            }
        })
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)
