const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const cors = require('cors');

const app = express();
app.use(cors());

const BASE_URL = 'https://v1.samehadaku.how';

// Headers biar gak kena blok
const HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://samehadaku.how/'
};

// --- HELPERS ---

const extractId = (url) => {
    if (!url) return '';
    const parts = url.replace(/\/$/, '').split('/');
    return parts[parts.length - 1];
};

const extractPoster = ($node) => {
    const img = $node.find('img');
    let src = img.attr('src') || img.attr('data-src') || img.attr('srcset');
    if (!src) return "https://dummyimage.com/300x400/000/fff&text=No+Image";
    return src.split('?')[0];
};

const parseGenreList = ($, $node) => {
    const genres = [];
    const links = $node.find('.genres a, .genre-info a, .genre a, div.bean a');
    links.each((i, el) => {
        const href = $(el).attr('href');
        genres.push({
            title: $(el).text().trim(),
            genreId: extractId(href),
            href: `/samehadaku/genres/${extractId(href)}`,
            samehadakuUrl: href
        });
    });
    return genres;
};

const getPagination = ($, currentPage) => {
    const $pagination = $('.pagination');
    if (!$pagination.length) return null;

    let totalPages = 1;
    const pageNumbers = $pagination.find('.page-numbers');
    
    pageNumbers.each((i, el) => {
        const num = parseInt($(el).text().replace(/,/g, ''));
        if (!isNaN(num) && num > totalPages) {
            totalPages = num;
        }
    });

    const hasNext = $pagination.find('.next').length > 0;
    const hasPrev = $pagination.find('.prev').length > 0;

    return {
        currentPage: parseInt(currentPage),
        hasPrevPage: hasPrev,
        prevPage: hasPrev ? parseInt(currentPage) - 1 : null,
        hasNextPage: hasNext,
        nextPage: hasNext ? parseInt(currentPage) + 1 : null,
        totalPages: totalPages
    };
};

// --- PARSERS PER SECTION ---

// Parser untuk List Standard (Ongoing, Completed, Search)
const parseAnimeItem = ($, el, statusForce = 'Ongoing') => {
    const aTag = $(el).find('a').first();
    if (!aTag.length) return null;

    const href = aTag.attr('href');
    const title = $(el).find('.title').text().trim() || aTag.attr('title');
    const poster = extractPoster($(el));
    const score = $(el).find('.score').text().trim() || '?';
    const type = $(el).find('.type').text().trim() || 'TV';
    const id = extractId(href);

    return {
        title,
        poster,
        type,
        score,
        status: statusForce,
        animeId: id,
        href: `/samehadaku/anime/${id}`,
        samehadakuUrl: href,
        genreList: parseGenreList($, $(el))
    };
};

// Parser untuk Latest/Home (Butuh Episode & Date)
const parseLatestItem = ($, el) => {
    const aTag = $(el).find('a').first();
    if (!aTag.length) return null;

    const href = aTag.attr('href');
    const title = $(el).find('.title').text().trim() || aTag.attr('title');
    const poster = extractPoster($(el));
    const id = extractId(href);

    let ep = '?';
    const epTag = $(el).find('.episode, .dtla, .author');
    if (epTag.length) {
        const txt = epTag.text().trim();
        if (txt.includes('Episode')) {
            ep = txt.replace('Episode', '').trim();
        } else {
            const match = txt.match(/\d+/);
            if (match) ep = match[0];
        }
    }

    let released = '?';
    const dateTag = $(el).find('.date, .year');
    if (dateTag.length) {
        released = dateTag.text().trim();
    } else {
        const meta = $(el).find('.meta');
        if (meta.length) released = meta.text().trim();
    }

    return {
        title,
        poster,
        episodes: ep,
        releasedOn: released,
        animeId: id,
        href: `/samehadaku/anime/${id}`,
        samehadakuUrl: href
    };
};

// --- ROUTES ---

app.get('/', (req, res) => {
    res.json({ message: "Samehadaku API (Node.js/Cheerio) is Ready" });
});

