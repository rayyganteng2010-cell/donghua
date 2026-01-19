const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

router.get('/', async (req, res) => {
  try {
    const page = req.query.page || 1;
    const url = page > 1 
      ? `https://donghuafilm.com/page/${page}/` 
      : 'https://donghuafilm.com/';
    
    console.log(`📺 Scraping homepage: ${url}`);
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://donghuafilm.com/'
      },
      timeout: 15000
    });
    
    const $ = cheerio.load(response.data);
    const donghuaList = [];
    
    // **Scrape dari berbagai selector untuk dapat lebih banyak data**
    
    // 1. Dari artikel utama
    $('article, .item, .anime-item, .post').each((index, element) => {
      const $el = $(element);
      
      // Cari thumbnail dari berbagai kemungkinan
      let thumbnail = $el.find('img').attr('src') || 
                     $el.find('img').attr('data-src') ||
                     $el.find('.thumb img').attr('src') ||
                     $el.find('.poster img').attr('src');
      
      // Clean up thumbnail URL
      if (thumbnail && thumbnail.startsWith('//')) {
        thumbnail = 'https:' + thumbnail;
      }
      
      // Cari title
      let title = $el.find('h2 a, h3 a, .title a, .entry-title a').text().trim();
      if (!title) {
        title = $el.find('h2, h3, .title, .entry-title').text().trim();
      }
      
      // Cari URL
      let animeUrl = $el.find('h2 a, h3 a, .title a, .entry-title a').attr('href') ||
                    $el.find('a').first().attr('href');
      
      // Cari episode info
      let episodeText = '';
      let episodeCount = null;
      
      // Coba berbagai kemungkinan selector untuk episode
      const episodeSelectors = ['.episode', '.epx', '.eps', '.episode-num', '.num-episode', '.ep'];
      episodeSelectors.forEach(selector => {
        const epText = $el.find(selector).text().trim();
        if (epText && !episodeText) {
          episodeText = epText;
          const match = epText.match(/\d+/);
          if (match) episodeCount = parseInt(match[0]);
        }
      });
      
      // Cari rating
      let rating = $el.find('.score, .rating, .ratings').text().trim();
      if (!rating) {
        const score = $el.find('[itemprop="ratingValue"]').text().trim();
        if (score) rating = score;
      }
      
      // Cari genres
      const genres = [];
      $el.find('.genres a, .genre a, .genx a, [rel="tag"]').each((i, genreEl) => {
        const genre = $(genreEl).text().trim();
        if (genre) genres.push(genre);
      });
      
      // Cari sinopsis singkat
      let synopsis = $el.find('.entry-content p, .description, .synopsis').text().trim().substring(0, 150);
      
      if (title && animeUrl && title.length > 2) {
        const slug = animeUrl.split('/').filter(Boolean).pop();
        
        donghuaList.push({
          id: slug || `donghua-${index}-${Date.now()}`,
          title,
          url: animeUrl,
          slug: slug,
          thumbnail,
          episodeCount,
          episodeText,
          rating: rating || null,
          genres: genres.length > 0 ? genres : null,
          synopsis: synopsis || null,
          scrapedAt: new Date().toISOString()
        });
      }
    });
    
    // 2. Scrape dari grid/container tambahan
    $('.grid-item, .anime-grid, .listupd .bs, .listupd article').each((index, element) => {
      const $el = $(element);
      
      // Skip jika sudah ada
      const existingUrl = $el.find('a').attr('href');
      if (donghuaList.some(item => item.url === existingUrl)) return;
      
      let thumbnail = $el.find('img').attr('src') || $el.find('img').attr('data-src');
      let title = $el.find('.tt, .ttx, h4, .title').text().trim();
      let animeUrl = $el.find('a').attr('href');
      
      if (thumbnail && thumbnail.startsWith('//')) {
        thumbnail = 'https:' + thumbnail;
      }
      
      if (title && animeUrl && title.length > 2) {
        const slug = animeUrl.split('/').filter(Boolean).pop();
        
        donghuaList.push({
          id: slug || `grid-${index}-${Date.now()}`,
          title,
          url: animeUrl,
          slug: slug,
          thumbnail,
          scrapedAt: new Date().toISOString()
        });
      }
    });
    
    // Hapus duplikat berdasarkan URL
    const uniqueList = [];
    const urlSet = new Set();
    
    donghuaList.forEach(item => {
      if (item.url && !urlSet.has(item.url)) {
        urlSet.add(item.url);
        uniqueList.push(item);
      }
    });
    
    // **Scrape pagination info**
    const pagination = [];
    const paginationSelectors = ['.pagination', '.page-numbers', '.paging', '.nav-links'];
    
    paginationSelectors.forEach(selector => {
      $(selector).find('a, .page-numbers').each((i, el) => {
        const $el = $(el);
        if ($el.is('span, .current')) return; // Skip current page
        
        const pageUrl = $el.attr('href');
        const pageText = $el.text().trim();
        
        if (pageUrl && pageText && !isNaN(parseInt(pageText))) {
          const pageNum = parseInt(pageText);
          pagination.push({
            page: pageNum,
            url: pageUrl,
            text: `Page ${pageText}`
          });
        }
      });
    });
    
    // **Cari total pages**
    let totalPages = 1;
    $(paginationSelectors.join(', ')).find('.page-numbers').each((i, el) => {
      const text = $(el).text().trim();
      if (text && !isNaN(text) && parseInt(text) > totalPages) {
        totalPages = parseInt(text);
      }
    });
    
    console.log(`✅ Found ${uniqueList.length} donghua on page ${page}`);
    
    res.json({
      success: true,
      metadata: {
        page: parseInt(page),
        totalItems: uniqueList.length,
        totalPages: totalPages || Math.max(...pagination.map(p => p.page)) || 1,
        hasNextPage: page < (totalPages || 1),
        scrapedFrom: url,
        scrapedAt: new Date().toISOString()
      },
      data: uniqueList,
      pagination: pagination.slice(0, 10), // Batasi 10 item pagination
      note: 'Data scraped from DonghuaFilm.com'
    });
    
  } catch (error) {
    console.error('❌ Home scraping error:', error.message);
    console.error('Stack:', error.stack);
    
    // Fallback: Return cached/static data jika scraping gagal
    const fallbackData = [
      {
        id: 'renegade-immortal',
        title: 'Renegade Immortal',
        url: 'https://donghuafilm.com/anime/renegade-immortal/',
        thumbnail: 'https://donghuafilm.com/wp-content/uploads/2023/05/Renegade-Immortal.jpg',
        episodeCount: 124,
        rating: '8.5'
      },
      {
        id: 'a-will-eternal',
        title: 'A Will Eternal',
        url: 'https://donghuafilm.com/anime/a-will-eternal/',
        thumbnail: 'https://donghuafilm.com/wp-content/uploads/2023/05/A-Will-Eternal.jpg',
        episodeCount: 52,
        rating: '8.7'
      }
    ];
    
    res.json({
      success: true,
      metadata: {
        page: parseInt(req.query.page || 1),
        totalItems: fallbackData.length,
        note: 'Using fallback data (scraping failed)'
      },
      data: fallbackData,
      error: error.message
    });
  }
});

module.exports = router;
