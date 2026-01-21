from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku API V30 - Python Perfect (Fixed Schedule)")

# Headers Mirip Browser Asli
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BASE_URL = "https://v1.samehadaku.how"

# --- HELPERS ---

def get_soup(url: str):
    try:
        session = requests.Session()
        req = session.get(url, headers=HEADERS, timeout=15)
        if req.status_code == 404:
            return None
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error: {e}")
        return None

def extract_id(url: str):
    if not url:
        return ""
    return url.strip("/").split("/")[-1]

def extract_poster(node):
    if not node:
        return "https://dummyimage.com/300x400/000/fff&text=No+Image"
    img = node.find("img")
    if not img:
        return "https://dummyimage.com/300x400/000/fff&text=No+Image"
    if img.get("src") and "data:image" not in img.get("src"):
        return img.get("src").split("?")[0]
    return img.get("data-src", "").split("?")[0] or img.get("src", "").split("?")[0] or "https://dummyimage.com/300x400/000/fff&text=No+Image"

def parse_genre_list(node):
    genres = []
    if not node:
        return genres
    links = node.select("a[href*='/genre/']")
    for g in links:
        href = g.get("href", "")
        gid = extract_id(href)
        if gid:
            genres.append(
                {
                    "title": g.get_text(strip=True),
                    "genreId": gid,
                    "href": f"/samehadaku/genres/{gid}",
                    "samehadakuUrl": href,
                }
            )
    return genres

def get_pagination(soup, current_page):
    if not soup:
        return None
    pagination = soup.find("div", class_="pagination")
    if not pagination:
        return None

    total_pages = 1
    page_links = pagination.find_all("a", class_="page-numbers")
    for p in page_links:
        txt = p.get_text(strip=True).replace(",", "")
        if txt.isdigit():
            val = int(txt)
            if val > total_pages:
                total_pages = val

    has_next = bool(pagination.find("a", class_="next"))
    has_prev = bool(pagination.find("a", class_="prev"))

    return {
        "currentPage": current_page,
        "hasPrevPage": has_prev,
        "prevPage": current_page - 1 if has_prev else None,
        "hasNextPage": has_next,
        "nextPage": current_page + 1 if has_next else None,
        "totalPages": total_pages,
    }

# --- PARSERS ---

def parse_latest_item(node):
    """Parser khusus Latest (anti text nyatu)"""
    try:
        a_tag = node.find("a")
        if not a_tag:
            return None

        real_url = a_tag.get("href", "")
        if not real_url:
            return None

        anime_id = extract_id(real_url)

        # Title
        title = "Unknown"
        t_div = node.find("div", class_="title")
        if t_div:
            title = t_div.get_text(strip=True)
        else:
            title = a_tag.get("title") or a_tag.get_text(" ", strip=True) or "Unknown"

        # Poster
        poster = extract_poster(node)

        # Episode & Released (logic anti-nyatu)
        ep = "?"
        released = "?"

        dtla = node.find("div", class_="dtla") or node
        full_text = dtla.get_text(" ", strip=True)

        m_ep = re.search(r"(?:Episode\s*)?(\d+)", full_text, re.IGNORECASE)
        if m_ep:
            ep = m_ep.group(1)

        date_span = node.find("span", class_="date") or node.find("span", class_="year")
        if date_span:
            released = date_span.get_text(strip=True)
        else:
            if "Released on" in full_text:
                parts = full_text.split("Released on")
                if len(parts) > 1:
                    released = parts[1].replace(":", "").strip().split("Posted")[0].strip()
            elif "yang lalu" in full_text:
                m_date = re.search(r"([\d\w\s]+yang lalu)", full_text)
                if m_date:
                    released = m_date.group(1).strip()

        return {
            "title": title,
            "poster": poster,
            "episodes": ep,
            "releasedOn": released,
            "animeId": anime_id,
            "href": f"/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url,
        }
    except:
        return None