// 1. HOME
app.get('/anime/samehadaku/home', async (req, res) => {
    try {
        const { data } = await axios.get(BASE_URL, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const recent = [];
        const nodes = $('.post-show li').length ? $('.post-show li') : $('.animepost').slice(0, 10);
        
        nodes.each((i, el) => {
            const item = parseLatestItem($, el);
            if (item) recent.push(item);
        });

        const top10 = [];
        const topNodes = $('.widget_senction.popular .serieslist li, .serieslist.pop li');
        topNodes.each((i, el) => {
            const parsed = parseAnimeItem($, el);
            if (parsed) {
                top10.push({
                    rank: i + 1,
                    title: parsed.title,
                    poster: parsed.poster,
                    score: parsed.score,
                    animeId: parsed.animeId,
                    href: parsed.href,
                    samehadakuUrl: parsed.samehadakuUrl
                });
            }
        });

        res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: {
                recent: { href: "/samehadaku/recent", samehadakuUrl: `${BASE_URL}/anime-terbaru/`, animeList: recent },
                top10: { href: "/samehadaku/top10", samehadakuUrl: BASE_URL, animeList: top10 },
                batch: { href: "/samehadaku/batch", samehadakuUrl: `${BASE_URL}/daftar-batch/`, batchList: [] },
                movie: { href: "/samehadaku/movies", samehadakuUrl: `${BASE_URL}/anime-movie/`, animeList: [] }
            }
        });
    } catch (e) {
        res.status(500).json({ status: "failed", message: e.message });
    }
});

// 2. SCHEDULE (FIXED: ID SEARCH + ESTIMATION)
app.get('/anime/samehadaku/schedule', async (req, res) => {
    try {
        const { data } = await axios.get(`${BASE_URL}/jadwal-rilis/`, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const dayMap = [
            { eng: "Monday", indo: "senin" },
            { eng: "Tuesday", indo: "selasa" },
            { eng: "Wednesday", indo: "rabu" },
            { eng: "Thursday", indo: "kamis" },
            { eng: "Friday", indo: "jumat" },
            { eng: "Saturday", indo: "sabtu" },
            { eng: "Sunday", indo: "minggu" }
        ];

        const daysResult = [];
        const content = $('.entry-content, main').first();

        for (const { eng, indo } of dayMap) {
            let animeList = [];
            
            // Logic: Cari Tab Pane berdasarkan ID atau Class
            // Samehadaku sering pake <div id="senin"> atau <div class="tab-pane" id="senin">
            let container = content.find(`#${indo}`);
            if (!container.length) container = content.find(`.${indo}`);
            
            // Fallback: Cari header text jika ID ga ketemu
            if (!container.length) {
                content.find('h3, h4, b').each((i, el) => {
                    if ($(el).text().toLowerCase().includes(indo)) {
                        // Cari sibling terdekat yang punya animepost
                        let next = $(el).next();
                        for (let k = 0; k < 3; k++) {
                            if (next.find('.animepost, li a').length) {
                                container = next;
                                return false; // break loop
                            }
                            next = next.next();
                        }
                    }
                });
            }

            if (container.length) {
                const items = container.find('.animepost, li');
                items.each((i, el) => {
                    const parsed = parseAnimeItem($, el); // Reuse parser
                    if (parsed && parsed.samehadakuUrl.includes('/anime/')) {
                        // Ganti status dengan estimation time
                        delete parsed.status;
                        
                        let est = "Update";
                        const timeTag = $(el).find('.time, .btime');
                        if (timeTag.length) {
                            est = timeTag.text().trim();
                        } else {
                            // Gali tooltip
                            const tooltip = $(el).find('.ttls, .dtla').text();
                            const timeMatch = tooltip.match(/(?:Pukul|Jam|Time|Rilis)\s*:\s*([\d\:]+)/i);
                            if (timeMatch) est = timeMatch[1].trim();
                        }
                        
                        parsed.estimation = est;
                        
                        // Cek duplikat
                        if (!animeList.find(x => x.title === parsed.title)) {
                            animeList.push(parsed);
                        }
                    }
                });
            }

            daysResult.push({ day: eng, animeList });
        }

        res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { days: daysResult },
            pagination: null
        });

    } catch (e) {
        res.status(500).json({ status: "failed", message: e.message });
    }
});

// 3. LATEST (PAGINATION)
app.get('/anime/samehadaku/latest', async (req, res) => {
    try {
        const page = req.query.page || 1;
        const url = page > 1 ? `${BASE_URL}/anime-terbaru/page/${page}/` : `${BASE_URL}/anime-terbaru/`;
        
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const animeList = [];
        $('.post-show li, .animepost').each((i, el) => {
            const item = parseLatestItem($, el);
            if (item) animeList.push(item);
        });

        res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { animeList },
            pagination: getPagination($, page)
        });
    } catch (e) {
        res.status(500).json({ status: "failed", message: e.message });
    }
});

// 4. ONGOING & COMPLETED
app.get('/anime/samehadaku/ongoing', async (req, res) => {
    try {
        const page = req.query.page || 1;
        const url = page > 1 
            ? `${BASE_URL}/daftar-anime-2/page/${page}/?status=Currently+Airing&order=update`
            : `${BASE_URL}/daftar-anime-2/?status=Currently+Airing&order=update`;
            
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const animeList = [];
        $('.animepost').each((i, el) => {
            const item = parseAnimeItem($, el, 'Ongoing');
            if (item) animeList.push(item);
        });

        res.json({
            status: "success", creator: "Sanka Vollerei", message: "",
            data: { animeList }, pagination: getPagination($, page)
        });
    } catch (e) { res.status(500).json({ status: "failed" }); }
});

