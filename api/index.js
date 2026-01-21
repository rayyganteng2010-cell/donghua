const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const cors = require('cors');
const crypto = require('crypto');

const app = express();
app.use(cors());

// Multiple base URLs untuk fallback
const BASE_URLS = [
    'https://samehadaku.how',
    'https://samehadaku.be',
    'https://samehadaku.rest'
];

// Rotasi User-Agent secara acak
const USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
];

// Helper untuk mendapatkan headers dengan rotasi
const getRandomHeaders = () => {
    const randomUA = USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
    const timestamp = Date.now();
    
    return {
        'User-Agent': randomUA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Referer': BASE_URLS[0],
        'X-Requested-With': 'XMLHttpRequest',
        'X-Timestamp': timestamp.toString()
    };
};

// Fungsi untuk mencoba multiple URLs dengan retry
const fetchWithRetry = async (path, retries = 3, delay = 1000) => {
    const endpoints = BASE_URLS.map(base => `${base}${path}`);
    
    for (let attempt = 0; attempt < retries; attempt++) {
        for (const endpoint of endpoints) {
            try {
                console.log(`Attempt ${attempt + 1}: Fetching ${endpoint}`);
                
                const headers = getRandomHeaders();
                const response = await axios({
                    method: 'GET',
                    url: endpoint,
                    headers: headers,
                    timeout: 10000,
                    validateStatus: (status) => status < 500,
                    // Tambahkan proxy jika diperlukan (opsional)
                    // proxy: {
                    //     protocol: 'http',
                    //     host: 'your-proxy-host',
                    //     port: 8080
                    // }
                });

                if (response.status === 200) {
                    console.log(`Success: ${endpoint}`);
                    return cheerio.load(response.data);
                }
                
                if (response.status === 403 || response.status === 429) {
                    console.log(`Blocked (${response.status}): ${endpoint}`);
                    // Delay sebelum mencoba lagi
                    await new Promise(resolve => setTimeout(resolve, delay * (attempt + 1)));
                    continue;
                }
                
            } catch (error) {
                console.log(`Error fetching ${endpoint}:`, error.message);
                if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
                    await new Promise(resolve => setTimeout(resolve, delay));
                }
                continue;
            }
        }
    }
    
    return null;
};

// Helper functions
const extractId = (url) => {
    if (!url) return '';
    const parts = url.replace(/\/$/, '').split('/');
    return parts[parts.length - 1] || parts[parts.length - 2] || '';
};

const extractPoster = ($node) => {
    const img = $node.find('img');
    let src = img.attr('src') || img.attr('data-src') || img.attr('srcset');
    
    if (src) {
        if (src.includes(',')) {
            src = src.split(',')[0].trim();
        }
        src = src.split('?')[0];
        
        // Konversi URL relatif ke absolut
        if (src.startsWith('//')) {
            src = 'https:' + src;
        } else if (src.startsWith('/')) {
            src = BASE_URLS[0] + src;
        }
        
        return src;
    }
    
    return "https://dummyimage.com/300x400/1a1a2e/ff4757&text=No+Image";
};

// Cache sederhana untuk mengurangi request
const cache = new Map();
const CACHE_DURATION = 5 * 60 * 1000; // 5 menit

const getCached = (key) => {
    const item = cache.get(key);
    if (item && Date.now() - item.timestamp < CACHE_DURATION) {
        return item.data;
    }
    return null;
};

const setCached = (key, data) => {
    cache.set(key, {
        timestamp: Date.now(),
        data: data
    });
};

// ROUTES

app.get('/', (req, res) => {
    res.json({ 
        message: "Samehadaku Proxy API",
        version: "1.0.0",
        status: "running",
        endpoints: [
            "/anime/samehadaku/schedule",
            "/anime/samehadaku/anime/:id",
            "/anime/samehadaku/episode/:id",
            "/anime/samehadaku/search?q=query",
            "/anime/samehadaku/latest",
            "/anime/samehadaku/ongoing",
            "/anime/samehadaku/popular"
        ]
    });
});

