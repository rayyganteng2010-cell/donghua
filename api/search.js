const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

router.get('/', async (req, res) => {
  try {
    const query = req.query.q;
    const page = req.query.page || 1;
    
    if (!query || query.trim().length < 2) {
      return res.status(400).json({
        success: false,
        error: 'Query parameter "q" is required (min 2 characters)',
        example: '/search?q=Renegade+Immortal'
      });
    }
    
    const encodedQuery = encodeURIComponent(query.trim());
    let url = `https://donghuafilm.com/?s=${encodedQuery}`;
    
    if (page > 1) {
      url += `&page=${page}`;
    }
    
    console.log(`🔍 Searching: "${query}" -> ${url}`);
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://donghuafilm.com/'
      },
      timeout: 15000
    });
    
    const $ = cheerio.load(response.data);
    const results = [];
    
    // **Cek jika ada pesan "tidak ditemukan"**
    const pageText = $('body').text().toLowerCase();
    const notFoundKeywords = [
      'tidak ditemukan',
      'no results found',
      'nothing found',
      'tidak ada hasil',
      'maaf, tidak ditemukan'
    ];
    
    const hasNoResults = notFoundKeywords.some(keyword => 
      pageText.includes(keyword)
    ) || $('.no-results, .not-found').length > 0;
    
    if (hasNoResults) {
      return res.json({
        success: true,
        query,
        page: parseInt(page),
        total: 0,
        results: [],
        message: `No results found for "${query}"`,
        suggestions: [
          'Try different keywords',
          'Check spelling',
          'Use English title'
        ]
      });
    }
    
    // **Parse search results dari berbagai kemungkinan selector**
    
    // Method 1: Artikel hasil pencarian
    $('article, .search-result, .result-item').each((index, element) => {
      const $el = $(element);
      
      let title = $el.find('h2 a, h3 a, .title a, .entry-title a').text().trim();
      let url = $el.find('h2 a, h3 a, .title a, .entry-title a').attr('href');
      let thumbnail = $el.find('img').attr('src') || 
                     $el.find('img').attr('data-src') ||
                     $el.find('.thumb img').attr('src');
      
      // Clean URL
      if (thumbnail && thumbnail.startsWith('//')) {
        thumbnail = 'https:' + thumbnail;
      }
      
      // Cari description
      let description = '';
      $el.find('.entry-content p, .description, .excerpt, .desc').each((i, p) => {
        const text = $(p).text().trim();
        if (text.length > 30 && !description) {
          description = text.substring(0, 200) + '...';
        }
      });
      
      // Cari episode info
      let episodeText = '';
      let episodeCount = null;
      
      $el.find('.episode, .epx, .eps, .ep').each((i, ep) => {
        const text = $(ep).text().trim();
        if (text && !episodeText) {
          episodeText = text;
          const match = text.match(/\d+/);
          if (match) episodeCount = parseInt(match[0]);
        }
      });
      
      // Cari tahun/type
      let year = null;
      let type = null;
      $el.find('.metadata, .info, .details span').each((i, meta) => {
        const text = $(meta).text().trim().toLowerCase();
        if (text.includes('202') || text.match(/\b(202[0-9]|201[0-9])\b/)) {
          const yearMatch = text.match(/(202[0-9]|201[0-9])/);
          if (yearMatch) year = yearMatch[0];
        }
        if (text.includes('donghua') || text.includes('anime') || text.includes('series')) {
          type = text.split('·')[0].trim();
        }
      });
      
      if (title && url) {
        const slug = url.split('/').filter(Boolean).pop();
        
        results.push({
          id: slug || `search-${index}-${Date.now()}`,
          title,
          url,
          slug,
          thumbnail: thumbnail || null,
          description: description || null,
          episodeCount,
          episodeText: episodeText || null,
          year,
          type,
          relevance: calculateRelevance(query, title), // Fungsi sederhana
          scrapedAt: new Date().toISOString()
        });
      }
    });
    
    // Method 2: Jika metode pertama tidak dapat hasil, cari semua link yang relevan
    if (results.length === 0) {
      $('a').each((index, element) => {
        const $el = $(element);
        const href = $el.attr('href');
        const text = $el.text().trim();
        
        // Filter hanya link anime yang mengandung kata kunci
        if (href && href.includes('/anime/') && text.length > 3) {
          const isRelevant = query.toLowerCase().split(' ').some(word =>
            text.toLowerCase().includes(word.toLowerCase()) ||
            href.toLowerCase().includes(word.toLowerCase())
          );
          
          if (isRelevant) {
            const slug = href.split('/').filter(Boolean).pop();
            results.push({
              id: slug || `link-${index}`,
              title: text,
              url: href,
              slug,
              scrapedAt: new Date().toISOString()
            });
          }
        }
      });
    }
    
    // **Hapus duplikat**
    const uniqueResults = [];
    const urlSet = new Set();
    
    results.forEach(item => {
      if (item.url && !urlSet.has(item.url)) {
        urlSet.add(item.url);
        uniqueResults.push(item);
      }
    });
    
    // **Sort by relevance**
    uniqueResults.sort((a, b) => {
      const aScore = calculateRelevance(query, a.title);
      const bScore = calculateRelevance(query, b.title);
      return bScore - aScore;
    });
    
    // **Cek pagination search**
    let totalPages = 1;
    const searchPagination = [];
    
    $('.pagination a, .page-numbers a').each((i, el) => {
      const pageUrl = $(el).attr('href');
      const pageText = $(el).text().trim();
      const pageNum = parseInt(pageText);
      
      if (pageUrl && pageNum && !isNaN(pageNum)) {
        searchPagination.push({
          page: pageNum,
          url: pageUrl,
          text: `Page ${pageNum}`
        });
        
        if (pageNum > totalPages) {
          totalPages = pageNum;
        }
      }
    });
    
    console.log(`✅ Search results for "${query}": ${uniqueResults.length} items`);
    
    res.json({
      success: true,
      query,
      metadata: {
        page: parseInt(page),
        totalResults: uniqueResults.length,
        totalPages: totalPages,
        hasMore: page < totalPages,
        scrapedFrom: url,
        scrapedAt: new Date().toISOString()
      },
      results: uniqueResults,
      pagination: searchPagination,
      suggestions: generateSuggestions(query, uniqueResults)
    });
    
  } catch (error) {
    console.error('❌ Search error:', error.message);
    
    // Fallback: Return some hardcoded results
    const fallbackResults = [
      {
        id: 'renegade-immortal',
        title: 'Renegade Immortal',
        url: 'https://donghuafilm.com/anime/renegade-immortal/',
        description: 'Seorang budak menjadi immortal melalui cultivation.',
        episodeCount: 124
      },
      {
        id: 'a-will-eternal',
        title: 'A Will Eternal',
        url: 'https://donghuafilm.com/anime/a-will-eternal/',
        description: 'Komedi cultivation tentang Bai Xiaochun.',
        episodeCount: 52
      }
    ].filter(item => 
      item.title.toLowerCase().includes((req.query.q || '').toLowerCase())
    );
    
    res.json({
      success: true,
      query: req.query.q,
      results: fallbackResults,
      total: fallbackResults.length,
      note: 'Using fallback data (search failed)',
      error: error.message
    });
  }
});