app.get('/anime/samehadaku/completed', async (req, res) => {
    try {
        const page = req.query.page || 1;
        const url = page > 1 
            ? `${BASE_URL}/daftar-anime-2/page/${page}/?status=Finished+Airing&order=latest`
            : `${BASE_URL}/daftar-anime-2/?status=Finished+Airing&order=latest`;
            
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const animeList = [];
        $('.animepost').each((i, el) => {
            const item = parseAnimeItem($, el, 'Completed');
            if (item) animeList.push(item);
        });

        res.json({
            status: "success", creator: "Sanka Vollerei", message: "",
            data: { animeList }, pagination: getPagination($, page)
        });
    } catch (e) { res.status(500).json({ status: "failed" }); }
});

// 5. GENRES
app.get('/anime/samehadaku/genres', async (req, res) => {
    try {
        const { data } = await axios.get(BASE_URL, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const genreList = [];
        const seen = new Set();
        
        $('a[href*="/genre/"]').each((i, el) => {
            const href = $(el).attr('href');
            if (!seen.has(href)) {
                const title = $(el).text().split('(')[0].trim();
                const id = extractId(href);
                if (id) {
                    genreList.push({
                        title, genreId: id, href: `/samehadaku/genres/${id}`, samehadakuUrl: href
                    });
                    seen.add(href);
                }
            }
        });
        
        genreList.sort((a, b) => a.title.localeCompare(b.title));
        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { genreList } });
    } catch (e) { res.status(500).json({ status: "failed" }); }
});

app.get('/anime/samehadaku/genres/:id', async (req, res) => {
    try {
        const page = req.query.page || 1;
        const { id } = req.params;
        const url = page > 1 ? `${BASE_URL}/genre/${id}/page/${page}/` : `${BASE_URL}/genre/${id}/`;
        
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const animeList = [];
        $('.animepost').each((i, el) => {
            const item = parseAnimeItem($, el);
            if (item) animeList.push(item);
        });

        res.json({
            status: "success", creator: "Sanka Vollerei", message: "",
            data: { animeList }, pagination: getPagination($, page)
        });
    } catch (e) { res.status(500).json({ status: "failed" }); }
});

// 6. DETAIL ANIME (JSON STRUCTURE MATCH)
app.get('/anime/samehadaku/anime/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const { data } = await axios.get(`${BASE_URL}/anime/${id}/`, { headers: HEADERS });
        const $ = cheerio.load(data);

        // Clean Title
        let title = $('h1.entry-title').text().trim();
        title = title.replace(/Nonton Anime|Sub Indo/gi, '').trim();
        
        // Agar sesuai request (title kosong di string) jika mau, atau isi title. 
        // Saya isi title normal, kalau mau kosong ganti jadi "".
        const titleResponse = ""; 

        const poster = extractPoster($('.thumb'));
        
        // Metadata Parsing
        const infos = {};
        $('.infox .spe span').each((i, el) => {
            const text = $(el).text();
            const parts = text.split(':');
            if (parts.length > 1) {
                const k = parts[0].trim().toLowerCase();
                const v = parts.slice(1).join(':').trim();
                infos[k] = v;
            }
        });

        const scoreVal = infos['score'] || $('.ratingValue').text().trim() || '?';
        const userCount = $('span[itemprop="ratingCount"]').text().trim();
        const users = userCount ? `${userCount} users` : 'N/A';

        const paragraphs = [];
        const descDiv = $('.desc, .entry-content').first();
        descDiv.find('p').each((i, el) => {
            if ($(el).text().trim()) paragraphs.push($(el).text().trim());
        });
        if (paragraphs.length === 0 && descDiv.text().trim()) paragraphs.push(descDiv.text().trim());

        const episodes = [];
        $('.lstepsiode li').each((i, el) => {
            const a = $(el).find('a');
            const href = a.attr('href');
            const epId = extractId(href);
            const rawTitle = $(el).find('.epl-title').text().trim() || a.text().trim();
            
            // Extract number from "Episode 3" -> 3
            let epNum = rawTitle;
            const match = rawTitle.match(/\d+/);
            if (match) epNum = parseInt(match[0]);

            episodes.push({
                title: epNum,
                episodeId: epId,
                href: `/samehadaku/episode/${epId}`,
                samehadakuUrl: href
            });
        });

        // Genres
        const genreList = parseGenreList($, $('.genre-info'));

        const respData = {
            title: titleResponse, // Kosong sesuai request
            poster,
            score: { value: scoreVal, users },
            japanese: infos['japanese'] || '-',
            synonyms: infos['synonyms'] || '-',
            english: infos['english'] || '-',
            status: infos['status'] || 'Unknown',
            type: infos['type'] || 'TV',
            source: infos['source'] || '-',
            duration: infos['duration'] || '-',
            episodes: parseInt(infos['total episode']) || null,
            season: infos['season'] || '-',
            studios: infos['studio'] || '-',
            producers: infos['producers'] || '-',
            aired: infos['released'] || '-',
            trailer: $('.trailer-anime iframe').attr('src') || "",
            synopsis: { paragraphs, connections: [] }, // Connections placeholder
            genreList,
            batchList: [],
            episodeList: episodes
        };

        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: respData, pagination: null });

    } catch (e) {
        res.status(404).json({ status: "failed", message: "Not found" });
    }
});

