/**
 * CORRECTED Node.js Bridge Server for REAL Shopify MCP Integration
 * 
 * CORRECCIÓN CRÍTICA: Declarar y configurar 'app' ANTES de definir las rutas
 * 
 * Este servidor proporciona una interfaz HTTP real entre Python y Shopify Admin GraphQL API,
 * usando nuestra implementación custom del cliente MCP.
 * 
 * Características:
 * - Integración REAL con Shopify Admin GraphQL API
 * - Rate limiting y security headers
 * - Logging estructurado
 * - Health checks comprehensivos
 * - Error handling robusto
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import winston from 'winston';
import Joi from 'joi';
import { config } from 'dotenv';
config();

// ✅ CORRECCIÓN CRÍTICA: Importar nuestro cliente real en lugar de @shopify/dev-mcp
import { RealShopifyMCPClient } from './shopify-mcp-client.js';

// ============================================================================
// 1. CONFIGURACIÓN DE LOGGING
// ============================================================================

const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.errors({ stack: true }),
        winston.format.json()
    ),
    defaultMeta: { service: 'mcp-bridge' },
    transports: [
        new winston.transports.File({ filename: 'logs/error.log', level: 'error' }),
        new winston.transports.File({ filename: 'logs/combined.log' }),
        new winston.transports.Console({
            format: winston.format.combine(
                winston.format.colorize(),
                winston.format.simple()
            )
        })
    ]
});

// ============================================================================
// 2. ESTADO DEL SERVIDOR Y MÉTRICAS
// ============================================================================

const serverState = {
    startTime: Date.now(),
    requestCount: 0,
    errorCount: 0,
    shopifyConnectionStatus: 'unknown',
    lastHealthCheck: null,
    lastShopifyTest: null
};

// ============================================================================
// 3. SHOPIFY MCP WRAPPER
// ============================================================================

/**
 * ✅ CORRECCIÓN: Wrapper para RealShopifyMCPClient en lugar de @shopify/dev-mcp
 * Encapsula la lógica de interacción con Shopify Admin GraphQL API
 */
class ShopifyMCPWrapper {
    constructor() {
        this.initialized = false;
        this.shopifyClient = null;
        this.initializationPromise = null;
    }
    
    async initialize() {
        if (this.initializationPromise) {
            return this.initializationPromise;
        }
        
        this.initializationPromise = this._doInitialize();
        return this.initializationPromise;
    }
    
    async _doInitialize() {
        try {
            logger.info('🏪 Initializing Real Shopify MCP client...');
            
            // ✅ USAR NUESTRO CLIENTE REAL
            this.shopifyClient = new RealShopifyMCPClient({
                shopDomain: process.env.SHOPIFY_SHOP_URL,
                accessToken: process.env.SHOPIFY_ACCESS_TOKEN,
                apiVersion: process.env.SHOPIFY_API_VERSION || '2024-07'
            });
            
            // Test the connection with real Shopify
            const initResult = await this.shopifyClient.initialize();
            
            if (initResult.success) {
                this.initialized = true;
                serverState.shopifyConnectionStatus = 'connected';
                serverState.lastShopifyTest = Date.now();
                
                logger.info('✅ Real Shopify MCP client initialized successfully', {
                    shopName: initResult.shopInfo.name,
                    currency: initResult.shopInfo.currencyCode
                });
                
                return true;
            } else {
                throw new Error('Shopify initialization failed');
            }
            
        } catch (error) {
            logger.error('❌ Real Shopify MCP initialization failed:', error);
            serverState.shopifyConnectionStatus = 'failed';
            this.initialized = false;
            throw error;
        }
    }
    
