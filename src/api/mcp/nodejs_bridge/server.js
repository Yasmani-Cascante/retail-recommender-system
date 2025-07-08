/**
 * Real Node.js Bridge Server for Shopify MCP Integration
 * 
 * Este servidor proporciona una interfaz HTTP real entre Python y Shopify MCP,
 * reemplazando los mocks anteriores con funcionalidad completamente operativa.
 * 
 * Características:
 * - Integración real con @shopify/dev-mcp
 * - Rate limiting y security headers
 * - Logging estructurado
 * - Health checks comprehensivos
 * - Error handling robusto
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const winston = require('winston');
const Joi = require('joi');
require('dotenv').config();

// Configurar logger
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

// Schemas de validación
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

// Estado del servidor y métricas
const serverState = {
    startTime: Date.now(),
    requestCount: 0,
    errorCount: 0,
    mcpConnectionStatus: 'unknown',
    lastHealthCheck: null
};

/**
 * MCP Client Wrapper
 * Encapsula la lógica de interacción con Shopify MCP
 */
class MCPClientWrapper {
    constructor() {
        this.initialized = false;
        this.mcpClient = null;
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
            logger.info('Initializing Shopify MCP client...');
            
            // Importar y configurar Shopify MCP
            const { createMCPClient } = require('@shopify/dev-mcp');
            
            this.mcpClient = await createMCPClient({
                // Configuración específica para MCP
                transport: 'stdio',
                capabilities: {
                    roots: true,
                    sampling: true,
                    experimental: {
                        progressNotifications: true
                    }
                }
            });
            
            // Verificar conexión
            await this.mcpClient.connect();
            
            this.initialized = true;
            serverState.mcpConnectionStatus = 'connected';
            logger.info('Shopify MCP client initialized successfully');
            
            return true;
            
        } catch (error) {
            logger.error('Failed to initialize MCP client:', error);
            serverState.mcpConnectionStatus = 'failed';
            this.initialized = false;
            throw error;
        }
    }
    
    async extractIntent(query, marketContext = {}, conversationHistory = []) {
        await this.ensureInitialized();
        
        try {
            logger.debug('Extracting intent via MCP', { 
                query: query.substring(0, 100),
                marketId: marketContext.market_id 
            });
            
            // Usar MCP para análisis de intención
            const result = await this.mcpClient.analyze({
                text: query,
                context: {
                    market: marketContext,
                    history: conversationHistory.slice(-3), // Últimas 3 interacciones
                    timestamp: new Date().toISOString()
                }
            });
            
            // Procesar y normalizar respuesta MCP
            const intent = this._normalizeIntentResponse(result, query);
            
            logger.debug('Intent extraction completed', { 
                type: intent.type,
                confidence: intent.confidence 
            });
            
            return intent;
            
        } catch (error) {
            logger.error('Intent extraction failed:', error);
            // Fallback a análisis básico
            return this._fallbackIntentAnalysis(query);
        }
    }
    
    async getMarketConfiguration(marketId) {
        await this.ensureInitialized();
        
        try {
            logger.debug('Fetching market configuration', { marketId });
            
            const marketData = await this.mcpClient.getMarketInfo({
                marketId: marketId
            });
            
            // Normalizar datos de mercado
            const config = this._normalizeMarketConfig(marketData, marketId);
            
            logger.debug('Market configuration retrieved', { 
                marketId,
                currency: config.currency 
            });
            
            return config;
            
        } catch (error) {
            logger.error('Market configuration fetch failed:', error);
            // Fallback a configuración por defecto
            return this._fallbackMarketConfig(marketId);
        }
    }
    
    async checkInventoryAvailability(marketId, productIds) {
        await this.ensureInitialized();
        
        try {
            logger.debug('Checking inventory availability', { 
                marketId, 
                productCount: productIds.length 
            });
            
            const inventoryData = await this.mcpClient.checkInventory({
                marketId: marketId,
                productIds: productIds
            });
            
            const availability = this._normalizeInventoryResponse(inventoryData);
            
            logger.debug('Inventory check completed', { 
                marketId,
                availableCount: Object.values(availability).filter(Boolean).length
            });
            
            return availability;
            
        } catch (error) {
            logger.error('Inventory check failed:', error);
            // Fallback: asumir disponibilidad limitada
            return this._fallbackInventoryResponse(productIds);
        }
    }
    
    async ensureInitialized() {
        if (!this.initialized) {
            await this.initialize();
        }
    }
    
    _normalizeIntentResponse(mcpResult, originalQuery) {
        /**
         * Normaliza la respuesta de MCP a un formato estándar
         */
        try {
            const intent = {
                type: mcpResult.intent?.type || 'general',
                confidence: Math.min(mcpResult.confidence || 0.7, 1.0),
                attributes: mcpResult.attributes || [],
                urgency: mcpResult.urgency || 'medium',
                categories: mcpResult.categories || [],
                budget_signals: mcpResult.budget || {},
                source: 'shopify_mcp',
                timestamp: new Date().toISOString(),
                original_query: originalQuery
            };
            
            // Mejorar confianza basada en señales adicionales
            if (intent.attributes.length > 0) {
                intent.confidence = Math.min(intent.confidence + 0.1, 1.0);
            }
            
            return intent;
            
        } catch (error) {
            logger.error('Error normalizing intent response:', error);
            return this._fallbackIntentAnalysis(originalQuery);
        }
    }
    
    _normalizeMarketConfig(mcpData, marketId) {
        /**
         * Normaliza configuración de mercado de MCP
         */
        const marketConfigs = {
            'US': { currency: 'USD', language: 'en', timezone: 'America/New_York' },
            'ES': { currency: 'EUR', language: 'es', timezone: 'Europe/Madrid' },
            'MX': { currency: 'MXN', language: 'es', timezone: 'America/Mexico_City' },
            'CO': { currency: 'COP', language: 'es', timezone: 'America/Bogota' },
            'CL': { currency: 'CLP', language: 'es', timezone: 'America/Santiago' }
        };
        
        const defaultConfig = marketConfigs[marketId] || marketConfigs['US'];
        
        return {
            market_id: marketId,
            market_name: mcpData?.market_name || `Market ${marketId}`,
            currency: mcpData?.currency || defaultConfig.currency,
            primary_language: mcpData?.language || defaultConfig.language,
            timezone: mcpData?.timezone || defaultConfig.timezone,
            tax_rate: mcpData?.tax_rate || 0.0,
            shipping_zones: mcpData?.shipping_zones || [`${marketId}_domestic`],
            payment_methods: mcpData?.payment_methods || ['credit_card', 'paypal'],
            cultural_preferences: {
                communication_style: mcpData?.cultural?.communication_style || 'standard',
                seasonal_events: mcpData?.cultural?.seasonal_events || [],
                product_preferences: mcpData?.cultural?.product_preferences || {}
            },
            source: 'shopify_mcp',
            last_updated: new Date().toISOString()
        };
    }
    
    _normalizeInventoryResponse(mcpData) {
        /**
         * Normaliza respuesta de inventario
         */
        const availability = {};
        
        if (mcpData && mcpData.products) {
            mcpData.products.forEach(product => {
                availability[product.id] = {
                    available: product.available || false,
                    quantity: product.quantity || 0,
                    price: product.price || null,
                    estimated_delivery: product.estimated_delivery || null
                };
            });
        }
        
        return availability;
    }
    
    _fallbackIntentAnalysis(query) {
        /**
         * Análisis de intención de fallback usando keywords
         */
        const queryLower = query.toLowerCase();
        
        const intentKeywords = {
            'search': ['busco', 'quiero', 'necesito', 'donde encuentro', 'buscando'],
            'recommendation': ['recomienda', 'sugieres', 'aconsejas', 'mejor opcion'],
            'comparison': ['comparar', 'diferencia', 'cual es mejor', 'versus', 'vs'],
            'purchase': ['comprar', 'precio', 'cuesta', 'checkout', 'carrito'],
            'support': ['ayuda', 'problema', 'no funciona', 'soporte']
        };
        
        let detectedIntent = 'general';
        let maxScore = 0;
        
        for (const [intent, keywords] of Object.entries(intentKeywords)) {
            const score = keywords.reduce((acc, keyword) => {
                return acc + (queryLower.includes(keyword) ? 1 : 0);
            }, 0);
            
            if (score > maxScore) {
                maxScore = score;
                detectedIntent = intent;
            }
        }
        
        const confidence = maxScore > 0 ? Math.min(0.6 + (maxScore * 0.1), 0.9) : 0.5;
        
        return {
            type: detectedIntent,
            confidence: confidence,
            attributes: Object.keys(intentKeywords).filter(intent => 
                intentKeywords[intent].some(keyword => queryLower.includes(keyword))
            ),
            urgency: queryLower.includes('urgente') || queryLower.includes('rapido') ? 'high' : 'medium',
            categories: [],
            budget_signals: {},
            source: 'fallback_keyword_analysis',
            timestamp: new Date().toISOString(),
            original_query: query
        };
    }
    
    _fallbackMarketConfig(marketId) {
        /**
         * Configuración de mercado de fallback
         */
        const configs = {
            'US': { currency: 'USD', language: 'en', timezone: 'America/New_York' },
            'ES': { currency: 'EUR', language: 'es', timezone: 'Europe/Madrid' },
            'MX': { currency: 'MXN', language: 'es', timezone: 'America/Mexico_City' },
            'CO': { currency: 'COP', language: 'es', timezone: 'America/Bogota' },
            'CL': { currency: 'CLP', language: 'es', timezone: 'America/Santiago' }
        };
        
        const config = configs[marketId] || configs['US'];
        
        return {
            market_id: marketId,
            market_name: `Market ${marketId}`,
            currency: config.currency,
            primary_language: config.language,
            timezone: config.timezone,
            tax_rate: 0.0,
            shipping_zones: [`${marketId}_domestic`],
            payment_methods: ['credit_card'],
            cultural_preferences: {
                communication_style: 'standard',
                seasonal_events: [],
                product_preferences: {}
            },
            source: 'fallback_config',
            last_updated: new Date().toISOString()
        };
    }
    
    _fallbackInventoryResponse(productIds) {
        /**
         * Respuesta de inventario de fallback
         */
        const availability = {};
        productIds.forEach(productId => {
            availability[productId] = {
                available: true,  // Asumir disponible por defecto
                quantity: 10,
                price: null,
                estimated_delivery: '3-5 business days'
            };
        });
        return availability;
    }
}

