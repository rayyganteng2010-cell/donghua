from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku API V17 - Complete + Genres")

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
    links = node.select(".genres a") or node.select(".genre-info a") or node.select(".genre a") or node.select("div.bean a")
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

# --- PARSERS ---

def parse_latest_item(node):
    """Parser khusus Home/Latest (Ada Episode & Date)"""
    try:
        a_tag = node.find("a")
        if not a_tag: return None
        
        real_url = a_tag['href']
        anime_id = extract_id(real_url)
        
        title = "Unknown"
        t_div = node.find("div", class_="title")
        if t_div: title = t_div.get_text(strip=True)
        else: title = a_tag.get("title", "Unknown")

        ep = "?"
        ep_tag = node.find("span", class_="episode") or node.find("div", class_="dtla")
        if ep_tag:
            raw_ep = ep_tag.get_text(strip=True)
            ep = raw_ep.replace("Episode", "").strip() if "Episode" in raw_ep else re.search(r'\d+', raw_ep).group(0) if re.search(r'\d+', raw_ep) else "?"

        released = "?"
        date_tag = node.find("span", class_="date") or node.find("span", class_="year")
        if date_tag: released = date_tag.get_text(strip=True)
        else:
            meta = node.find("div", class_="meta")
            if meta: released = meta.get_text(strip=True)

        return {
            "title": title,
            "poster": extract_poster(node),
            "episodes": ep,
            "releasedOn": released,
            "animeId": anime_id,
            "href": f"/anime/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url
        }
    except: return None

def parse_library_item(node, status_force=None):
    """Parser khusus Ongoing, Completed, Search, Schedule"""
    try:
        a_tag = node.find("a")
        if not a_tag: return None
        
        real_url = a_tag['href']
        anime_id = extract_id(real_url)
        title = node.find("div", class_="title").get_text(strip=True)
        
        score = "?"
        score_tag = node.find("div", class_="score")
        if score_tag: score = score_tag.get_text(strip=True).strip()
        
        atype = "TV"
        type_tag = node.find("div", class_="type")
        if type_tag: atype = type_tag.get_text(strip=True)
        
        status = status_force if status_force else "Ongoing"

        return {
            "title": title,
            "poster": extract_poster(node),
            "type": atype,
            "score": score,
            "status": status,
            "animeId": anime_id,
            "href": f"/anime/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url,
            "genreList": parse_genre_list(node)
        }
    except: return None

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"message": "Samehadaku API V17 - Complete"}

# 1. NEW ENDPOINT: LIST ALL GENRES
@app.get("/anime/samehadaku/genres")
def get_all_genres():
    soup = get_soup(BASE_URL)
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    genre_list = []
    seen_ids = set()
    
    # Cari link genre (biasanya di widget/sidebar)
    # Kita cari semua tag <a> yang href-nya mengandung '/genre/'
    nodes = soup.select("a[href*='/genre/']")
    
    for node in nodes:
        try:
            href = node['href']
            # Validasi basic
            if "/genre/" not in href: continue
            
            g_id = extract_id(href)
            title = node.get_text(strip=True)
            
            # Bersihkan title jika ada count (misal "Action (5)")
            if "(" in title: title = title.split("(")[0].strip()
            
            if g_id and g_id not in seen_ids and title:
                genre_list.append({
                    "title": title,
                    "genreId": g_id,
                    "href": f"/anime/samehadaku/genres/{g_id}",
                    "samehadakuUrl": href
                })
                seen_ids.add(g_id)
        except: continue
        
    # Sort A-Z
    genre_list.sort(key=lambda x: x['title'])
    
    return JSONResponse({
        "status": "success",
        "creator": "Sanka Vollerei",
        "message": "",
        "data": { "genreList": genre_list }
    })

# 2. HOME
@app.get("/anime/samehadaku/home")
def get_home_data():
    soup = get_soup(BASE_URL)
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    data = {}
    recent_list = []
    nodes = soup.select(".post-show li") or soup.select(".animepost")[:10]
    for item in nodes:
        parsed = parse_latest_item(item)
        if parsed: recent_list.append(parsed)
            
    data["recent"] = { "href": "/samehadaku/recent", "samehadakuUrl": f"{BASE_URL}/anime-terbaru/", "animeList": recent_list }
    
    top_list = []
    for idx, item in enumerate(soup.select(".widget_senction.popular .serieslist li") or soup.select(".serieslist.pop li"), 1):
        parsed = parse_library_item(item)
        if parsed:
            top_list.append({
                "rank": idx, "title": parsed['title'], "poster": parsed['poster'], "score": parsed['score'],
                "animeId": parsed['animeId'], "href": parsed['href'], "samehadakuUrl": parsed['samehadakuUrl']
            })
            
    data["top10"] = { "href": "/samehadaku/top10", "samehadakuUrl": BASE_URL, "animeList": top_list }
    data["batch"] = { "href": "/samehadaku/batch", "samehadakuUrl": f"{BASE_URL}/daftar-batch/", "batchList": [] }
    data["movie"] = { "href": "/samehadaku/movies", "samehadakuUrl": f"{BASE_URL}/anime-movie/", "animeList": [] }

    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": data})