    async extractIntent(query, marketContext = {}, conversationHistory = []) {
        await this.ensureInitialized();
        
        try {
            logger.debug('🧠 Extracting intent via Real Shopify MCP', { 
                query: query.substring(0, 100),
                marketId: marketContext.market_id 
            });
            
            // ✅ USAR MÉTODO REAL DEL CLIENTE
            const result = await this.shopifyClient.extractIntent(
                query, 
                marketContext, 
                conversationHistory
            );
            
            logger.debug('✅ Intent extraction completed', { 
                type: result.intent?.type,
                confidence: result.intent?.confidence 
            });
            
            return result;
            
        } catch (error) {
            logger.error('❌ Intent extraction failed:', error);
            throw error;
        }
    }
    
    async getMarketConfiguration(marketId) {
        await this.ensureInitialized();
        
        try {
            logger.debug('🌍 Fetching market configuration', { marketId });
            
            // ✅ USAR MÉTODO REAL DEL CLIENTE
            const result = await this.shopifyClient.getMarketConfiguration(marketId);
            
            logger.debug('✅ Market configuration retrieved', { 
                marketId,
                currency: result.market_config?.currency 
            });
            
            return result;
            
        } catch (error) {
            logger.error('❌ Market configuration fetch failed:', error);
            throw error;
        }
    }
    
    async checkInventoryAvailability(marketId, productIds) {
        await this.ensureInitialized();
        
        try {
            logger.debug('📦 Checking inventory availability', { 
                marketId, 
                productCount: productIds.length 
            });
            
            // ✅ USAR MÉTODO REAL DEL CLIENTE  
            const result = await this.shopifyClient.checkInventoryAvailability(marketId, productIds);
            
            logger.debug('✅ Inventory check completed', { 
                marketId,
                totalProducts: Object.keys(result.availability || {}).length
            });
            
            return result;
            
        } catch (error) {
            logger.error('❌ Inventory check failed:', error);
            throw error;
        }
    }
    
    async ensureInitialized() {
        if (!this.initialized) {
            await this.initialize();
        }
    }
    
    getConnectionStatus() {
        return {
            initialized: this.initialized,
            connection_status: serverState.shopifyConnectionStatus,
            last_test: serverState.lastShopifyTest,
            client_metrics: this.shopifyClient?.getConnectionStatus() || null
        };
    }
}

// ✅ INSTANCIA GLOBAL DEL CLIENTE REAL
const shopifyMCP = new ShopifyMCPWrapper();

// ============================================================================
// 4. CONFIGURACIÓN DE EXPRESS Y MIDDLEWARE
// ============================================================================

// ✅ CORRECCIÓN CRÍTICA: Declarar app ANTES de usarla en las rutas
const app = express();
const PORT = process.env.PORT || 3001;

// Middleware de seguridad
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            scriptSrc: ["'self'"],
            imgSrc: ["'self'", "data:", "https:"],
        },
    },
}));

app.use(cors({
    origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:8000'],
    credentials: true
}));

app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Rate limiting
const limiter = rateLimit({
    windowMs: 60 * 1000, // 1 minute
    max: 100, // 100 requests per minute
    message: {
        error: 'Too many requests',
        retryAfter: '60 seconds'
    },
    standardHeaders: true,
    legacyHeaders: false,
});

app.use(limiter);

// Request timing middleware
app.use((req, res, next) => {
    req.startTime = Date.now();
    next();
});

// Middleware de logging
app.use((req, res, next) => {
    const start = Date.now();
    
    res.on('finish', () => {
        const duration = Date.now() - start;
        logger.info('HTTP Request', {
            method: req.method,
            url: req.url,
            statusCode: res.statusCode,
            duration: `${duration}ms`,
            userAgent: req.get('User-Agent'),
            ip: req.ip
        });
    });
    
    next();
});

// Middleware para contar requests
app.use((req, res, next) => {
    serverState.requestCount++;
    next();
});

// ============================================================================
// 5. SCHEMAS DE VALIDACIÓN
// ============================================================================

