from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku API V26 - Detail & Latest Fixed")

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
    if not node: return genres
    links = node.select("a[href*='/genre/']")
    for g in links:
        g_id = extract_id(g['href'])
        genres.append({
            "title": g.get_text(strip=True),
            "genreId": g_id,
            "href": f"/samehadaku/genres/{g_id}",
            "samehadakuUrl": g['href']
        })
    return genres

def get_pagination(soup, current_page):
    pagination = soup.find("div", class_="pagination")
    if not pagination: return None
    page_links = pagination.find_all("a", class_="page-numbers")
    total_pages = 1
    if page_links:
        nums = [int(p.get_text(strip=True).replace(",","")) for p in page_links if p.get_text(strip=True).replace(",","").isdigit()]
        if nums: total_pages = max(nums)
    has_next = bool(pagination.find("a", class_="next"))
    has_prev = bool(pagination.find("a", class_="prev"))
    return {
        "currentPage": current_page, "hasPrevPage": has_prev, "prevPage": current_page - 1 if has_prev else None,
        "hasNextPage": has_next, "nextPage": current_page + 1 if has_next else None, "totalPages": total_pages
    }

# --- PARSERS ---

def parse_latest_item(node):
    """Parser Latest (Fix Text Nyatu)"""
    try:
        a_tag = node.find("a")
        if not a_tag: return None
        
        real_url = a_tag['href']
        anime_id = extract_id(real_url)
        
        title = "Unknown"
        t_div = node.find("div", class_="title")
        if t_div: title = t_div.get_text(strip=True)
        else: title = a_tag.get("title") or a_tag.get_text(strip=True)

        # Fix Episode & Released On
        ep = "?"
        released = "?"
        
        # 1. Coba ambil dari tag spesifik dulu (paling akurat)
        ep_tag = node.find("span", class_="episode") or node.find("div", class_="dtla")
        date_tag = node.find("span", class_="date") or node.find("span", class_="year")
        
        if ep_tag:
            raw_ep = ep_tag.get_text(strip=True)
            # Hapus text sampah
            ep = raw_ep.replace("Episode", "").replace(":", "").strip()
        
        if date_tag:
            released = date_tag.get_text(strip=True)
        
        # 2. Fallback: Parse text gabungan dengan separator
        if ep == "?" or released == "?":
            # Ambil text dengan separator spasi biar gak nempel "Jihen3Posted"
            full_text = node.get_text(" | ", strip=True)
            
            # Cari Episode (Angka murni atau "Episode X")
            if ep == "?":
                m_ep = re.search(r'(?:Episode\s+|^)(\d+)', full_text, re.I)
                if m_ep: ep = m_ep.group(1)
            
            # Cari Released (Released on: ...)
            if released == "?":
                if "Released on:" in full_text:
                    parts = full_text.split("Released on:")
                    if len(parts) > 1:
                        # Ambil sisa text sampai pipe berikutnya atau ujung
                        released = parts[1].split("|")[0].strip()
                elif "yang lalu" in full_text:
                    m_date = re.search(r'([\d\w\s]+yang lalu)', full_text)
                    if m_date: released = m_date.group(1).strip()

        return {
            "title": title,
            "poster": extract_poster(node),
            "episodes": ep,
            "releasedOn": released,
            "animeId": anime_id,
            "href": f"/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url
        }
    except: return None

def parse_library_item(node, status_force=None):
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
            "title": title, "poster": extract_poster(node), "type": atype, "score": score,
            "status": status, "animeId": anime_id, "href": f"/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url, "genreList": parse_genre_list(node)
        }
    except: return None

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"message": "Samehadaku API V26 - Fix Detail & Latest"}

# 1. LIST GENRES
@app.get("/anime/samehadaku/genres")
def get_all_genres():
    soup = get_soup(BASE_URL)
    genre_list = []
    seen = set()
    for node in soup.select("a[href*='/genre/']"):
        if node['href'] not in seen:
            t = node.get_text(strip=True).split("(")[0].strip()
            gid = extract_id(node['href'])
            if gid:
                genre_list.append({"title": t, "genreId": gid, "href": f"/samehadaku/genres/{gid}", "samehadakuUrl": node['href']})
                seen.add(node['href'])
    genre_list.sort(key=lambda x: x['title'])
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": { "genreList": genre_list }})

