// src/api/mcp/nodejs_bridge/server.js
// Node.js Bridge para Shopify MCP Integration

const express = require('express');
const cors = require('cors');
const { spawn } = require('child_process');

const app = express();
const PORT = process.env.MCP_NODE_PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Health check
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy', 
        service: 'mcp-bridge',
        timestamp: new Date().toISOString()
    });
});

// MCP Bridge Class
class ShopifyMCPBridge {
    constructor() {
        this.mcpProcess = null;
        this.isConnected = false;
        this.conversationCache = new Map();
    }

    async initializeMCP() {
        try {
            console.log('🔄 Initializing Shopify MCP...');
            
            // Usar el modo mock si está configurado
            const useMockMCP = process.env.USE_MOCK_MCP === "true";
            
            if (useMockMCP) {
                console.log('💡 Usando Mock MCP para desarrollo...');
                this.mcpProcess = spawn('node', ['mock_mcp_server.js'], {
                    stdio: ['pipe', 'pipe', 'pipe']
                });
            } else {
                // Usar npm run para ejecutar el script del package.json
                console.log('🔌 Iniciando Shopify MCP real...');
                this.mcpProcess = spawn('npm', ['run', 'shopify-mcp'], {
                    stdio: ['pipe', 'pipe', 'pipe'],
                    shell: true  // Usar shell para mejor compatibilidad
                });
            }

            this.mcpProcess.stdout.on('data', (data) => {
                console.log(`MCP stdout: ${data}`);
            });

            this.mcpProcess.stderr.on('data', (data) => {
                console.error(`MCP stderr: ${data}`);
            });

            this.mcpProcess.on('close', (code) => {
                console.log(`MCP process exited with code ${code}`);
                this.isConnected = false;
            });

            // Wait for initialization
            await new Promise(resolve => setTimeout(resolve, 2000));
            this.isConnected = true;
            
            console.log('✅ Shopify MCP initialized successfully');
            return true;
        } catch (error) {
            console.error('❌ Failed to initialize MCP:', error);
            return false;
        }
    }

    async sendMCPQuery(query, context = {}) {
        if (!this.isConnected) {
            throw new Error('MCP not connected');
        }

        try {
            // Simulate MCP interaction - replace with actual MCP protocol
            const mcpRequest = {
                jsonrpc: '2.0',
                id: Date.now(),
                method: 'tools/call',
                params: {
                    name: 'search_docs',
                    arguments: {
                        query: query,
                        context: context
                    }
                }
            };

            // Send to MCP process
            this.mcpProcess.stdin.write(JSON.stringify(mcpRequest) + '\n');

            // For now, return simulated response
            return {
                success: true,
                result: {
                    query: query,
                    context: context,
                    response: `MCP response for: ${query}`,
                    metadata: {
                        source: 'shopify-dev-mcp',
                        timestamp: new Date().toISOString()
                    }
                }
            };
        } catch (error) {
            console.error('Error in MCP query:', error);
            throw error;
        }
    }

    cacheConversation(sessionId, conversation) {
        this.conversationCache.set(sessionId, {
            ...conversation,
            lastUpdated: Date.now()
        });

        // Cleanup old conversations (older than 1 hour)
        const oneHourAgo = Date.now() - 3600000;
        for (const [key, value] of this.conversationCache.entries()) {
            if (value.lastUpdated < oneHourAgo) {
                this.conversationCache.delete(key);
            }
        }
    }

    getConversation(sessionId) {
        return this.conversationCache.get(sessionId) || null;
    }
}

// Initialize MCP Bridge
const mcpBridge = new ShopifyMCPBridge();

// API Endpoints

