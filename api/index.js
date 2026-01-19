const express = require('express');
const cors = require('cors');
const app = express();

// Middleware
app.use(cors());
app.use(express.json());

// Route handlers
const homeRoutes = require('./home');
const searchRoutes = require('./search');
const animeRoutes = require('./anime');
const episodeRoutes = require('./episode');

// Routes
app.get('/', homeRoutes);
app.get('/search', searchRoutes);
app.get('/anime/:slug', animeRoutes);
app.get('/episode/:slug', episodeRoutes);

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'DonghuaFilm Scraper API is running',
    timestamp: new Date().toISOString()
  });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(500).json({ 
    error: 'Internal Server Error',
    message: err.message,
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({ 
    error: 'Not Found',
    message: `Route ${req.originalUrl} not found`,
    timestamp: new Date().toISOString()
  });
});

// Export untuk Vercel
module.exports = (req, res) => {
  return app(req, res);
};
