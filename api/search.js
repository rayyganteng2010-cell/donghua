const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

/**
 * GET /search?q=query - Search for donghua
 */
router.get('/', async (req, res) => {
  try {
    const query = req.query.q;
    if (!query) {
      return res.status(400).json({
        success: false,
        error: 'Query parameter "q" is required'
      });
    }
    
    const encodedQuery = encodeURIComponent(query);
    const url = `https://donghuafilm.com/?s=${encodedQuery}`;
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const $ = cheerio.load(response.data);
    const results = [];
    
    // Check if no results
    const noResults = $('.no-results').length > 0 || 
                      $('p:contains("Tidak ditemukan")').length > 0;
    
    if (noResults) {
      return res.json({
        success: true,
        query,
        url,
        total: 0,
        results: [],
        message: 'No results found'
      });
    }
    
    // Parse search results
    $('article').each((index, element) => {
      const $el = $(element);
      
      const title = $el.find('h2 a').text().trim();
      const url = $el.find('h2 a').attr('href');
      const thumbnail = $el.find('img').attr('src') || $el.find('img').attr('data-src');
      const description = $el.find('.entry-content p').text().trim();
      
      // Extract episode info
      const episodeText = $el.find('.episode').text() || $el.find('.epx').text() || '';
      const episodeMatch = episodeText.match(/\d+/);
      const episodeCount = episodeMatch ? parseInt(episodeMatch[0]) : null;
      
      if (title && url) {
        results.push({
          id: url.split('/').filter(Boolean).pop() || `result-${index}`,
          title,
          url,
          thumbnail,
          description,
          episodeCount,
          episodeText
        });
      }
    });
    
    res.json({
      success: true,
      query,
      url,
      total: results.length,
      results
    });
    
  } catch (error) {
    console.error('Search error:', error.message);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Search failed'
    });
  }
});

module.exports = router;