def parse_library_item(node, status_force=None):
    """Parser standard untuk List (ongoing, completed, popular, genre, search)"""
    try:
        a_tag = node.find("a")
        if not a_tag:
            return None

        real_url = a_tag.get("href", "")
        if not real_url:
            return None

        anime_id = extract_id(real_url)

        title_div = node.find("div", class_="title")
        title = title_div.get_text(strip=True) if title_div else a_tag.get_text(" ", strip=True)

        poster = extract_poster(node)

        score = "?"
        sc = node.find("div", class_="score")
        if sc:
            score = sc.get_text(strip=True).strip()

        atype = "TV"
        tp = node.find("div", class_="type")
        if tp:
            atype = tp.get_text(strip=True)

        status = status_force if status_force else "Ongoing"

        return {
            "title": title,
            "poster": poster,
            "type": atype,
            "score": score,
            "status": status,
            "animeId": anime_id,
            "href": f"/samehadaku/anime/{anime_id}",
            "samehadakuUrl": real_url,
            "genreList": parse_genre_list(node),
        }
    except:
        return None

# --- FIXED SCHEDULE PARSER (robust) ---

DAY_LABELS = {
    "Monday": ["senin"],
    "Tuesday": ["selasa"],
    "Wednesday": ["rabu"],
    "Thursday": ["kamis"],
    "Friday": ["jumat", "jumaat"],   # penting: sering "Jumaat"
    "Saturday": ["sabtu"],
    "Sunday": ["minggu"],
}

def normalize_day(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())

def is_day_header(tag) -> bool:
    if not getattr(tag, "get_text", None):
        return False
    t = normalize_day(tag.get_text(" ", strip=True))
    if not t:
        return False
    wanted = set()
    for labs in DAY_LABELS.values():
        for x in labs:
            wanted.add(normalize_day(x))
    return t in wanted

def find_day_header(content, wanted_labels):
    wanted = set(normalize_day(x) for x in wanted_labels)
    for tag in content.find_all(["h1","h2","h3","h4","strong","b","p","div","span"], limit=4000):
        txt = normalize_day(tag.get_text(" ", strip=True))
        if txt in wanted:
            return tag
    return None

def parse_schedule_item(node):
    """
    Jadwal rilis sering minim:
    - ada link /anime/
    - kadang format text: "TV 7.10 Judul ..."
    - jam bisa "01:00"
    """
    try:
        a = node.find("a", href=True)
        if not a:
            return None
        href = a["href"]
        if "/anime/" not in href:
            return None

        anime_id = extract_id(href)
        raw = a.get_text(" ", strip=True)

        atype = "TV"
        score = "?"
        title = raw

        m = re.match(r"^(?P<type>[A-Za-z]+)\s+(?P<score>\d+(?:\.\d+)?)\s+(?P<title>.+)$", raw)
        if m:
            atype = m.group("type").strip()
            score = m.group("score").strip()
            title = m.group("title").strip()

        # jam rilis
        estimation = None
        time_tag = node.find("span", class_="time") or node.find("div", class_="btime")
        if time_tag:
            estimation = time_tag.get_text(" ", strip=True)

        if not estimation:
            blob = node.get_text(" ", strip=True)
            mt = re.search(r"\b(\d{1,2}:\d{2})\b", blob)
            if mt:
                estimation = mt.group(1)

        poster = "https://dummyimage.com/300x400/000/fff&text=No+Image"

        return {
            "title": title,
            "poster": poster,
            "type": atype,
            "score": score,
            "animeId": anime_id,
            "href": f"/samehadaku/anime/{anime_id}",
            "samehadakuUrl": href,
            "estimation": estimation or "Update",
            "genreList": [],
        }
    except:
        return None

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"message": "Samehadaku API V30 - Python Works Best (Schedule Fixed)"}

