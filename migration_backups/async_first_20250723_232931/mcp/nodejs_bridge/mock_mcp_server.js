// src/api/mcp/nodejs_bridge/mock_mcp_server.js
// Mock del servidor MCP para desarrollo

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.MOCK_MCP_PORT || 3002;

// Middleware
app.use(cors());
app.use(express.json());

// MCP Mock routes
app.post('/api/query', (req, res) => {
  const { query, context } = req.body;
  
  console.log(`Mock MCP received query: ${query}`);
  
  // Simular respuesta MCP
  res.json({
    success: true,
    result: {
      response: `This is a mock response for: ${query}`,
      sessionId: context?.sessionId || 'mock-session',
      metadata: {
        source: 'mock-mcp',
        timestamp: new Date().toISOString()
      }
    }
  });
});

app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'mock-mcp',
    timestamp: new Date().toISOString()
  });
});

// Start mock server
app.listen(PORT, () => {
  console.log(`🔸 Mock MCP Server running on port ${PORT}`);
});

// Keep process running
console.log('🔹 Mock MCP process ready to handle requests');
process.stdin.resume();

// Handle termination
process.on('SIGINT', () => {
  console.log('🛑 Shutting down Mock MCP...');
  process.exit(0);
});
