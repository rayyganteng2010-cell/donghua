const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

/**
 * GET / - Scrape homepage for latest donghua
 * Query params: page (optional)
 */
router.get('/', async (req, res) => {
  try {
    const page = req.query.page || 1;
    const url = page > 1 
      ? `https://donghuafilm.com/page/${page}/` 
      : 'https://donghuafilm.com/';
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const $ = cheerio.load(response.data);
    const donghuaList = [];
    
    // Scrape each anime item
    $('article').each((index, element) => {
      const $el = $(element);
      
      // Extract thumbnail
      const thumbnail = $el.find('img').attr('src') || $el.find('img').attr('data-src');
      
      // Extract title and link
      const title = $el.find('h2 a').text().trim();
      const animeUrl = $el.find('h2 a').attr('href');
      
      // Extract episode info
      const episodeText = $el.find('.episode').text() || $el.find('.epx').text() || '';
      const episodeMatch = episodeText.match(/\d+/);
      const episodeCount = episodeMatch ? parseInt(episodeMatch[0]) : null;
      
      // Extract genres
      const genres = [];
      $el.find('.genres a').each((i, genreEl) => {
        genres.push($(genreEl).text().trim());
      });
      
      // Extract rating if available
      const rating = $el.find('.score').text().trim();
      
      if (title && animeUrl) {
        donghuaList.push({
          id: animeUrl.split('/').filter(Boolean).pop() || `donghua-${index}`,
          title,
          url: animeUrl,
          thumbnail,
          episodeCount,
          episodeText,
          genres,
          rating: rating || null,
          index
        });
      }
    });
    
    // Check for pagination
    const pagination = [];
    $('.pagination a').each((i, el) => {
      const pageUrl = $(el).attr('href');
      const pageText = $(el).text().trim();
      if (pageUrl && pageText) {
        pagination.push({
          text: pageText,
          url: pageUrl,
          page: pageUrl.match(/page\/(\d+)/)?.[1] || null
        });
      }
    });
    
    res.json({
      success: true,
      url,
      total: donghuaList.length,
      donghua: donghuaList,
      pagination,
      currentPage: parseInt(page)
    });
    
  } catch (error) {
    console.error('Error scraping homepage:', error.message);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Failed to scrape homepage'
    });
  }
});

module.exports = router;