// 1. SCHEDULE - Endpoint utama yang diminta
app.get('/anime/samehadaku/schedule', async (req, res) => {
    const cacheKey = 'schedule';
    const cached = getCached(cacheKey);
    
    if (cached) {
        return res.json(cached);
    }
    
    const $ = await fetchWithRetry('/jadwal-rilis/');
    if (!$) {
        return res.status(500).json({ 
            status: "error", 
            creator: "Sanka Vollerei", 
            message: "Gagal mengakses jadwal anime",
            data: { days: [] }
        });
    }
    
    const dayMap = [
        { eng: "Monday", idn: "senin", selector: "#senin, .senin, [id*='senin'], [class*='senin']" },
        { eng: "Tuesday", idn: "selasa", selector: "#selasa, .selasa, [id*='selasa'], [class*='selasa']" },
        { eng: "Wednesday", idn: "rabu", selector: "#rabu, .rabu, [id*='rabu'], [class*='rabu']" },
        { eng: "Thursday", idn: "kamis", selector: "#kamis, .kamis, [id*='kamis'], [class*='kamis']" },
        { eng: "Friday", idn: "jumat", selector: "#jumat, .jumat, [id*='jumat'], [class*='jumat']" },
        { eng: "Saturday", idn: "sabtu", selector: "#sabtu, .sabtu, [id*='sabtu'], [class*='sabtu']" },
        { eng: "Sunday", idn: "minggu", selector: "#minggu, .minggu, [id*='minggu'], [class*='minggu']" }
    ];
    
    const days = [];
    const content = $('article, .entry-content, main, .schedule-container').first();
    
    for (const day of dayMap) {
        let animeList = [];
        
        // Cari elemen berdasarkan selector
        let container = content.find(day.selector);
        
        // Jika tidak ditemukan, cari berdasarkan teks
        if (!container.length) {
            content.find('h2, h3, h4, strong, b').each((i, el) => {
                if ($(el).text().toLowerCase().includes(day.idn)) {
                    let nextEl = $(el).next();
                    for (let j = 0; j < 3 && nextEl.length; j++) {
                        if (nextEl.find('.animepost, .bsx, .bs').length) {
                            container = nextEl;
                            break;
                        }
                        nextEl = nextEl.next();
                    }
                }
            });
        }
        
        if (container.length) {
            container.find('.animepost, .bsx, .bs, li').each((i, el) => {
                const link = $(el).find('a').attr('href');
                if (link && link.includes('/anime/')) {
                    const animeId = extractId(link);
                    const title = $(el).find('.tt, .title').text().trim() || 
                                 $(el).find('a').attr('title') || 
                                 "Unknown Title";
                    
                    const poster = extractPoster($(el));
                    const type = $(el).find('.type').text().trim() || 'TV';
                    const score = $(el).find('.score, .rating').text().trim() || '0.0';
                    const genres = $(el).find('.genres').text().trim() || 'Unknown';
                    
                    // Estimasi waktu rilis
                    let estimation = "Update";
                    const timeText = $(el).find('.time, .btime, .dtla').text();
                    if (timeText) {
                        const timeMatch = timeText.match(/(\d+)\s*(jam|hour|h)/i);
                        if (timeMatch) {
                            const hours = parseInt(timeMatch[1]);
                            estimation = `${hours}h`;
                        } else if (timeText.includes('d') || timeText.includes('hari')) {
                            estimation = timeText.trim();
                        }
                    }
                    
                    animeList.push({
                        title: title,
                        poster: poster,
                        type: type,
                        score: parseFloat(score) || 0.0,
                        estimation: estimation,
                        genres: genres,
                        animeId: animeId,
                        href: `/samehadaku/anime/${animeId}`,
                        samehadakuUrl: link.startsWith('http') ? link : `${BASE_URLS[0]}${link}`
                    });
                }
            });
        }
        
        days.push({
            day: day.eng,
            animeList: animeList.slice(0, 15) // Batasi jumlah anime per hari
        });
    }
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: { days }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 2. DETAIL ANIME
app.get('/anime/samehadaku/anime/:id', async (req, res) => {
    const { id } = req.params;
    const cacheKey = `anime_${id}`;
    const cached = getCached(cacheKey);
    
    if (cached) {
        return res.json(cached);
    }
    
    const $ = await fetchWithRetry(`/anime/${id}/`);
    if (!$) {
        return res.status(404).json({
            status: "error",
            creator: "Sanka Vollerei",
            message: "Anime tidak ditemukan",
            data: null
        });
    }
    
    // Parse informasi anime
    const title = $('h1.entry-title').text().trim();
    const poster = extractPoster($('.thumb, .anime-poster'));
    
    // Informasi detail
    const info = {};
    $('.spe span').each((i, el) => {
        const text = $(el).text().trim();
        const parts = text.split(':');
        if (parts.length >= 2) {
            const key = parts[0].trim().toLowerCase().replace(/\s+/g, '_');
            const value = parts.slice(1).join(':').trim();
            info[key] = value;
        }
    });
    
    // Rating
    const scoreValue = $('.ratingValue').text().trim() || info.score || '0.0';
    const ratingCount = $('span[itemprop="ratingCount"]').text().trim() || '0';
    
    // Sinopsis
    const paragraphs = [];
    $('.entry-content p, .desc p').each((i, el) => {
        const text = $(el).text().trim();
        if (text && text.length > 20) {
            paragraphs.push(text);
        }
    });
    
    // Genre list
    const genreList = [];
    $('.genre-info a, a[href*="/genre/"]').each((i, el) => {
        const href = $(el).attr('href');
        const genreId = extractId(href);
        if (genreId && genreId !== '') {
            genreList.push({
                title: $(el).text().trim(),
                genreId: genreId,
                href: `/samehadaku/genres/${genreId}`,
                samehadakuUrl: href.startsWith('http') ? href : `${BASE_URLS[0]}${href}`
            });
        }
    });
    
    // Episode list
    const episodeList = [];
    $('.lstepsiode li, .episodelist li').each((i, el) => {
        const link = $(el).find('a').attr('href');
        if (link && link.includes('episode-')) {
            const episodeId = extractId(link);
            const episodeNum = $(el).find('.epl-num').text().trim() || 
                              $(el).find('.episode-num').text().trim() ||
                              `${i + 1}`;
            
            episodeList.push({
                title: parseInt(episodeNum) || episodeNum,
                episodeId: episodeId,
                href: `/samehadaku/episode/${episodeId}`,
                samehadakuUrl: link.startsWith('http') ? link : `${BASE_URLS[0]}${link}`
            });
        }
    });
    
    // Batch list
    const batchList = [];
    $('a[href*="/batch/"]').each((i, el) => {
        const href = $(el).attr('href');
        const batchId = extractId(href);
        if (batchId) {
            batchList.push({
                title: $(el).text().trim() || `Batch ${i + 1}`,
                batchId: batchId,
                href: `/samehadaku/batch/${batchId}`,
                samehadakuUrl: href.startsWith('http') ? href : `${BASE_URLS[0]}${href}`
            });
        }
    });
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: {
            title: title,
            poster: poster,
            score: {
                value: parseFloat(scoreValue) || 0.0,
                users: ratingCount
            },
            japanese: info.japanese || info.japanese_title || '-',
            synonyms: info.synonyms || info.alternative_title || '-',
            english: info.english || info.english_title || title,
            status: info.status || 'Unknown',
            type: info.type || 'TV',
            source: info.source || '-',
            duration: info.duration || '24 min.',
            episodes: parseInt(info.total_episode) || episodeList.length || null,
            season: info.season || '-',
            studios: info.studio || info.studios || '-',
            producers: info.producers || '-',
            aired: info.aired || info.released || '-',
            trailer: $('iframe[src*="youtube"]').attr('src') || '',
            synopsis: {
                paragraphs: paragraphs.length ? paragraphs : ["Sinopsis tidak tersedia."],
                connections: []
            },
            genreList: genreList.slice(0, 10),
            batchList: batchList.slice(0, 5),
            episodeList: episodeList.slice(0, 30).reverse() // Episode terbaru pertama
        }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 3. DETAIL EPISODE
app.get('/anime/samehadaku/episode/:id', async (req, res) => {
    const { id } = req.params;
    const cacheKey = `episode_${id}`;
    const cached = getCached(cacheKey);
    
    if (cached) {
        return res.json(cached);
    }
    
    const $ = await fetchWithRetry(`/${id}/`);
    if (!$) {
        return res.status(404).json({
            status: "error",
            creator: "Sanka Vollerei",
            message: "Episode tidak ditemukan",
            data: null
        });
    }
    
    // Judul episode
    const title = $('h1.entry-title').text().trim();
    
    // Poster anime
    const poster = extractPoster($('.anime-thumb, .thumb'));
    
    // URL streaming default (iframe)
    const defaultStreamingUrl = $('iframe').attr('src') || '';
    
    // Navigasi episode
    const prevLink = $('.prev a').attr('href');
    const nextLink = $('.next a').attr('href');
    
    const hasPrevEpisode = !!prevLink && !prevLink.includes('/anime/');
    const hasNextEpisode = !!nextLink && !nextLink.includes('/anime/');
    
    // Sinopsis
    const synopsisParagraphs = [];
    $('.entry-content p').each((i, el) => {
        const text = $(el).text().trim();
        if (text && !text.includes('DOWNLOAD') && !text.includes('Streaming')) {
            synopsisParagraphs.push(text);
        }
    });
    
    // Genre list
    const genreList = [];
    $('a[href*="/genre/"]').each((i, el) => {
        const href = $(el).attr('href');
        const genreId = extractId(href);
        if (genreId) {
            genreList.push({
                title: $(el).text().trim(),
                genreId: genreId,
                href: `/samehadaku/genres/${genreId}`,
                samehadakuUrl: href.startsWith('http') ? href : `${BASE_URLS[0]}${href}`
            });
        }
    });
    
    // Server streaming (qualities)
    const qualities = [];
    const serverSections = $('.dlbod, .download-eps, .mirrorstream');
    
    if (serverSections.length) {
        serverSections.each((i, section) => {
            const qualityTitle = $(section).find('strong, b, h4').first().text().trim() || 'unknown';
            
            const serverList = [];
            $(section).find('a').each((j, a) => {
                const serverTitle = $(a).text().trim();
                const href = $(a).attr('href');
                if (href && !href.includes('javascript')) {
                    const serverId = crypto.randomBytes(4).toString('hex');
                    serverList.push({
                        title: serverTitle,
                        serverId: serverId,
                        href: `/samehadaku/server/${serverId}`,
                        streamUrl: href
                    });
                }
            });
            
            if (serverList.length > 0) {
                qualities.push({
                    title: qualityTitle,
                    serverList: serverList
                });
            }
        });
    } else {
        // Fallback: buat server default
        qualities.push({
            title: "Default",
            serverList: [{
                title: "Default Stream",
                serverId: "default",
                href: "/samehadaku/server/default",
                streamUrl: defaultStreamingUrl
            }]
        });
    }
    
    // Download links
    const formats = [];
    const downloadSections = $('.download-list, .download-links');
    
    if (downloadSections.length) {
        downloadSections.each((i, section) => {
            const formatTitle = $(section).find('strong, b').first().text().trim() || 'MKV';
            
            const qualityGroups = [];
            $(section).find('li, .download-item').each((j, item) => {
                const qualityTitle = $(item).find('strong, .quality').text().trim() || `${j+1}80p`;
                
                const urls = [];
                $(item).find('a').each((k, a) => {
                    urls.push({
                        title: $(a).text().trim() || `Server ${k+1}`,
                        url: $(a).attr('href')
                    });
                });
                
                if (urls.length > 0) {
                    qualityGroups.push({
                        title: qualityTitle,
                        urls: urls
                    });
                }
            });
            
            if (qualityGroups.length > 0) {
                formats.push({
                    title: formatTitle,
                    qualities: qualityGroups
                });
            }
        });
    }
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: {
            title: title,
            animeId: id.split('-episode-')[0] || id,
            poster: poster,
            releasedOn: $('.date').text().trim() || 'Unknown',
            defaultStreamingUrl: defaultStreamingUrl,
            hasPrevEpisode: hasPrevEpisode,
            prevEpisode: hasPrevEpisode ? {
                title: "Prev",
                episodeId: extractId(prevLink),
                href: `/samehadaku/episode/${extractId(prevLink)}`,
                samehadakuUrl: prevLink.startsWith('http') ? prevLink : `${BASE_URLS[0]}${prevLink}`
            } : null,
            hasNextEpisode: hasNextEpisode,
            nextEpisode: hasNextEpisode ? {
                title: "Next",
                episodeId: extractId(nextLink),
                href: `/samehadaku/episode/${extractId(nextLink)}`,
                samehadakuUrl: nextLink.startsWith('http') ? nextLink : `${BASE_URLS[0]}${nextLink}`
            } : null,
            synopsis: {
                paragraphs: synopsisParagraphs.length ? synopsisParagraphs : ["Sinopsis tidak tersedia."],
                connections: []
            },
            genreList: genreList.slice(0, 10),
            server: {
                qualities: qualities
            },
            downloadUrl: {
                formats: formats.length ? formats : [
                    {
                        title: "MKV",
                        qualities: [
                            {
                                title: "360p",
                                urls: [
                                    { title: "Default Download", url: "#" }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 4. SEARCH ANIME
app.get('/anime/samehadaku/search', async (req, res) => {
    const { q, page = 1 } = req.query;
    
    if (!q || q.trim() === '') {
        return res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { animeList: [] },
            pagination: { currentPage: 1, hasNextPage: false }
        });
    }
    
    const cacheKey = `search_${q}_${page}`;
    const cached = getCached(cacheKey);
    
    if (cached) {
        return res.json(cached);
    }
    
    const encodedQuery = encodeURIComponent(q);
    const $ = await fetchWithRetry(`/page/${page}/?s=${encodedQuery}`);
    
    if (!$) {
        return res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { animeList: [] },
            pagination: { currentPage: parseInt(page), hasNextPage: false }
        });
    }
    
    const animeList = [];
    $('.post-show article, .animepost, .bsx, .bs').each((i, el) => {
        const link = $(el).find('a').attr('href');
        if (link && link.includes('/anime/')) {
            const animeId = extractId(link);
            const title = $(el).find('.tt, .title').text().trim() || 
                         $(el).find('a').attr('title') || 
                         "Unknown Title";
            
            const poster = extractPoster($(el));
            const type = $(el).find('.type').text().trim() || 'TV';
            const score = $(el).find('.score, .rating').text().trim() || '0.0';
            const genres = $(el).find('.genres').text().trim() || 'Unknown';
            
            animeList.push({
                title: title,
                poster: poster,
                type: type,
                score: parseFloat(score) || 0.0,
                genres: genres,
                animeId: animeId,
                href: `/samehadaku/anime/${animeId}`,
                samehadakuUrl: link.startsWith('http') ? link : `${BASE_URLS[0]}${link}`
            });
        }
    });
    
    // Cek apakah ada halaman berikutnya
    const hasNextPage = $('.next, .nav-next').length > 0 || 
                       $('.page-numbers').last().text().includes('Next');
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: { animeList },
        pagination: {
            currentPage: parseInt(page),
            hasNextPage: hasNextPage,
            nextPage: hasNextPage ? parseInt(page) + 1 : null,
            totalResults: animeList.length
        }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 5. LATEST EPISODES
app.get('/anime/samehadaku/latest', async (req, res) => {
    const { page = 1 } = req.query;
    const cacheKey = `latest_${page}`;
    const cached = getCached(cacheKey);
    
    if (cached) {
        return res.json(cached);
    }
    
    const $ = await fetchWithRetry(page > 1 ? `/page/${page}/` : '/');
    if (!$) {
        return res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { animeList: [] },
            pagination: { currentPage: parseInt(page), hasNextPage: false }
        });
    }
    
    const animeList = [];
    $('.post-show article, .animepost').each((i, el) => {
        const link = $(el).find('a').attr('href');
        if (link && !link.includes('/anime/') && link.includes('episode-')) {
            const episodeId = extractId(link);
            const animeMatch = link.match(/anime\/([^\/]+)/);
            const animeId = animeMatch ? animeMatch[1] : '';
            
            const title = $(el).find('.tt, .title').text().trim() || 
                         $(el).find('a').attr('title') || 
                         "Unknown Episode";
            
            const poster = extractPoster($(el));
            const released = $(el).find('.date, .time').text().trim() || 'Today';
            
            animeList.push({
                title: title,
                poster: poster,
                episodeId: episodeId,
                animeId: animeId,
                releasedOn: released,
                href: `/samehadaku/episode/${episodeId}`,
                samehadakuUrl: link.startsWith('http') ? link : `${BASE_URLS[0]}${link}`
            });
        }
    });
    
    const hasNextPage = $('.next, .nav-next').length > 0;
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: { animeList },
        pagination: {
            currentPage: parseInt(page),
            hasNextPage: hasNextPage,
            nextPage: hasNextPage ? parseInt(page) + 1 : null
        }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 6. ONGOING ANIME
app.get('/anime/samehadaku/ongoing', async (req, res) => {
    const { page = 1 } = req.query;
    const cacheKey = `ongoing_${page}`;
    
    const $ = await fetchWithRetry(`/daftar-anime-2/page/${page}/?status=Currently+Airing`);
    if (!$) {
        return res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { animeList: [] },
            pagination: { currentPage: parseInt(page), hasNextPage: false }
        });
    }
    
    const animeList = [];
    $('.animepost, .bsx, .bs').each((i, el) => {
        const link = $(el).find('a').attr('href');
        if (link && link.includes('/anime/')) {
            const animeId = extractId(link);
            const title = $(el).find('.tt, .title').text().trim();
            const poster = extractPoster($(el));
            const type = $(el).find('.type').text().trim() || 'TV';
            const score = $(el).find('.score').text().trim() || '0.0';
            const genres = $(el).find('.genres').text().trim() || 'Unknown';
            
            animeList.push({
                title: title,
                poster: poster,
                type: type,
                score: parseFloat(score) || 0.0,
                genres: genres,
                status: "Ongoing",
                animeId: animeId,
                href: `/samehadaku/anime/${animeId}`,
                samehadakuUrl: link.startsWith('http') ? link : `${BASE_URLS[0]}${link}`
            });
        }
    });
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: { animeList },
        pagination: {
            currentPage: parseInt(page),
            hasNextPage: animeList.length > 0
        }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 7. POPULAR ANIME
app.get('/anime/samehadaku/popular', async (req, res) => {
    const cacheKey = 'popular';
    const cached = getCached(cacheKey);
    
    if (cached) {
        return res.json(cached);
    }
    
    const $ = await fetchWithRetry('/');
    if (!$) {
        return res.json({
            status: "success",
            creator: "Sanka Vollerei",
            message: "",
            data: { animeList: [] }
        });
    }
    
    const animeList = [];
    $('.popular-posts li, .serieslist li').each((i, el) => {
        const link = $(el).find('a').attr('href');
        if (link && link.includes('/anime/')) {
            const animeId = extractId(link);
            const title = $(el).find('.tt, .title').text().trim();
            const poster = extractPoster($(el));
            const rank = i + 1;
            
            animeList.push({
                rank: rank,
                title: title,
                poster: poster,
                animeId: animeId,
                href: `/samehadaku/anime/${animeId}`,
                samehadakuUrl: link.startsWith('http') ? link : `${BASE_URLS[0]}${link}`
            });
        }
    });
    
    const response = {
        status: "success",
        creator: "Sanka Vollerei",
        message: "",
        data: { animeList: animeList.slice(0, 10) }
    };
    
    setCached(cacheKey, response);
    res.json(response);
});

// 8. SERVER PROXY (untuk streaming video)
app.get('/anime/samehadaku/server/:serverId', async (req, res) => {
    const { serverId } = req.params;
    
    // Ini adalah endpoint placeholder untuk server streaming
    // Di implementasi nyata, ini akan mengarahkan ke URL streaming
    
    res.json({
        status: "success",
        creator: "Sanka Vollerei",
        message: "Server streaming",
        data: {
            serverId: serverId,
            streamingUrl: `https://example.com/stream/${serverId}`,
            message: "Gunakan URL streaming dari endpoint episode"
        }
    });
});

// Error handling middleware
app.use((err, req, res, next) => {
    console.error('API Error:', err);
    res.status(500).json({
        status: "error",
        creator: "Sanka Vollerei",
        message: "Terjadi kesalahan internal server",
        error: process.env.NODE_ENV === 'development' ? err.message : undefined
    });
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({
        status: "error",
        creator: "Sanka Vollerei",
        message: "Endpoint tidak ditemukan"
    });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`🚀 Samehadaku Proxy API running on port ${PORT}`);
    console.log(`🌐 Base URLs: ${BASE_URLS.join(', ')}`);
    console.log(`📡 Endpoints:`);
    console.log(`   GET /anime/samehadaku/schedule`);
    console.log(`   GET /anime/samehadaku/anime/:id`);
    console.log(`   GET /anime/samehadaku/episode/:id`);
    console.log(`   GET /anime/samehadaku/search?q=query`);
});

module.exports = app;