# 3. LATEST
@app.get("/anime/samehadaku/latest")
def get_latest(page: int = 1):
    url = f"{BASE_URL}/anime-terbaru/page/{page}/" if page > 1 else f"{BASE_URL}/anime-terbaru/"
    soup = get_soup(url)
    results = [parse_latest_item(x) for x in (soup.select(".post-show li") or soup.select(".animepost")) if parse_latest_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 4. ONGOING
@app.get("/anime/samehadaku/ongoing")
def get_ongoing(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Ongoing&order=update" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Ongoing&order=update"
    soup = get_soup(url)
    results = [parse_library_item(x, "Ongoing") for x in soup.select(".animepost") if parse_library_item(x, "Ongoing")]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 5. COMPLETED
@app.get("/anime/samehadaku/completed")
def get_completed(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Completed&order=latest" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Completed&order=latest"
    soup = get_soup(url)
    results = [parse_library_item(x, "Completed") for x in soup.select(".animepost") if parse_library_item(x, "Completed")]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 6. SCHEDULE
@app.get("/anime/samehadaku/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    day_mapping = [("Monday", "Senin"), ("Tuesday", "Selasa"), ("Wednesday", "Rabu"), ("Thursday", "Kamis"), ("Friday", "Jumat"), ("Saturday", "Sabtu"), ("Sunday", "Minggu")]
    days_result = []
    content = soup.find("div", class_="entry-content") or soup.find("main") or soup
    
    for eng, indo in day_mapping:
        anime_list = []
        header = content.find(lambda t: t.name in ['h3','h4','div','span'] and indo.lower() == t.get_text(strip=True).lower())
        if header:
            curr = header.find_next_sibling()
            limit = 0
            while curr and limit < 5:
                if ("animepost" in str(curr)) or (curr.name == "ul"):
                    for item in (curr.select(".animepost") or curr.select("li")):
                        if item.find("a") and "/anime/" in item.find("a").get("href",""):
                            parsed = parse_library_item(item)
                            if parsed:
                                # Estimation time logic
                                est = "Update"
                                tooltip = item.find("div", class_="ttls") or item.find("div", class_="dtla")
                                if tooltip:
                                    m_time = re.search(r'(?:Pukul|Jam|Time|Rilis)\s*:\s*([^|]+)', tooltip.get_text(" ", strip=True), re.I)
                                    if m_time: est = m_time.group(1).strip()
                                parsed['estimation'] = est
                                if parsed['title'] not in [x['title'] for x in anime_list]: anime_list.append(parsed)
                    if anime_list: break
                curr = curr.find_next_sibling()
                limit += 1
        days_result.append({"day": eng, "animeList": anime_list})
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"days": days_result}})

# 7. SEARCH
@app.get("/anime/samehadaku/search")
def search_anime(query: str, page: int = 1):
    url = f"{BASE_URL}/page/{page}/?s={query}" if page > 1 else f"{BASE_URL}/?s={query}"
    soup = get_soup(url)
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 8. GENRE DETAIL
@app.get("/anime/samehadaku/genres/{genre_id}")
def get_anime_by_genre(genre_id: str, page: int = 1):
    url = f"{BASE_URL}/genre/{genre_id}/page/{page}/" if page > 1 else f"{BASE_URL}/genre/{genre_id}/"
    soup = get_soup(url)
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 9. BATCH
@app.get("/anime/samehadaku/batch")
def get_batch_list(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-batch/page/{page}/" if page > 1 else f"{BASE_URL}/daftar-batch/")
    results = []
    for node in soup.select(".animepost"):
        item = parse_library_item(node, "Completed")
        if item:
            item['batchId'] = item.pop('animeId')
            item['href'] = f"/anime/samehadaku/batch/{item['batchId']}"
            results.append(item)
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"batchList": results}, "pagination": get_pagination(soup, page)})