const schemas = {
    extractIntent: Joi.object({
        query: Joi.string().required().min(1).max(1000),
        market_context: Joi.object({
            market_id: Joi.string().required(),
            currency: Joi.string().optional(),
            language: Joi.string().optional()
        }).optional(),
        conversation_history: Joi.array().items(Joi.object()).optional()
    }),
    
    getMarketConfig: Joi.object({
        market_id: Joi.string().required().pattern(/^[A-Z]{2,3}$/)
    }),
    
    checkInventory: Joi.object({
        market_id: Joi.string().required(),
        product_ids: Joi.array().items(Joi.string()).required().min(1).max(50)
    })
};

// Validador de requests
const validateRequest = (schema) => {
    return (req, res, next) => {
        const { error } = schema.validate(req.body);
        if (error) {
            logger.warn('Validation error', { 
                error: error.details[0].message,
                path: req.path 
            });
            return res.status(400).json({
                error: 'Validation failed',
                details: error.details[0].message
            });
        }
        next();
    };
};

// ============================================================================
// 6. RUTAS DE LA API (AHORA app YA ESTÁ DECLARADA)
// ============================================================================

/**
 * Health check endpoint
 */
app.get('/health', async (req, res) => {
    try {
        const healthStatus = {
            status: 'healthy',
            timestamp: new Date().toISOString(),
            uptime: Date.now() - serverState.startTime,
            version: process.env.npm_package_version || '2.0.0',
            environment: process.env.NODE_ENV || 'development',
            
            // ✅ SHOPIFY CONNECTION STATUS
            shopify_connection: serverState.shopifyConnectionStatus,
            
            metrics: {
                total_requests: serverState.requestCount,
                total_errors: serverState.errorCount,
                error_rate: serverState.requestCount > 0 ? 
                    (serverState.errorCount / serverState.requestCount) : 0
            },
            
            // Configuration check
            configuration: {
                shopify_configured: !!(process.env.SHOPIFY_SHOP_URL && process.env.SHOPIFY_ACCESS_TOKEN),
                shop_url: process.env.SHOPIFY_SHOP_URL ? 
                    process.env.SHOPIFY_SHOP_URL.replace(/\/.*/, '/***') : 'not_configured',
                api_version: process.env.SHOPIFY_API_VERSION || 'default'
            }
        };
        
        // Test Shopify connection if unknown
        if (serverState.shopifyConnectionStatus === 'unknown') {
            try {
                await shopifyMCP.ensureInitialized();
                healthStatus.shopify_connection = 'connected';
                healthStatus.shopify_details = shopifyMCP.getConnectionStatus();
            } catch (error) {
                healthStatus.shopify_connection = 'failed';
                healthStatus.shopify_error = error.message;
            }
        }
        
        serverState.lastHealthCheck = Date.now();
        
        // Determine overall status
        if (healthStatus.shopify_connection === 'failed') {
            healthStatus.status = 'degraded';
            res.status(503);
        }
        
        res.json(healthStatus);
        
    } catch (error) {
        serverState.errorCount++;
        logger.error('Health check failed:', error);
        res.status(500).json({
            status: 'unhealthy',
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * ✅ MCP Status endpoint (compatible con Python client)
 */
app.get('/api/mcp/status', async (req, res) => {
    try {
        const status = {
            mcp_status: 'operational',
            bridge_version: process.env.npm_package_version || '2.0.0',
            claude_model: process.env.CLAUDE_MODEL || 'claude-sonnet-4-20250514',
            conversation_cache_size: 0,
            active_sessions: 0,
            shopify_integration: {
                status: serverState.shopifyConnectionStatus,
                shop_domain: process.env.SHOPIFY_SHOP_URL,
                api_version: process.env.SHOPIFY_API_VERSION || '2024-07',
                last_test: serverState.lastShopifyTest
            },
            server_info: {
                uptime_seconds: Math.floor((Date.now() - serverState.startTime) / 1000),
                total_requests: serverState.requestCount,
                error_rate: serverState.requestCount > 0 ? 
                    (serverState.errorCount / serverState.requestCount) : 0
            },
            timestamp: new Date().toISOString()
        };
        
        res.json(status);
        
    } catch (error) {
        logger.error('MCP status endpoint failed:', error);
        res.status(500).json({
            mcp_status: 'error',
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * ✅ Intent analysis endpoint (compatible con Python client) 
 */
app.post('/api/mcp/analyze-intent', async (req, res) => {
    try {
        const { text, context = {} } = req.body;
        
        if (!text) {
            return res.status(400).json({ 
                error: 'Text is required for intent analysis',
                timestamp: new Date().toISOString()
            });
        }
        
        logger.info('Intent analysis request', { 
            textLength: text.length,
            marketId: context.market_id 
        });
        
        // Llamar al endpoint interno de extract-intent
        const result = await shopifyMCP.extractIntent(
            text, 
            context, 
            []
        );
        
        // Formatear respuesta compatible con Python client
        const response = {
            success: true,
            intent: result.intent?.type || 'general',
            confidence: result.intent?.confidence || 0.5,
            entities: result.intent?.attributes || [],
            reasoning: `Intent detected based on Shopify analysis`,
            timestamp: new Date().toISOString()
        };
        
        res.json(response);
        
    } catch (error) {
        logger.error('Intent analysis failed:', error);
        res.status(500).json({
            success: false,
            error: 'Error analyzing intent',
            details: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * ✅ Conversation endpoint (compatible con Python client)
 */
app.post('/api/mcp/conversation', async (req, res) => {
    try {
        const { query, sessionId, context = {} } = req.body;
        
        if (!query) {
            return res.status(400).json({ 
                error: 'Query is required',
                timestamp: new Date().toISOString()
            });
        }
        
        logger.info('Conversation request', { 
            queryLength: query.length,
            sessionId: sessionId,
            marketId: context.market_id 
        });
        
        // Generar session ID si no se proporciona
        const finalSessionId = sessionId || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        // Procesar usando extract-intent
        const intentResult = await shopifyMCP.extractIntent(
            query, 
            context, 
            []
        );
        
        // Generar respuesta conversacional simple
        const conversationalResponse = `Based on your query, I understand you're looking for ${intentResult.intent?.type || 'general assistance'}. Here's what I can help you with.`;
        
        const response = {
            success: true,
            response: conversationalResponse,
            sessionId: finalSessionId,
            metadata: {
                processing_time_ms: Date.now() - req.startTime,
                intent_detected: intentResult.intent?.type,
                confidence: intentResult.intent?.confidence,
                market_id: context.market_id,
                timestamp: new Date().toISOString()
            }
        };
        
        res.json(response);
        
    } catch (error) {
        logger.error('Conversation processing failed:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error processing conversation',
            details: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * Extract intent from user query
 */
app.post('/mcp/extract-intent', validateRequest(schemas.extractIntent), async (req, res) => {
    try {
        const { query, market_context, conversation_history } = req.body;
        
        logger.info('Intent extraction request', { 
            queryLength: query.length,
            marketId: market_context?.market_id 
        });
        
        // ✅ USAR CLIENTE SHOPIFY REAL
        const result = await shopifyMCP.extractIntent(
            query, 
            market_context || {}, 
            conversation_history || []
        );
        
        res.json({
            success: true,
            ...result,  // Include all fields from RealShopifyMCPClient
            processing_time_ms: Date.now() - req.startTime,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        serverState.errorCount++;
        logger.error('Intent extraction failed:', error);
        res.status(500).json({
            success: false,
            error: 'Intent extraction failed',
            message: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * Get market configuration
 */
app.post('/mcp/markets/get-config', validateRequest(schemas.getMarketConfig), async (req, res) => {
    try {
        const { market_id } = req.body;
        
        logger.info('Market config request', { marketId: market_id });
        
        // ✅ USAR CLIENTE SHOPIFY REAL
        const result = await shopifyMCP.getMarketConfiguration(market_id);
        
        res.json({
            success: true,
            ...result,  // Include all fields from RealShopifyMCPClient
            processing_time_ms: Date.now() - req.startTime,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        serverState.errorCount++;
        logger.error('Market config fetch failed:', error);
        res.status(500).json({
            success: false,
            error: 'Market configuration fetch failed',
            message: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * Check inventory availability
 */
app.post('/mcp/inventory/check-availability', validateRequest(schemas.checkInventory), async (req, res) => {
    try {
        const { market_id, product_ids } = req.body;
        
        logger.info('Inventory check request', { 
            marketId: market_id,
            productCount: product_ids.length 
        });
        
        // ✅ USAR CLIENTE SHOPIFY REAL
        const result = await shopifyMCP.checkInventoryAvailability(market_id, product_ids);
        
        res.json({
            success: true,
            ...result,  // Include all fields from RealShopifyMCPClient
            processing_time_ms: Date.now() - req.startTime,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        serverState.errorCount++;
        logger.error('Inventory check failed:', error);
        res.status(500).json({
            success: false,
            error: 'Inventory check failed',
            message: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * Get detailed server and Shopify metrics
 */
app.get('/metrics', async (req, res) => {
    try {
        const metrics = {
            server: {
                uptime_seconds: Math.floor((Date.now() - serverState.startTime) / 1000),
                total_requests: serverState.requestCount,
                total_errors: serverState.errorCount,
                error_rate: serverState.requestCount > 0 ? 
                    (serverState.errorCount / serverState.requestCount) : 0,
                memory_usage: process.memoryUsage(),
                environment: process.env.NODE_ENV || 'development'
            },
            
            shopify: {
                connection_status: serverState.shopifyConnectionStatus,
                last_health_check: serverState.lastHealthCheck,
                last_shopify_test: serverState.lastShopifyTest,
                client_details: shopifyMCP.getConnectionStatus()
            },
            
            timestamp: new Date().toISOString()
        };
        
        // Get detailed Shopify metrics if available
        if (shopifyMCP.initialized && shopifyMCP.shopifyClient) {
            try {
                const shopifyMetrics = await shopifyMCP.shopifyClient.getMetrics();
                metrics.shopify.detailed_metrics = shopifyMetrics;
            } catch (error) {
                logger.warn('Could not fetch detailed Shopify metrics:', error.message);
            }
        }
        
        res.json(metrics);
        
    } catch (error) {
        logger.error('Metrics fetch failed:', error);
        res.status(500).json({
            error: 'Failed to fetch metrics',
            timestamp: new Date().toISOString()
        });
    }
});

// ============================================================================
// 7. ERROR HANDLERS
// ============================================================================

// 404 handler
app.use('*', (req, res) => {
    res.status(404).json({
        error: 'Endpoint not found',
        path: req.originalUrl,
        method: req.method,
        timestamp: new Date().toISOString()
    });
});

// Global error handler
app.use((err, req, res, next) => {
    serverState.errorCount++;
    logger.error('Unhandled error:', err);
    
    res.status(500).json({
        error: 'Internal server error',
        message: err.message,
        timestamp: new Date().toISOString()
    });
});

// ============================================================================
// 8. GRACEFUL SHUTDOWN
// ============================================================================

const shutdown = async (signal) => {
    logger.info(`${signal} received, shutting down gracefully`);
    
    if (shopifyMCP.shopifyClient) {
        try {
            await shopifyMCP.shopifyClient.disconnect();
            logger.info('Shopify client disconnected');
        } catch (error) {
            logger.error('Error disconnecting Shopify client:', error);
        }
    }
    
    process.exit(0);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// ============================================================================
// 9. START SERVER
// ============================================================================

app.listen(PORT, () => {
    logger.info(`🚀 Real Shopify MCP Bridge server running on port ${PORT}`, {
        environment: process.env.NODE_ENV || 'development',
        version: process.env.npm_package_version || '2.0.0',
        shopify_configured: !!(process.env.SHOPIFY_SHOP_URL && process.env.SHOPIFY_ACCESS_TOKEN)
    });
    
    // Initialize Shopify client on startup
    shopifyMCP.initialize().catch(error => {
        logger.error('Failed to initialize Shopify client on startup:', error);
    });
});

export default app;