# 2. HOME
@app.get("/anime/samehadaku/home")
def get_home_data():
    soup = get_soup(BASE_URL)
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
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Currently+Airing&order=update" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Currently+Airing&order=update"
    soup = get_soup(url)
    results = [parse_library_item(x, "Ongoing") for x in soup.select(".animepost") if parse_library_item(x, "Ongoing")]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 5. COMPLETED
@app.get("/anime/samehadaku/completed")
def get_completed(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Finished+Airing&order=latest" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Finished+Airing&order=latest"
    soup = get_soup(url)
    results = [parse_library_item(x, "Completed") for x in soup.select(".animepost") if parse_library_item(x, "Completed")]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

# 6. SCHEDULE
@app.get("/anime/samehadaku/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    day_mapping = [("Monday", "senin"), ("Tuesday", "selasa"), ("Wednesday", "rabu"), ("Thursday", "kamis"), ("Friday", "jumat"), ("Saturday", "sabtu"), ("Sunday", "minggu")]
    days_result = []
    content = soup.find("div", class_="entry-content") or soup.find("main") or soup
    
    for eng, indo in day_mapping:
        anime_list = []
        container = content.find("div", id=indo) or content.find("div", class_=indo)
        # Fallback: Cari header text
        if not container:
            header = content.find(lambda t: t.name in ['h3','h4','b'] and indo.lower() == t.get_text(strip=True).lower())
            if header:
                curr = header.find_next_sibling()
                for _ in range(5):
                    if curr and (curr.select(".animepost") or curr.select("li")):
                        container = curr
                        break
                    curr = curr.find_next_sibling() if curr else None
        
        if container:
            raw_items = container.select(".animepost") or container.select("li")
            for item in raw_items:
                if item.find("a") and "/anime/" in item.find("a").get("href",""):
                    parsed = parse_library_item(item)
                    if parsed:
                        del parsed['status']
                        est = "Update"
                        time_tag = item.find("span", class_="time") or item.find("div", class_="btime")
                        if time_tag: est = time_tag.get_text(strip=True)
                        else:
                            tooltip = item.find("div", class_="ttls") or item.find("div", class_="dtla")
                            if tooltip:
                                m = re.search(r'(?:Pukul|Jam|Time|Rilis)\s*:\s*([\d\:]+)', tooltip.get_text(" ", strip=True), re.I)
                                if m: est = m.group(1).strip()
                        parsed['estimation'] = est
                        if parsed['title'] not in [x['title'] for x in anime_list]: anime_list.append(parsed)
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
            item['href'] = f"/samehadaku/batch/{item['batchId']}"
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

# 12. ANIME DETAIL (FIX DATA KOSONG)
@app.get("/anime/samehadaku/anime/{anime_id}")
def get_anime_detail(anime_id: str):
    soup = get_soup(f"{BASE_URL}/anime/{anime_id}/")
    if not soup: return JSONResponse({"status": "failed"}, 404)
    try:
        # Title Fix: Hapus "Nonton Anime" dan "Sub Indo"
        raw_title = soup.find("h1", class_="entry-title").get_text(strip=True)
        title = raw_title.replace("Nonton Anime", "").replace("Sub Indo", "").strip()
        
        poster = extract_poster(soup.find("div", class_="thumb"))
        
        # Info Parsing (Updated Selector)
        infos = {}
        # Gunakan 'get_text' dengan separator ':' karena kadang tag <b> mengacaukan
        for spe in soup.select(".infox .spe"):
            text = spe.get_text(":", strip=True) # Ex: "Japanese: Naruto"
            parts = text.split(":", 1)
            if len(parts) > 1:
                k = parts[0].replace(":", "").strip().lower()
                v = parts[1].strip()
                infos[k] = v
        
        # Mapping Value (Default val if key missing)
        japanese = infos.get("japanese", "-")
        synonyms = infos.get("synonyms", "-")
        english = infos.get("english", "-")
        status = infos.get("status", "Unknown")
        type_anime = infos.get("type", "TV")
        source = infos.get("source", "-")
        duration = infos.get("duration", "-")
        season = infos.get("season", "-")
        studios = infos.get("studio", "-")
        producers = infos.get("producers", "-")
        aired = infos.get("released", "-")
        
        # Episodes (Safe Convert)
        ep_val = infos.get("total episode", "?")
        episodes_count = int(ep_val) if ep_val.isdigit() else None

        # Score & Users
        score_val = infos.get("score", "?")
        if score_val == "?" or not score_val[0].isdigit():
            # Fallback ke schema
            sc = soup.find("span", itemprop="ratingValue")
            if sc: score_val = sc.get_text(strip=True)
            
        rating_count = soup.find("span", itemprop="ratingCount")
        users = f"{rating_count.get_text(strip=True)} users" if rating_count else "N/A"

        # Synopsis
        synopsis_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        paragraphs = []
        if synopsis_div:
            ps = synopsis_div.find_all("p")
            if ps:
                paragraphs = [p.get_text(strip=True) for p in ps if p.get_text(strip=True)]
            else:
                paragraphs = [synopsis_div.get_text(strip=True)]
        
        # Connections
        connections = []
        related = soup.find("div", class_="related-post")
        if related:
            for link in related.find_all("a"):
                connections.append({
                    "title": link.get("title", link.get_text(strip=True)),
                    "animeId": extract_id(link['href']),
                    "href": f"/samehadaku/anime/{extract_id(link['href'])}",
                    "samehadakuUrl": link['href']
                })

        # Episode List
        episodes = []
        for li in soup.select(".lstepsiode li"):
            a = li.find("a")
            if a:
                ep_id = extract_id(a['href'])
                raw_title = li.find("span", class_="epl-title").get_text(strip=True) if li.find("span", class_="epl-title") else a.get_text(strip=True)
                try: t_num = int(re.search(r'\d+', raw_title).group())
                except: t_num = raw_title
                episodes.append({"title": t_num, "episodeId": ep_id, "href": f"/samehadaku/episode/{ep_id}", "samehadakuUrl": a['href']})
        
        data = {
            "title": title, "poster": poster, "score": {"value": score_val, "users": users},
            "japanese": japanese, "synonyms": synonyms, "english": english,
            "status": status, "type": type_anime, "source": source,
            "duration": duration, "episodes": episodes_count,
            "season": season, "studios": studios, "producers": producers,
            "aired": aired, "trailer": soup.find("iframe")['src'] if soup.select_one(".trailer-anime iframe") else "",
            "synopsis": {"paragraphs": paragraphs, "connections": connections},
            "genreList": parse_genre_list(soup.find("div", class_="genre-info")),
            "batchList": [], "episodeList": episodes
        }
        return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": data, "pagination": None})
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)

# 13. EPISODE DETAIL
@app.get("/anime/samehadaku/episode/{episode_id}")
def get_episode_detail(episode_id: str):
    soup = get_soup(f"{BASE_URL}/{episode_id}/")
    if not soup: return JSONResponse({"status": "failed"}, 404)
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        nav = {"prev": None, "next": None}
        pa, na = soup.find("a", class_="prev"), soup.find("a", class_="next")
        if pa and "/anime/" not in pa['href']: nav["prev"] = f"/samehadaku/episode/{extract_id(pa['href'])}"
        if na and "/anime/" not in na['href']: nav["next"] = f"/samehadaku/episode/{extract_id(na['href'])}"
        downloads = []
        box = soup.find("div", class_="download-eps") or soup.find("div", id="server")
        if box:
            for ul in box.find_all("ul"):
                ft = ul.find_previous(["p","h4","div","span"]).get_text(strip=True) if ul.find_previous(["p","h4","div","span"]) else "Unknown"
                if "MKV" in ft: ft = "MKV"
                elif "MP4" in ft: ft = "MP4"
                elif "x265" in ft: ft = "x265"
                qs = []
                for li in ul.find_all("li"):
                    qn = li.find("strong").get_text(strip=True) if li.find("strong") else "Unknown"
                    urls = [{"title": a.get_text(strip=True), "url": a['href']} for a in li.find_all("a")]
                    qs.append({"title": qn, "urls": urls})
                if qs: downloads.append({"title": ft, "qualities": qs})
        return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"title": title, "streamUrl": soup.find("iframe")['src'] if soup.find("iframe") else "", "navigation": nav, "downloads": downloads}})
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)