# 10. MOVIES
@app.get("/anime/samehadaku/movies")
def get_movies(page: int = 1):
    soup = get_soup(f"{BASE_URL}/anime-movie/page/{page}/" if page > 1 else f"{BASE_URL}/anime-movie/")
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    for r in results: r['type'] = "Movie"
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 11. POPULAR
@app.get("/anime/samehadaku/popular")
def get_popular(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-anime-2/page/{page}/?order=popular" if page > 1 else f"{BASE_URL}/daftar-anime-2/?order=popular")
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 12. ANIME DETAIL
@app.get("/anime/samehadaku/anime/{anime_id}")
def get_anime_detail(anime_id: str):
    soup = get_soup(f"{BASE_URL}/anime/{anime_id}/")
    if not soup: return JSONResponse({"status": "failed"}, 404)
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        poster = extract_poster(soup.find("div", class_="thumb"))
        infos = {}
        for spe in soup.select(".infox .spe span"):
            if ":" in spe.get_text(): k,v = spe.get_text().split(":",1); infos[k.strip().lower()] = v.strip()
        
        synopsis_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        paragraphs = [p.get_text(strip=True) for p in synopsis_div.find_all("p")] if synopsis_div else []
        if not paragraphs and synopsis_div: paragraphs = [synopsis_div.get_text(strip=True)]

        episodes = []
        for li in soup.select(".lstepsiode li"):
            a = li.find("a")
            if a:
                ep_id = extract_id(a['href'])
                episodes.append({
                    "title": li.find("span", class_="epl-title").get_text(strip=True) if li.find("span", class_="epl-title") else a.get_text(strip=True),
                    "episodeId": ep_id,
                    "href": f"/anime/samehadaku/episode/{ep_id}",
                    "date": li.find("span", class_="date").get_text(strip=True) if li.find("span", class_="date") else "?"
                })
        
        data = {
            "title": title, "poster": poster, "score": {"value": infos.get("score","?"), "users": "N/A"},
            "japanese": infos.get("japanese","-"), "synonyms": infos.get("synonyms","-"), "english": infos.get("english","-"),
            "status": infos.get("status","Unknown"), "type": infos.get("type","TV"), "source": infos.get("source","-"),
            "duration": infos.get("duration","-"), "studios": infos.get("studio","-"), "producers": infos.get("producers","-"),
            "aired": infos.get("released","-"), "season": infos.get("season","-"),
            "synopsis": {"paragraphs": paragraphs}, "genreList": parse_genre_list(soup.find("div", class_="genre-info")),
            "episodeList": episodes, "trailer": soup.find("iframe")['src'] if soup.find("div", class_="trailer-anime") and soup.find("div", class_="trailer-anime").find("iframe") else ""
        }
        return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": data})
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)

# 13. EPISODE DETAIL
@app.get("/anime/samehadaku/episode/{episode_id}")
def get_episode_detail(episode_id: str):
    soup = get_soup(f"{BASE_URL}/{episode_id}/")
    if not soup: return JSONResponse({"status": "failed"}, 404)
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        nav = {"prev": None, "next": None}
        prev_a, next_a = soup.find("a", class_="prev"), soup.find("a", class_="next")
        if prev_a and "/anime/" not in prev_a['href']: nav["prev"] = f"/anime/samehadaku/episode/{extract_id(prev_a['href'])}"
        if next_a and "/anime/" not in next_a['href']: nav["next"] = f"/anime/samehadaku/episode/{extract_id(next_a['href'])}"
        
        downloads = []
        box = soup.find("div", class_="download-eps") or soup.find("div", id="server")
        if box:
            for ul in box.find_all("ul"):
                fmt_title = "Unknown"
                prev = ul.find_previous(["p", "h4", "div", "span"])
                if prev: fmt_title = prev.get_text(strip=True)
                
                if "MKV" in fmt_title: fmt_title = "MKV"
                elif "MP4" in fmt_title: fmt_title = "MP4"
                elif "x265" in fmt_title: fmt_title = "x265"
                
                quals = []
                for li in ul.find_all("li"):
                    qname = li.find("strong").get_text(strip=True) if li.find("strong") else "Unknown"
                    urls = [{"title": a.get_text(strip=True), "url": a['href']} for a in li.find_all("a")]
                    quals.append({"title": qname, "urls": urls})
                if quals: downloads.append({"title": fmt_title, "qualities": quals})
        
        return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {
            "title": title, "streamUrl": soup.find("iframe")['src'] if soup.find("iframe") else "", "navigation": nav, "downloads": downloads
        }})
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)
