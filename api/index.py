from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku API V21 - Schedule Tabs Fixed")

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
    # Coba berbagai kemungkinan lokasi genre
    links = node.select(".genres a") or node.select(".genre-info a") or node.select(".genre a") or node.select("div.bean a")
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
            if "Episode" in raw_ep:
                ep = raw_ep.replace("Episode", "").strip()
            else:
                m = re.search(r'\d+', raw_ep)
                ep = m.group(0) if m else raw_ep

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
            "title": title,
            "poster": extract_poster(node),
            "type": atype,
            "score": score,
            "status": status,
            "animeId": anime_id,
            "href": f"/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url,
            "genreList": parse_genre_list(node)
        }
    except: return None

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"message": "Samehadaku API V21 - Fixed Schedule Logic"}

# 1. SCHEDULE (LOGIC BARU: CARI ID/CLASS HARI)
@app.get("/anime/samehadaku/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    
    # Mapping Hari: (Key JSON, [Kemungkinan ID/Class/Text di HTML])
    day_mapping = [
        ("Monday", ["senin", "monday"]), 
        ("Tuesday", ["selasa", "tuesday"]), 
        ("Wednesday", ["rabu", "wednesday"]),
        ("Thursday", ["kamis", "thursday"]), 
        ("Friday", ["jumat", "friday"]), 
        ("Saturday", ["sabtu", "saturday"]), 
        ("Sunday", ["minggu", "sunday"])
    ]
    
    days_result = []
    
    # Area jadwal
    schedule_area = soup.find("div", class_="schedule") or soup.find("div", class_="entry-content") or soup

    for eng_day, keys in day_mapping:
        anime_list = []
        
        # STRATEGI 1: Cari Container Spesifik (Tab Pane)
        # Cari div yang id-nya mengandung nama hari (misal id="senin")
        container = None
        for k in keys:
            # Coba cari berdasarkan ID
            container = schedule_area.find("div", id=re.compile(k, re.I))
            if container: break
            # Coba cari berdasarkan Class
            container = schedule_area.find("div", class_=re.compile(k, re.I))
            if container: break
        
        # STRATEGI 2: Fallback ke Text Header (Jika tab tidak pakai ID)
        if not container:
            header = schedule_area.find(lambda t: t.name in ['h3','h4','div','b'] and any(k in t.get_text(strip=True).lower() for k in keys))
            if header:
                # Cari container di dekat header
                curr = header.find_next_sibling()
                limit = 0
                while curr and limit < 3:
                    if curr.name in ['div', 'ul'] and (curr.select(".animepost") or curr.select("li a")):
                        container = curr
                        break
                    curr = curr.find_next_sibling()
                    limit += 1

        # Kalau container ketemu, parse isinya
        if container:
            raw_items = container.select(".animepost") or container.select("li")
            for item in raw_items:
                # Pastikan item ini punya link anime
                if item.find("a") and "/anime/" in item.find("a").get("href",""):
                    parsed = parse_library_item(item)
                    if parsed:
                        # Hapus status, ganti estimation time (Sesuai Video)
                        del parsed['status']
                        
                        est = "Update"
                        # Cari waktu tayang (biasanya ada ikon jam atau text waktu)
                        # Dari video, waktunya format "01:00", "23:00"
                        # Biasanya ada di class .time atau .data
                        time_tag = item.find("span", class_="time") or item.find("div", class_="btime")
                        if time_tag:
                            est = time_tag.get_text(strip=True)
                        else:
                            # Coba cari di tooltip jika tidak ada di luar
                            tooltip = item.find("div", class_="ttls") or item.find("div", class_="dtla")
                            if tooltip:
                                text = tooltip.get_text(" ", strip=True)
                                m_time = re.search(r'(?:Pukul|Jam|Time)\s*:\s*([\d\:]+)', text, re.I)
                                if m_time: est = m_time.group(1).strip()
                        
                        parsed['estimation'] = est # Format "01:00" atau "Update"
                        
                        if parsed['title'] not in [x['title'] for x in anime_list]:
                            anime_list.append(parsed)

        days_result.append({
            "day": eng_day,
            "animeList": anime_list
        })

    return JSONResponse({
        "status": "success",
        "creator": "Sanka Vollerei",
        "message": "",
        "data": { "days": days_result },
        "pagination": None
    })

# 2. HOME
@app.get("/anime/samehadaku/home")
def get_home_data():
    soup = get_soup(BASE_URL)
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    data = {}
    
    # Recent
    recent_list = []
    nodes = soup.select(".post-show li") or soup.select(".animepost")[:10]
    for item in nodes:
        parsed = parse_latest_item(item)
        if parsed: recent_list.append(parsed)
            
    data["recent"] = { "href": "/samehadaku/recent", "samehadakuUrl": f"{BASE_URL}/anime-terbaru/", "animeList": recent_list }
    
    # Top 10
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

# 3. LISTS (LATEST, ONGOING, COMPLETED, SEARCH, GENRE, MOVIES, POPULAR, BATCH)
@app.get("/anime/samehadaku/latest")
def get_latest(page: int = 1):
    url = f"{BASE_URL}/anime-terbaru/page/{page}/" if page > 1 else f"{BASE_URL}/anime-terbaru/"
    soup = get_soup(url)
    results = [parse_latest_item(x) for x in (soup.select(".post-show li") or soup.select(".animepost")) if parse_latest_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/ongoing")
def get_ongoing(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Ongoing&order=update" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Ongoing&order=update"
    soup = get_soup(url)
    results = [parse_library_item(x, "Ongoing") for x in soup.select(".animepost") if parse_library_item(x, "Ongoing")]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/completed")
def get_completed(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Completed&order=latest" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Completed&order=latest"
    soup = get_soup(url)
    results = [parse_library_item(x, "Completed") for x in soup.select(".animepost") if parse_library_item(x, "Completed")]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/search")
def search_anime(query: str, page: int = 1):
    url = f"{BASE_URL}/page/{page}/?s={query}" if page > 1 else f"{BASE_URL}/?s={query}"
    soup = get_soup(url)
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

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
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"genreList": genre_list}})

@app.get("/anime/samehadaku/genres/{genre_id}")
def get_anime_by_genre(genre_id: str, page: int = 1):
    url = f"{BASE_URL}/genre/{genre_id}/page/{page}/" if page > 1 else f"{BASE_URL}/genre/{genre_id}/"
    soup = get_soup(url)
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/movies")
def get_movies(page: int = 1):
    soup = get_soup(f"{BASE_URL}/anime-movie/page/{page}/" if page > 1 else f"{BASE_URL}/anime-movie/")
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    for r in results: r['type'] = "Movie"
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

@app.get("/anime/samehadaku/popular")
def get_popular(page: int = 1):
    soup = get_soup(f"{BASE_URL}/daftar-anime-2/page/{page}/?order=popular" if page > 1 else f"{BASE_URL}/daftar-anime-2/?order=popular")
    results = [parse_library_item(x) for x in soup.select(".animepost") if parse_library_item(x)]
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)})

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

# 4. DETAILS
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
        paragraphs = [p.get_text(strip=True) for p in synopsis_div.find_all("p")] if synopsis_div else [synopsis_div.get_text(strip=True)] if synopsis_div else []
        
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
            "title": title, "poster": poster, "score": {"value": infos.get("score","?"), "users": "N/A"},
            "japanese": infos.get("japanese","-"), "synonyms": infos.get("synonyms","-"), "english": infos.get("english","-"),
            "status": infos.get("status","Unknown"), "type": infos.get("type","TV"), "source": infos.get("source","-"),
            "duration": infos.get("duration","-"), "episodes": infos.get("total episode", None),
            "season": infos.get("season","-"), "studios": infos.get("studio","-"), "producers": infos.get("producers","-"),
            "aired": infos.get("released","-"), "trailer": soup.find("iframe")['src'] if soup.select_one(".trailer-anime iframe") else "",
            "synopsis": {"paragraphs": paragraphs, "connections": []}, "genreList": parse_genre_list(soup.find("div", class_="genre-info")),
            "batchList": [], "episodeList": episodes
        }
        return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": data, "pagination": None})
    except Exception as e: return JSONResponse({"status": "failed", "error": str(e)}, 500)

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