// Process conversational query
app.post('/api/mcp/conversation', async (req, res) => {
    try {
        const { query, sessionId, context = {} } = req.body;
        
        if (!query) {
            return res.status(400).json({ error: 'Query is required' });
        }

        console.log(`🗣️ Processing conversation: "${query}" for session: ${sessionId}`);

        // Get conversation history
        const conversation = mcpBridge.getConversation(sessionId) || { history: [] };

        // Process with MCP
        const mcpResponse = await mcpBridge.sendMCPQuery(query, {
            ...context,
            history: conversation.history
        });

        // Update conversation
        conversation.history.push({
            user: query,
            assistant: mcpResponse.result.response,
            timestamp: new Date().toISOString()
        });

        // Cache updated conversation
        if (sessionId) {
            mcpBridge.cacheConversation(sessionId, conversation);
        }

        res.json({
            success: true,
            response: mcpResponse.result.response,
            sessionId: sessionId,
            metadata: mcpResponse.result.metadata
        });

    } catch (error) {
        console.error('Error processing conversation:', error);
        res.status(500).json({ 
            error: 'Failed to process conversation',
            details: error.message 
        });
    }
});

// Get conversation history
app.get('/api/mcp/conversation/:sessionId', (req, res) => {
    try {
        const { sessionId } = req.params;
        const conversation = mcpBridge.getConversation(sessionId);
        
        if (!conversation) {
            return res.status(404).json({ error: 'Conversation not found' });
        }

        res.json({
            success: true,
            conversation: conversation
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Search Shopify documentation
app.post('/api/mcp/search', async (req, res) => {
    try {
        const { query, filters = {} } = req.body;
        
        console.log(`🔍 Searching Shopify docs: "${query}"`);

        const searchResponse = await mcpBridge.sendMCPQuery(query, {
            type: 'documentation_search',
            filters: filters
        });

        res.json({
            success: true,
            results: searchResponse.result,
            query: query
        });

    } catch (error) {
        console.error('Error in documentation search:', error);
        res.status(500).json({ error: error.message });
    }
});

// Intent analysis for conversational AI
app.post('/api/mcp/analyze-intent', async (req, res) => {
    try {
        const { text, context = {} } = req.body;
        
        // Simple intent analysis - can be enhanced with AI
        const intentMapping = {
            'search': ['find', 'search', 'look for', 'show me'],
            'recommend': ['recommend', 'suggest', 'what should', 'help me choose'],
            'compare': ['compare', 'difference', 'better', 'versus', 'vs'],
            'cart': ['add to cart', 'buy', 'purchase', 'order'],
            'help': ['help', 'how to', 'explain', 'what is']
        };

        let detectedIntent = 'general';
        let confidence = 0.5;

        const textLower = text.toLowerCase();
        
        for (const [intent, keywords] of Object.entries(intentMapping)) {
            const matches = keywords.filter(keyword => textLower.includes(keyword));
            if (matches.length > 0) {
                detectedIntent = intent;
                confidence = Math.min(0.9, 0.6 + (matches.length * 0.1));
                break;
            }
        }

        res.json({
            success: true,
            intent: detectedIntent,
            confidence: confidence,
            text: text,
            extractedEntities: {
                // Could extract product names, categories, etc.
            }
        });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// MCP status
app.get('/api/mcp/status', (req, res) => {
    res.json({
        status: mcpBridge.isConnected ? 'connected' : 'disconnected',
        conversationsActive: mcpBridge.conversationCache.size,
        uptime: process.uptime(),
        memoryUsage: process.memoryUsage()
    });
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('🛑 Shutting down MCP Bridge...');
    if (mcpBridge.mcpProcess) {
        mcpBridge.mcpProcess.kill();
    }
    process.exit(0);
});

// Start server
app.listen(PORT, async () => {
    console.log(`🌉 MCP Bridge running on port ${PORT}`);
    
    // Initialize MCP connection
    const initialized = await mcpBridge.initializeMCP();
    if (initialized) {
        console.log('🎉 MCP Bridge ready to handle requests!');
    } else {
        console.log('⚠️ MCP Bridge started but MCP connection failed');
    }
});

module.exports = app;