// 7. EPISODE DOWNLOADS
app.get('/anime/samehadaku/episode/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const { data } = await axios.get(`${BASE_URL}/${id}/`, { headers: HEADERS });
        const $ = cheerio.load(data);

        const title = $('h1.entry-title').text().trim();
        const iframe = $('iframe').attr('src') || "";
        
        const prevHref = $('.prev').attr('href');
        const nextHref = $('.next').attr('href');
        
        const nav = {
            prev: (prevHref && !prevHref.includes('/anime/')) ? `/samehadaku/episode/${extractId(prevHref)}` : null,
            next: (nextHref && !nextHref.includes('/anime/')) ? `/samehadaku/episode/${extractId(nextHref)}` : null
        };

        const downloads = [];
        const downloadBox = $('.download-eps, #server');
        
        if (downloadBox.length) {
            downloadBox.find('ul').each((i, ul) => {
                // Cari header format (MKV/MP4) di element sebelumnya
                let formatTitle = "Unknown";
                let prev = $(ul).prev();
                while(prev.length && !['p', 'h4', 'div', 'span'].includes(prev.prop('tagName').toLowerCase())) {
                    prev = prev.prev();
                }
                if (prev.length) formatTitle = prev.text().trim();

                // Normalize Title
                if (formatTitle.includes('MKV')) formatTitle = 'MKV';
                else if (formatTitle.includes('MP4')) formatTitle = 'MP4';
                else if (formatTitle.includes('x265')) formatTitle = 'x265';

                const qualities = [];
                $(ul).find('li').each((j, li) => {
                    const qName = $(li).find('strong, b').text().trim() || 'Unknown';
                    const urls = [];
                    $(li).find('a').each((k, a) => {
                        urls.push({ title: $(a).text().trim(), url: $(a).attr('href') });
                    });
                    qualities.push({ title: qName, urls });
                });

                if (qualities.length) {
                    downloads.push({ title: formatTitle, qualities });
                }
            });
        }

        res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: {
                title,
                streamUrl: iframe,
                navigation: nav,
                downloads
            }
        });

    } catch (e) {
        res.status(404).json({ status: "failed", message: "Not found" });
    }
});

// OTHER ROUTES (Search, Batch, Movie, Popular) - Standard Parser
const createListEndpoint = (urlBuilder) => async (req, res) => {
    try {
        const page = req.query.page || 1;
        const url = urlBuilder(page, req.query);
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const animeList = [];
        $('.animepost').each((i, el) => {
            const item = parseAnimeItem($, el);
            if (item) animeList.push(item);
        });

        res.json({
            status: "success", creator: "Sanka Vollerei", message: "",
            data: { animeList }, pagination: getPagination($, page)
        });
    } catch (e) { res.status(500).json({ status: "failed" }); }
};

app.get('/anime/samehadaku/search', createListEndpoint((p, q) => p > 1 ? `${BASE_URL}/page/${p}/?s=${q.s}` : `${BASE_URL}/?s=${q.s}`));
app.get('/anime/samehadaku/batch', createListEndpoint(p => p > 1 ? `${BASE_URL}/daftar-batch/page/${p}/` : `${BASE_URL}/daftar-batch/`));
app.get('/anime/samehadaku/movies', createListEndpoint(p => p > 1 ? `${BASE_URL}/anime-movie/page/${p}/` : `${BASE_URL}/anime-movie/`));
app.get('/anime/samehadaku/popular', createListEndpoint(p => p > 1 ? `${BASE_URL}/daftar-anime-2/page/${p}/?order=popular` : `${BASE_URL}/daftar-anime-2/?order=popular`));

// Export for Vercel
module.exports = app;