// **Helper Functions**

function calculateRelevance(query, title) {
  const queryWords = query.toLowerCase().split(' ');
  const titleLower = title.toLowerCase();
  let score = 0;
  
  // Exact match
  if (titleLower === query.toLowerCase()) score += 100;
  
  // Contains all words
  const containsAll = queryWords.every(word => titleLower.includes(word));
  if (containsAll) score += 50;
  
  // Contains some words
  queryWords.forEach(word => {
    if (titleLower.includes(word)) score += 10;
  });
  
  // Starts with query
  if (titleLower.startsWith(query.toLowerCase())) score += 30;
  
  return score;
}

function generateSuggestions(query, results) {
  const suggestions = [];
  const queryLower = query.toLowerCase();
  
  if (results.length === 0) {
    suggestions.push('Try searching in English');
    suggestions.push('Check your spelling');
    suggestions.push('Search by character name');
  }
  
  // Jika query pendek, sarankan pencarian yang lebih spesifik
  if (query.length < 4) {
    suggestions.push('Try longer search terms');
  }
  
  // Ambil genre dari results yang ada
  const commonTerms = ['immortal', 'cultivation', 'donghua', 'xianxia', 'wuxia'];
  commonTerms.forEach(term => {
    if (!queryLower.includes(term) && term.length > 3) {
      suggestions.push(`Try "${query} ${term}"`);
    }
  });
  
  return suggestions.slice(0, 3);
}

module.exports = router;