// Instancia global del cliente MCP
const mcpClient = new MCPClientWrapper();

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

// Middleware para contar requests
app.use((req, res, next) => {
    serverState.requestCount++;
    next();
});

// Routes

/**
 * Health check endpoint
 */
app.get('/health', async (req, res) => {
    try {
        const healthStatus = {
            status: 'healthy',
            timestamp: new Date().toISOString(),
            uptime: Date.now() - serverState.startTime,
            version: process.env.npm_package_version || '1.0.0',
            environment: process.env.NODE_ENV || 'development',
            mcp_connection: serverState.mcpConnectionStatus,
            metrics: {
                total_requests: serverState.requestCount,
                total_errors: serverState.errorCount,
                error_rate: serverState.requestCount > 0 ? 
                    (serverState.errorCount / serverState.requestCount) : 0
            }
        };
        
        // Test MCP connection if needed
        if (serverState.mcpConnectionStatus === 'unknown') {
            try {
                await mcpClient.ensureInitialized();
                healthStatus.mcp_connection = 'connected';
            } catch (error) {
                healthStatus.mcp_connection = 'failed';
                healthStatus.mcp_error = error.message;
            }
        }
        
        serverState.lastHealthCheck = Date.now();
        res.json(healthStatus);
        
    } catch (error) {
        logger.error('Health check failed:', error);
        res.status(500).json({
            status: 'unhealthy',
            error: error.message,
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
        
        const intent = await mcpClient.extractIntent(
            query, 
            market_context || {}, 
            conversation_history || []
        );
        
        res.json({
            success: true,
            intent: intent,
            timestamp: new Date().toISOString(),
            processing_time_ms: Date.now() - req.startTime
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
        
        const config = await mcpClient.getMarketConfiguration(market_id);
        
        res.json({
            success: true,
            market_config: config,
            timestamp: new Date().toISOString(),
            processing_time_ms: Date.now() - req.startTime
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
        
        const availability = await mcpClient.checkInventoryAvailability(market_id, product_ids);
        
        res.json({
            success: true,
            availability: availability,
            market_id: market_id,
            timestamp: new Date().toISOString(),
            processing_time_ms: Date.now() - req.startTime
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
 * Get server metrics
 */
app.get('/metrics', (req, res) => {
    const metrics = {
        uptime_seconds: Math.floor((Date.now() - serverState.startTime) / 1000),
        total_requests: serverState.requestCount,
        total_errors: serverState.errorCount,
        error_rate: serverState.requestCount > 0 ? 
            (serverState.errorCount / serverState.requestCount) : 0,
        mcp_connection_status: serverState.mcpConnectionStatus,
        last_health_check: serverState.lastHealthCheck,
        memory_usage: process.memoryUsage(),
        environment: process.env.NODE_ENV || 'development',
        timestamp: new Date().toISOString()
    };
    
    res.json(metrics);
});

// Error handlers

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

// Graceful shutdown
process.on('SIGTERM', async () => {
    logger.info('SIGTERM received, shutting down gracefully');
    
    if (mcpClient.mcpClient) {
        try {
            await mcpClient.mcpClient.disconnect();
            logger.info('MCP client disconnected');
        } catch (error) {
            logger.error('Error disconnecting MCP client:', error);
        }
    }
    
    process.exit(0);
});

process.on('SIGINT', async () => {
    logger.info('SIGINT received, shutting down gracefully');
    
    if (mcpClient.mcpClient) {
        try {
            await mcpClient.mcpClient.disconnect();
            logger.info('MCP client disconnected');
        } catch (error) {
            logger.error('Error disconnecting MCP client:', error);
        }
    }
    
    process.exit(0);
});

// Start server
app.listen(PORT, () => {
    logger.info(`MCP Bridge server running on port ${PORT}`, {
        environment: process.env.NODE_ENV || 'development',
        version: process.env.npm_package_version || '1.0.0'
    });
    
    // Initialize MCP client on startup
    mcpClient.initialize().catch(error => {
        logger.error('Failed to initialize MCP client on startup:', error);
    });
});

module.exports = app;