# 1. HOME
@app.get("/anime/samehadaku/home")
def get_home_data():
    soup = get_soup(BASE_URL)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    data = {}

    # Recent
    recent = []
    nodes = soup.select(".post-show li") or soup.select(".animepost")[:10]
    for n in nodes:
        item = parse_latest_item(n)
        if item:
            recent.append(item)
    data["recent"] = {
        "href": "/samehadaku/recent",
        "samehadakuUrl": f"{BASE_URL}/anime-terbaru/",
        "animeList": recent,
    }

    # Top 10
    top10 = []
    top_nodes = soup.select(".widget_senction.popular .serieslist li") or soup.select(".serieslist.pop li")
    for idx, n in enumerate(top_nodes, 1):
        item = parse_library_item(n)
        if item:
            top10.append(
                {
                    "rank": idx,
                    "title": item["title"],
                    "poster": item["poster"],
                    "score": item["score"],
                    "animeId": item["animeId"],
                    "href": item["href"],
                    "samehadakuUrl": item["samehadakuUrl"],
                }
            )
    data["top10"] = {"href": "/samehadaku/top10", "samehadakuUrl": BASE_URL, "animeList": top10}

    data["batch"] = {"href": "/samehadaku/batch", "samehadakuUrl": f"{BASE_URL}/daftar-batch/", "batchList": []}
    data["movie"] = {"href": "/samehadaku/movies", "samehadakuUrl": f"{BASE_URL}/anime-movie/", "animeList": []}

    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": data})

# 2. SCHEDULE (FIXED)
@app.get("/anime/samehadaku/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    content = soup.find("div", class_="entry-content") or soup.find("main") or soup

    days_res = []
    for eng_day, labels in DAY_LABELS.items():
        anime_list = []

        header = find_day_header(content, labels)

        # fallback: cari section berdasar id/class yang mengandung nama hari
        section = None
        if not header:
            for lab in labels:
                section = content.find(
                    lambda t: getattr(t, "get", None)
                    and (
                        (t.get("id") and normalize_day(t.get("id")) == normalize_day(lab))
                        or (
                            t.get("class")
                            and any(normalize_day(c) == normalize_day(lab) for c in (t.get("class") or []))
                        )
                    )
                )
                if section:
                    break

        if header:
            cur = header.find_next_sibling()
            while cur and not is_day_header(cur):
                candidates = cur.select("li, div") if hasattr(cur, "select") else []
                if not candidates:
                    candidates = [cur]

                for c in candidates:
                    if getattr(c, "find", None) and c.find("a", href=re.compile(r"/anime/")):
                        it = parse_schedule_item(c)
                        if it:
                            anime_list.append(it)

                cur = cur.find_next_sibling()

        elif section:
            for c in section.select("li, div"):
                if c.find("a", href=re.compile(r"/anime/")):
                    it = parse_schedule_item(c)
                    if it:
                        anime_list.append(it)

        # dedup by animeId
        seen = set()
        final = []
        for x in anime_list:
            if x["animeId"] not in seen:
                seen.add(x["animeId"])
                final.append(x)

        days_res.append({"day": eng_day, "animeList": final})

    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"days": days_res}})

# 3. LISTS
@app.get("/anime/samehadaku/latest")
def get_latest(page: int = 1):
    url = f"{BASE_URL}/anime-terbaru/page/{page}/" if page > 1 else f"{BASE_URL}/anime-terbaru/"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    results = []
    nodes = soup.select(".post-show li") or soup.select(".animepost")
    for n in nodes:
        p = parse_latest_item(n)
        if p:
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

