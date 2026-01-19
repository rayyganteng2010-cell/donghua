const express = require('express');
const cors = require('cors');
const app = express();

// Middleware
app.use(cors());
app.use(express.json());

// Import routes
const homeRoutes = require('./home');
const searchRoutes = require('./search');
const animeRoutes = require('./anime');
const episodeRoutes = require('./episode');

// Routes
app.get('/', (req, res) => {
  // Direct handler untuk home
  homeRoutes(req, res);
});

app.get('/search', (req, res) => {
  searchRoutes(req, res);
});

app.get('/anime/:slug', (req, res) => {
  // Load anime routes dynamically
  animeRoutes(req, res);
});

app.get('/episode/:slug', (req, res) => {
  // Load episode routes dynamically
  episodeRoutes(req, res);
});

// Health check dengan info detail
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'DonghuaFilm Scraper API',
    version: '2.0',
    timestamp: new Date().toISOString(),
    endpoints: {
      home: 'GET /',
      search: 'GET /search?q={query}',
      anime: 'GET /anime/{slug}',
      episode: 'GET /episode/{slug}',
      health: 'GET /health'
    },
    stats: {
      memory: process.memoryUsage(),
      uptime: process.uptime()
    }
  });
});

// Welcome page
app.get('/info', (req, res) => {
  res.json({
    message: '🎬 DonghuaFilm Scraper API',
    description: 'Unofficial API for scraping DonghuaFilm.com',
    features: [
      'Scrape latest donghua',
      'Search donghua by title',
      'Get anime details and episodes',
      'Get episode video links'
    ],
    note: 'This API is for educational purposes only',
    github: 'https://github.com/yourusername/donghua-api'
  });
});

// Error handling
app.use((err, req, res, next) => {
  console.error('🚨 Server Error:', {
    error: err.message,
    stack: err.stack,
    url: req.url,
    method: req.method
  });
  
  res.status(500).json({
    error: 'Internal Server Error',
    message: process.env.NODE_ENV === 'development' ? err.message : 'Something went wrong',
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    requested: req.originalUrl,
    available_endpoints: [
      '/',
      '/search?q={query}',
      '/anime/{slug}',
      '/episode/{slug}',
      '/health',
      '/info'
    ],
    timestamp: new Date().toISOString()
  });
});

// Export untuk Vercel
module.exports = (req, res) => {
  console.log(`📥 Incoming: ${req.method} ${req.url}`);
  return app(req, res);
};
