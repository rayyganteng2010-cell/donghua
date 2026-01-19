const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

/**
 * GET /anime/:slug - Get anime details and episode list
 * Example: /anime/renegade-immortal
 */
router.get('/:slug', async (req, res) => {
  try {
    const slug = req.params.slug;
    const url = `https://donghuafilm.com/anime/${slug}/`;
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const $ = cheerio.load(response.data);
    
    // Extract anime details
    const title = $('h1.entry-title').text().trim();
    const thumbnail = $('.thumb img').attr('src') || 
                     $('.poster img').attr('src') ||
                     $('img[itemprop="image"]').attr('src');
    
    // Extract synopsis/description
    let description = '';
    $('.entry-content p').each((i, el) => {
      const text = $(el).text().trim();
      if (text && text.length > 50 && !description) {
        description = text;
      }
    });
    
    // Extract metadata
    const metadata = {};
    $('.info-content span').each((i, el) => {
      const text = $(el).text().trim();
      if (text.includes(':')) {
        const [key, ...valueParts] = text.split(':');
        if (key && valueParts.length > 0) {
          metadata[key.trim()] = valueParts.join(':').trim();
        }
      }
    });
    
    // Extract genres
    const genres = [];
    $('.genx a').each((i, el) => {
      genres.push($(el).text().trim());
    });
    
    // Extract episodes
    const episodes = [];
    $('.eplister ul li').each((index, element) => {
      const $el = $(element);
      
      const episodeUrl = $el.find('a').attr('href');
      const episodeTitle = $el.find('.epl-title').text().trim();
      const episodeNumber = $el.find('.epl-num').text().trim();
      const episodeDate = $el.find('.epl-date').text().trim();
      const episodeThumbnail = $el.find('img').attr('src') || 
                              $el.find('img').attr('data-src');
      
      if (episodeUrl) {
        episodes.push({
          id: episodeUrl.split('/').filter(Boolean).pop() || `ep-${index}`,
          url: episodeUrl,
          title: episodeTitle,
          number: episodeNumber,
          date: episodeDate,
          thumbnail: episodeThumbnail,
          episode: parseInt(episodeNumber.match(/\d+/)?.[0]) || index + 1
        });
      }
    });
    
    // If no episodes in .eplister, check for other structures
    if (episodes.length === 0) {
      $('.episode-list a, .episodes a').each((index, element) => {
        const $el = $(element);
        const episodeUrl = $el.attr('href');
        const episodeText = $el.text().trim();
        
        if (episodeUrl && episodeUrl.includes('episode')) {
          episodes.push({
            id: episodeUrl.split('/').filter(Boolean).pop(),
            url: episodeUrl,
            title: episodeText,
            number: episodeText.match(/\d+/)?.[0] || `${index + 1}`,
            episode: index + 1
          });
        }
      });
    }
    
    res.json({
      success: true,
      url,
      anime: {
        slug,
        title,
        thumbnail,
        description,
        metadata,
        genres,
        totalEpisodes: episodes.length
      },
      episodes: episodes.reverse(), // Latest episodes first
      totalEpisodes: episodes.length
    });
    
  } catch (error) {
    console.error('Error fetching anime details:', error.message);
    
    // Check if it's a 404 error
    if (error.response && error.response.status === 404) {
      return res.status(404).json({
        success: false,
        error: 'Anime not found',
        message: 'The requested anime does not exist'
      });
    }
    
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Failed to fetch anime details'
    });
  }
});

module.exports = router;