@app.get("/anime/samehadaku/ongoing")
def get_ongoing(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Currently+Airing&order=update" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Currently+Airing&order=update"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for n in nodes:
        p = parse_library_item(n, "Ongoing")
        if p:
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

@app.get("/anime/samehadaku/completed")
def get_completed(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?status=Finished+Airing&order=latest" if page > 1 else f"{BASE_URL}/daftar-anime-2/?status=Finished+Airing&order=latest"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for n in nodes:
        p = parse_library_item(n, "Completed")
        if p:
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

# 4. DETAIL ANIME
@app.get("/anime/samehadaku/anime/{anime_id}")
def get_anime_detail(anime_id: str):
    soup = get_soup(f"{BASE_URL}/anime/{anime_id}/")
    if not soup:
        return JSONResponse({"status": "failed"}, 404)

    try:
        raw_title = soup.find("h1", class_="entry-title").get_text(strip=True)
        _ = raw_title.replace("Sub Indo", "").replace("Nonton Anime", "").strip()

        poster = extract_poster(soup.find("div", class_="thumb"))

        # Info Parsing
        infos = {}
        for spe in soup.select(".infox .spe span"):
            txt = spe.get_text(":", strip=True)
            if ":" in txt:
                k, v = txt.split(":", 1)
                infos[k.strip().lower()] = v.strip()

        score_val = infos.get("score", "?")
        if score_val == "?":
            sc = soup.find("span", itemprop="ratingValue")
            if sc:
                score_val = sc.get_text(strip=True)

        rating_count = soup.find("span", itemprop="ratingCount")
        users = f"{rating_count.get_text(strip=True)} users" if rating_count else "N/A"

        ep_val = infos.get("total episode", "0")
        episodes_int = int(ep_val) if ep_val.isdigit() else None

        synopsis_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        paragraphs = []
        if synopsis_div:
            ps = synopsis_div.find_all("p")
            if ps:
                paragraphs = [p.get_text(strip=True) for p in ps if p.get_text(strip=True)]
            else:
                paragraphs = [synopsis_div.get_text(strip=True)]

        # Episode List (clean)
        episodes = []
        for li in soup.select(".lstepsiode li"):
            a = li.find("a")
            if a:
                ep_id = extract_id(a["href"])
                raw_ep_title = li.find("span", class_="epl-title").get_text(strip=True) if li.find("span", class_="epl-title") else a.get_text(strip=True)
                try:
                    t_num = int(re.search(r"\d+", raw_ep_title).group())
                except:
                    t_num = raw_ep_title

                episodes.append(
                    {"title": t_num, "episodeId": ep_id, "href": f"/samehadaku/episode/{ep_id}", "samehadakuUrl": a["href"]}
                )

        trailer_iframe = soup.select_one(".trailer-anime iframe")
        trailer_url = trailer_iframe.get("src", "") if trailer_iframe else ""

        data = {
            "title": "",  # sesuai request lu: title kosong
            "poster": poster,
            "score": {"value": score_val, "users": users},
            "japanese": infos.get("japanese", "-"),
            "synonyms": infos.get("synonyms", "-"),
            "english": infos.get("english", "-"),
            "status": infos.get("status", "Unknown"),
            "type": infos.get("type", "TV"),
            "source": infos.get("source", "-"),
            "duration": infos.get("duration", "-"),
            "episodes": episodes_int,
            "season": infos.get("season", "-"),
            "studios": infos.get("studio", "-"),
            "producers": infos.get("producers", "-"),
            "aired": infos.get("released", "-"),
            "trailer": trailer_url,
            "synopsis": {"paragraphs": paragraphs, "connections": []},
            "genreList": parse_genre_list(soup.find("div", class_="genre-info")),
            "batchList": [],
            "episodeList": episodes,
        }

        return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": data, "pagination": None})
    except Exception as e:
        return JSONResponse({"status": "failed", "error": str(e)}, 500)

# 5. GENRES, BATCH, MOVIES, POPULAR, SEARCH
@app.get("/anime/samehadaku/genres")
def get_all_genres():
    soup = get_soup(BASE_URL)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    genre_list = parse_genre_list(soup)
    unique = {g["genreId"]: g for g in genre_list}.values()
    final_list = sorted(list(unique), key=lambda x: x["title"])
    return JSONResponse({"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"genreList": final_list}})

@app.get("/anime/samehadaku/genres/{genre_id}")
def get_anime_by_genre(genre_id: str, page: int = 1):
    url = f"{BASE_URL}/genre/{genre_id}/page/{page}/" if page > 1 else f"{BASE_URL}/genre/{genre_id}/"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for x in nodes:
        p = parse_library_item(x)
        if p:
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

@app.get("/anime/samehadaku/search")
def search_anime(query: str, page: int = 1):
    url = f"{BASE_URL}/page/{page}/?s={query}" if page > 1 else f"{BASE_URL}/?s={query}"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for x in nodes:
        p = parse_library_item(x)
        if p:
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

@app.get("/anime/samehadaku/batch")
def get_batch_list(page: int = 1):
    url = f"{BASE_URL}/daftar-batch/page/{page}/" if page > 1 else f"{BASE_URL}/daftar-batch/"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for x in nodes:
        item = parse_library_item(x, "Completed")
        if item:
            item["batchId"] = item.pop("animeId")
            item["href"] = f"/samehadaku/batch/{item['batchId']}"
            results.append(item)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"batchList": results}, "pagination": get_pagination(soup, page)}
    )

@app.get("/anime/samehadaku/movies")
def get_movies(page: int = 1):
    url = f"{BASE_URL}/anime-movie/page/{page}/" if page > 1 else f"{BASE_URL}/anime-movie/"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for x in nodes:
        p = parse_library_item(x)
        if p:
            p["type"] = "Movie"
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

@app.get("/anime/samehadaku/popular")
def get_popular(page: int = 1):
    url = f"{BASE_URL}/daftar-anime-2/page/{page}/?order=popular" if page > 1 else f"{BASE_URL}/daftar-anime-2/?order=popular"
    soup = get_soup(url)
    if not soup:
        return JSONResponse({"status": "failed"}, 500)

    nodes = soup.select(".animepost")
    results = []
    for x in nodes:
        p = parse_library_item(x)
        if p:
            results.append(p)

    return JSONResponse(
        {"status": "success", "creator": "Sanka Vollerei", "message": "", "data": {"animeList": results}, "pagination": get_pagination(soup, page)}
    )

# 6. EPISODE STREAM + DOWNLOADS
@app.get("/anime/samehadaku/episode/{episode_id}")
def get_episode_detail(episode_id: str):
    soup = get_soup(f"{BASE_URL}/{episode_id}/")
    if not soup:
        return JSONResponse({"status": "failed"}, 404)

    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)

        nav = {"prev": None, "next": None}
        pa = soup.find("a", class_="prev")
        na = soup.find("a", class_="next")
        if pa and pa.get("href") and "/anime/" not in pa["href"]:
            nav["prev"] = f"/samehadaku/episode/{extract_id(pa['href'])}"
        if na and na.get("href") and "/anime/" not in na["href"]:
            nav["next"] = f"/samehadaku/episode/{extract_id(na['href'])}"

        downloads = []
        box = soup.find("div", class_="download-eps") or soup.find("div", id="server")
        if box:
            for ul in box.find_all("ul"):
                prev_tag = ul.find_previous(["p", "h4", "div", "span"])
                ft = prev_tag.get_text(strip=True) if prev_tag else "Unknown"

                if "MKV" in ft:
                    ft = "MKV"
                elif "MP4" in ft:
                    ft = "MP4"
                elif "x265" in ft:
                    ft = "x265"

                quals = []
                for li in ul.find_all("li"):
                    qn = li.find("strong") or li.find("b")
                    qn_txt = qn.get_text(strip=True) if qn else "Unknown"
                    urls = [{"title": a.get_text(strip=True), "url": a["href"]} for a in li.find_all("a", href=True)]
                    quals.append({"title": qn_txt, "urls": urls})

                if quals:
                    downloads.append({"title": ft, "qualities": quals})

        iframe = soup.find("iframe")
        stream = iframe.get("src", "") if iframe else ""

        return JSONResponse(
            {
                "status": "success",
                "creator": "Sanka Vollerei",
                "message": "",
                "data": {"title": title, "streamUrl": stream, "navigation": nav, "downloads": downloads},
            }
        )
    except Exception as e:
        return JSONResponse({"status": "failed", "error": str(e)}, 500)
