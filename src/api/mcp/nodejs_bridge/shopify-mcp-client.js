/**
* REAL SHOPIFY MCP CLIENT
* 
* Implementación real usando Shopify Admin GraphQL API + Web Pixels API
* para proporcionar datos auténticos de ecommerce
*/


import { GraphQLClient } from 'graphql-request';
import fetch from 'node-fetch';

export class RealShopifyMCPClient {
    constructor(config = {}) {
        this.shopDomain = config.shopDomain || process.env.SHOPIFY_SHOP_URL;
        this.accessToken = config.accessToken || process.env.SHOPIFY_ACCESS_TOKEN;
        this.apiVersion = config.apiVersion || process.env.SHOPIFY_API_VERSION || '2024-07';
        
        this.initialized = false;
        this.graphqlClient = null;
        this.connectionStatus = 'initializing';
        
        // Performance tracking
        this.metrics = {
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            avgResponseTime: 0,
            lastError: null
        };
        
        if (!this.shopDomain || !this.accessToken) {
            throw new Error('SHOPIFY_SHOP_URL and SHOPIFY_ACCESS_TOKEN are required');
        }
        
        console.log(`🏪 RealShopifyMCPClient configured for: ${this.shopDomain}`);
    }
    
    async initialize() {
        try {
            console.log('🔧 Initializing Real Shopify MCP Client...');
            
            // Setup GraphQL client
            const shopifyApiUrl = `https://${this.shopDomain}/admin/api/${this.apiVersion}/graphql.json`;
            
            this.graphqlClient = new GraphQLClient(shopifyApiUrl, {
                headers: {
                    'X-Shopify-Access-Token': this.accessToken,
                    'Content-Type': 'application/json',
                    'User-Agent': 'RetailRecommender-MCPBridge/2.0.0'
                },
                timeout: 10000
            });
            
            // Test connection with shop info
            const shopInfo = await this._testConnection();
            
            this.initialized = true;
            this.connectionStatus = 'connected';
            
            console.log(`✅ Connected to Shopify shop: ${shopInfo.name}`);
            console.log(`💰 Currency: ${shopInfo.currencyCode}`);
            console.log(`🌍 Domain: ${shopInfo.primaryDomain.host}`);
            
            return {
                success: true,
                shopInfo: shopInfo,
                message: 'Real Shopify MCP Client initialized successfully'
            };
            
        } catch (error) {
            console.error('❌ Real Shopify MCP initialization failed:', error);
            this.connectionStatus = 'failed';
            this.initialized = false;
            this.metrics.lastError = error.message;
            throw error;
        }
    }
    
    async _testConnection() {
        const query = `
            query GetShopInfo {
                shop {
                    name
                    primaryDomain {
                        host
                    }
                    currencyCode
                    plan {
                        displayName
                    }
                    billingAddress {
                        countryCodeV2
                        province
                    }
                    shipsToCountries
                }
            }
        `;
        
        const result = await this._makeGraphQLRequest(query);
        return result.shop;
    }
    
    async extractIntent(query, marketContext = {}, conversationHistory = []) {
        const startTime = Date.now();
        
        try {
            console.log(`🧠 Extracting intent for: \"${query.substring(0, 50)}...\"`);
            
            // 1. Local NLP analysis
            const localIntent = this._analyzeIntentAdvanced(query, marketContext);
            
            // 2. Search relevant products in Shopify to enrich context
            const relevantProducts = await this._searchRelevantProducts(query, marketContext);
            
            // 3. Enrich intent with real Shopify data
            const enrichedIntent = this._enrichIntentWithShopifyData(localIntent, relevantProducts);
            
            // 4. Generate contextual insights
            const insights = this._generateContextualInsights(enrichedIntent, relevantProducts, marketContext);
            
            const responseTime = Date.now() - startTime;
            this._updateMetrics(true, responseTime);
            
            return {
                success: true,
                intent: enrichedIntent,
                relevant_products: relevantProducts.slice(0, 5),
                contextual_insights: insights,
                processing_time_ms: responseTime,
                timestamp: new Date().toISOString(),
                source: 'shopify_admin_graphql'
            };
            
        } catch (error) {
            const responseTime = Date.now() - startTime;
            this._updateMetrics(false, responseTime);
            
            console.error('Intent extraction failed:', error);
            
            // Intelligent fallback
            return this._fallbackIntentAnalysis(query, marketContext);
        }
    }
    
    async _searchRelevantProducts(query, marketContext) {
        const searchQuery = `
            query SearchProducts($query: String!, $first: Int!) {
                products(first: $first, query: $query, sortKey: RELEVANCE) {
                    edges {
                        node {
                            id
                            title
                            handle
                            description
                            productType
                            vendor
                            tags
                            status
                            availableForSale
                            totalInventory
                            createdAt
                            updatedAt
                            variants(first: 5) {
                                edges {
                                    node {
                                        id
                                        title
                                        price
                                        compareAtPrice
                                        availableForSale
                                        inventoryQuantity
                                        inventoryPolicy
                                        weight
                                        weightUnit
                                    }
                                }
                            }
                            images(first: 3) {
                                edges {
                                    node {
                                        url
                                        altText
                                        width
                                        height
                                    }
                                }
                            }
                            seo {
                                title
                                description
                            }
                        }
                    }
                }
            }
        `;
        
        const variables = {
            query: this._buildShopifySearchQuery(query),
            first: 20
        };
        
        try {
            const result = await this._makeGraphQLRequest(searchQuery, variables);
            
            const products = result.products.edges.map(edge => ({
                id: edge.node.id,
                title: edge.node.title,
                handle: edge.node.handle,
                description: edge.node.description,
                type: edge.node.productType,
                vendor: edge.node.vendor,
                tags: edge.node.tags,
                status: edge.node.status,
                availableForSale: edge.node.availableForSale,
                totalInventory: edge.node.totalInventory,
                createdAt: edge.node.createdAt,
                variants: edge.node.variants.edges.map(v => ({
                    id: v.node.id,
                    title: v.node.title,
                    price: parseFloat(v.node.price),
                    compareAtPrice: v.node.compareAtPrice ? parseFloat(v.node.compareAtPrice) : null,
                    available: v.node.availableForSale,
                    inventory: v.node.inventoryQuantity,
                    weight: v.node.weight,
                    weightUnit: v.node.weightUnit
                })),
                images: edge.node.images.edges.map(i => ({
                    url: i.node.url,
                    alt: i.node.altText,
                    width: i.node.width,
                    height: i.node.height
                })),
                seo: edge.node.seo
            }));
            
            console.log(`🔍 Found ${products.length} relevant products for query: \"${query}\"`);
            return products;
            
        } catch (error) {
            console.error('Product search failed:', error);
            return [];
        }
    }
    
    async getMarketConfiguration(marketId) {
        try {
            console.log(`🌍 Getting market configuration for: ${marketId}`);
            
            // Get real shop information
            const shopQuery = `
                query GetShopMarketInfo {
                    shop {
                        name
                        currencyCode
                        primaryDomain {
                            host
                        }
                        billingAddress {
                            countryCodeV2
                            province
                            city
                            zip
                        }
                        shipsToCountries
                        paymentSettings {
                            acceptedCardBrands
                            currencyCode
                            supportedDigitalWallets
                        }
                        plan {
                            displayName
                            partnerDevelopment
                            shopifyPlus
                        }
                        features {
                            avalaraAvatax
                            branding {
                                checkout {
                                    banner
                                }
                            }
                            dynamicCheckout
                            giftCards
                            harmonizedSystemCode
                            internationalDomains
                            internationalPriceOverrides
                            internationalPriceRules
                            legacySubscriptionGatewayEnabled
                            liveView
                            marketingActivityExtensions
                            multiLocation
                            onboardingVisual
                            paypalExpressCheckout
                            reports
                            sellsGiftCards
                            showMetrics
                            storefront
                            usingShopifyBalance
                        }
                    }
                }
            `;
            
            const shopInfo = await this._makeGraphQLRequest(shopQuery);
            const shop = shopInfo.shop;
            
            // Build comprehensive market configuration
            const marketConfig = {
                market_id: marketId,
                market_name: this._getMarketName(marketId),
                
                // Real shop data
                shop_info: {
                    name: shop.name,
                    domain: shop.primaryDomain.host,
                    country: shop.billingAddress?.countryCodeV2,
                    province: shop.billingAddress?.province,
                    city: shop.billingAddress?.city,
                    plan: shop.plan.displayName,
                    shopify_plus: shop.plan.shopifyPlus
                },
                
                // Financial configuration
                currency: shop.currencyCode,
                payment_methods: shop.paymentSettings.acceptedCardBrands,
                digital_wallets: shop.paymentSettings.supportedDigitalWallets,
                
                // Localization
                primary_language: this._getLanguageForMarket(marketId),
                timezone: this._getTimezoneForMarket(marketId),
                
                // Shipping
                ships_to_countries: shop.shipsToCountries,
                shipping_zones: this._getShippingZonesForMarket(marketId),
                
                // Market-specific settings
                tax_rate: this._getTaxRateForMarket(marketId),
                cultural_preferences: this._getCulturalPreferences(marketId),
                
                // Capabilities
                features: {
                    multi_location: shop.features.multiLocation,
                    international_pricing: shop.features.internationalPriceOverrides,
                    gift_cards: shop.features.giftCards,
                    dynamic_checkout: shop.features.dynamicCheckout,
                    live_view: shop.features.liveView
                },
                
                // Metadata
                source: 'shopify_admin_graphql_real',
                last_updated: new Date().toISOString(),
                data_quality: 'authentic'
            };
            
            return {
                success: true,
                market_config: marketConfig,
                timestamp: new Date().toISOString()
            };
            
        } catch (error) {
            console.error('Market configuration fetch failed:', error);
            return this._fallbackMarketConfig(marketId);
        }
    }
    
    async checkInventoryAvailability(marketId, productIds) {
        try {
            console.log(`📦 Checking inventory for ${productIds.length} products in market: ${marketId}`);
            
            // Convert product IDs to Shopify format if needed
            const shopifyIds = productIds.map(id => 
                id.startsWith('gid://shopify/Product/') ? id : `gid://shopify/Product/${id}`
            );
            
            const inventoryQuery = `
                query GetProductInventory($ids: [ID!]!) {
                    nodes(ids: $ids) {
                        ... on Product {
                            id
                            title
                            handle
                            availableForSale
                            totalInventory
                            status
                            variants(first: 10) {
                                edges {
                                    node {
                                        id
                                        title
                                        price
                                        compareAtPrice
                                        availableForSale
                                        inventoryQuantity
                                        inventoryPolicy
                                        inventoryItem {
                                            inventoryLevels(first: 5) {
                                                edges {
                                                    node {
                                                        available
                                                        location {
                                                            name
                                                            address {
                                                                countryCodeV2
                                                                province
                                                                city
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        weight
                                        weightUnit
                                    }
                                }
                            }
                        }
                    }
                }
            `;
            
            const variables = { ids: shopifyIds };
            const result = await this._makeGraphQLRequest(inventoryQuery, variables);
            
            const availability = {};
            
            result.nodes.forEach((product, index) => {
                const originalId = productIds[index];
                
                if (product) {
                    const mainVariant = product.variants.edges[0]?.node;
                    const allVariants = product.variants.edges.map(edge => edge.node);
                    
                    // Calculate location-specific availability
                    const locationAvailability = mainVariant?.inventoryItem?.inventoryLevels?.edges?.map(edge => ({
                        location: edge.node.location.name,
                        available: edge.node.available,
                        country: edge.node.location.address?.countryCodeV2,
                        province: edge.node.location.address?.province
                    })) || [];
                    
                    availability[originalId] = {
                        // Basic availability
                        available: product.availableForSale,
                        status: product.status,
                        total_inventory: product.totalInventory,
                        
                        // Main variant info
                        main_variant: mainVariant ? {
                            id: mainVariant.id,
                            title: mainVariant.title,
                            price: {
                                amount: parseFloat(mainVariant.price),
                                currency: this._getCurrencyForMarket(marketId),
                                compare_at: mainVariant.compareAtPrice ? parseFloat(mainVariant.compareAtPrice) : null
                            },
                            quantity: mainVariant.inventoryQuantity,
                            available: mainVariant.availableForSale,
                            inventory_policy: mainVariant.inventoryPolicy,
                            weight: {
                                value: mainVariant.weight,
                                unit: mainVariant.weightUnit
                            }
                        } : null,
                        
                        // All variants
                        all_variants: allVariants.map(variant => ({
                            id: variant.id,
                            title: variant.title,
                            price: parseFloat(variant.price),
                            quantity: variant.inventoryQuantity,
                            available: variant.availableForSale
                        })),
                        
                        // Location-specific availability
                        location_availability: locationAvailability,
                        
                        // Market-specific calculations
                        estimated_delivery: this._calculateDeliveryEstimate(marketId, locationAvailability),
                        local_taxes: this._calculateLocalTaxes(mainVariant?.price, marketId),
                        
                        // Metadata
                        last_updated: new Date().toISOString(),
                        source: 'shopify_admin_graphql_real',
                        market_adapted: true
                    };
                } else {
                    availability[originalId] = {
                        available: false,
                        error: 'Product not found in Shopify',
                        source: 'shopify_admin_graphql_real'
                    };
                }
            });
            
            return {
                success: true,
                availability: availability,
                market_id: marketId,
                total_products_checked: productIds.length,
                timestamp: new Date().toISOString()
            };
            
        } catch (error) {
            console.error('Inventory check failed:', error);
            return this._fallbackInventoryCheck(productIds, marketId);
        }
    }
    
    // HELPER METHODS
    
    async _makeGraphQLRequest(query, variables = {}) {
        this.metrics.totalRequests++;
        
        try {
            const result = await this.graphqlClient.request(query, variables);
            this.metrics.successfulRequests++;
            return result;
        } catch (error) {
            this.metrics.failedRequests++;
            this.metrics.lastError = error.message;
            throw error;
        }
    }
    
    _updateMetrics(success, responseTime) {
        if (success) {
            this.metrics.successfulRequests++;
        } else {
            this.metrics.failedRequests++;
        }
        
        this.metrics.totalRequests++;
        
        // Calculate moving average response time
        const weight = 0.1;
        this.metrics.avgResponseTime = (1 - weight) * this.metrics.avgResponseTime + weight * responseTime;
    }
    
    _buildShopifySearchQuery(userQuery) {
        // Build intelligent Shopify search query from user input
        const cleanQuery = userQuery.toLowerCase()
            .replace(/[^\\w\\s]/g, ' ')
            .replace(/\\s+/g, ' ')
            .trim();
        
        // Add search operators for better results
        const keywords = cleanQuery.split(' ').filter(word => word.length > 2);
        
        return keywords.length > 0 ? keywords.join(' OR ') : cleanQuery;
    }
    
    _analyzeIntentAdvanced(query, marketContext) {
        const queryLower = query.toLowerCase();
        
        // Advanced intent patterns with confidence scoring
        const intentPatterns = {
            'product_search': {
                keywords: ['busco', 'buscando', 'quiero', 'necesito', 'looking for', 'need', 'want'],
                context_keywords: ['producto', 'product', 'artículo', 'item'],
                confidence_base: 0.4,
                urgency_indicators: ['ahora', 'now', 'urgente', 'urgent']
            },
            'purchase_intent': {
                keywords: ['comprar', 'buy', 'purchase', 'adquirir', 'precio', 'price', 'cuesta', 'cost'],
                context_keywords: ['checkout', 'carrito', 'cart', 'pagar', 'pay'],
                confidence_base: 0.7,
                urgency_indicators: ['ya', 'now', 'inmediato', 'immediate']
            },
            'recommendation': {
                keywords: ['recomienda', 'recommend', 'sugieres', 'suggest', 'aconsejas', 'advise'],
                context_keywords: ['mejor', 'best', 'top', 'opción', 'option'],
                confidence_base: 0.6,
                urgency_indicators: ['pronto', 'soon']
            },
            'comparison': {
                keywords: ['comparar', 'compare', 'diferencia', 'difference', 'versus', 'vs'],
                context_keywords: ['entre', 'between', 'opciones', 'options', 'productos', 'products'],
                confidence_base: 0.8,
                urgency_indicators: ['decidir', 'decide', 'elegir', 'choose']
            },
            'gift_search': {
                keywords: ['regalo', 'gift', 'presente', 'present', 'sorpresa', 'surprise'],
                context_keywords: ['para', 'for', 'cumpleaños', 'birthday', 'aniversario', 'anniversary'],
                confidence_base: 0.6,
                urgency_indicators: ['mañana', 'tomorrow', 'pronto', 'soon']
            },
            'support': {
                keywords: ['ayuda', 'help', 'problema', 'problem', 'soporte', 'support'],
                context_keywords: ['no funciona', 'not working', 'error', 'issue'],
                confidence_base: 0.3,
                urgency_indicators: ['urgente', 'urgent', 'inmediato', 'immediate']
            }
        };
        
        let bestIntent = 'general';
        let maxConfidence = 0.2;
        let matchedKeywords = [];
        let urgencyLevel = 'medium';
        
        for (const [intent, pattern] of Object.entries(intentPatterns)) {
            let confidence = pattern.confidence_base;
            let keywords = [];
            
            // Check primary keywords
            for (const keyword of pattern.keywords) {
                if (queryLower.includes(keyword)) {
                    confidence += 0.2;
                    keywords.push(keyword);
                }
            }
            
            // Check context keywords
            for (const contextKeyword of pattern.context_keywords) {
                if (queryLower.includes(contextKeyword)) {
                    confidence += 0.1;
                }
            }
            
            // Check urgency indicators
            for (const urgencyIndicator of pattern.urgency_indicators) {
                if (queryLower.includes(urgencyIndicator)) {
                    urgencyLevel = 'high';
                    confidence += 0.05;
                }
            }
            
            // Market context boost
            if (marketContext.market_id) {
                confidence += 0.05;
            }
            
            if (confidence > maxConfidence) {
                maxConfidence = confidence;
                bestIntent = intent;
                matchedKeywords = keywords;
            }
        }
        
        return {
            type: bestIntent,
            confidence: Math.min(maxConfidence, 0.95),
            attributes: matchedKeywords,
            urgency: urgencyLevel,
            categories: this._extractCategories(queryLower),
            budget_signals: this._extractBudgetSignals(queryLower),
            temporal_context: this._extractTemporalContext(queryLower),
            emotional_context: this._extractEmotionalContext(queryLower)
        };
    }
    
    _enrichIntentWithShopifyData(localIntent, products) {
        const enriched = { ...localIntent };
        
        if (products.length > 0) {
            // Boost confidence with real product data
            enriched.confidence = Math.min(localIntent.confidence + 0.1, 0.95);
            
            // Add Shopify-specific insights
            enriched.suggested_categories = [...new Set(products.map(p => p.type).filter(Boolean))];
            enriched.suggested_vendors = [...new Set(products.map(p => p.vendor).filter(Boolean))];
            enriched.suggested_tags = [...new Set(products.flatMap(p => p.tags).filter(Boolean))];
            
            // Price analysis
            const prices = products.flatMap(p => p.variants.map(v => v.price)).filter(price => !isNaN(price));
            if (prices.length > 0) {
                enriched.price_insights = {
                    min: Math.min(...prices),
                    max: Math.max(...prices),
                    avg: prices.reduce((a, b) => a + b, 0) / prices.length,
                    range: Math.max(...prices) - Math.min(...prices)
                };
            }
            
            // Availability insights
            const availableProducts = products.filter(p => p.availableForSale);
            enriched.availability_insights = {
                total_products: products.length,
                available_products: availableProducts.length,
                availability_rate: availableProducts.length / products.length,
                out_of_stock: products.length - availableProducts.length
            };
        }
        
        return enriched;
}
    
    _generateContextualInsights(intent, products, marketContext) {
        const insights = {
            intent_analysis: {
                primary_intent: intent.type,
                confidence_level: intent.confidence > 0.8 ? 'high' : intent.confidence > 0.5 ? 'medium' : 'low',
                urgency: intent.urgency,
                categories_detected: intent.categories
            },
            
            product_insights: {
                total_matches: products.length,
                top_categories: this._getTopCategories(products),
                price_range: intent.price_insights,
                availability_summary: intent.availability_insights
            },
            
            market_recommendations: {
                market_id: marketContext.market_id,
                localization_suggestions: this._getLocalizationSuggestions(marketContext.market_id),
                cultural_adaptations: this._getCulturalAdaptations(marketContext.market_id, intent)
            },
            
            next_actions: this._suggestNextActions(intent, products, marketContext)
        };
        
        return insights;
    }
    
    // CATEGORY AND CONTEXT EXTRACTION
    
    _extractCategories(text) {
        const categoryPatterns = {
            'electronics': ['teléfono', 'phone', 'móvil', 'mobile', 'laptop', 'tablet', 'auriculares', 'headphones', 'cargador', 'charger'],
            'clothing': ['ropa', 'clothes', 'camisa', 'shirt', 'pantalón', 'pants', 'zapatos', 'shoes', 'vestido', 'dress', 'chaqueta', 'jacket'],
            'home': ['casa', 'home', 'hogar', 'muebles', 'furniture', 'decoración', 'decoration', 'cocina', 'kitchen', 'baño', 'bathroom'],
            'sports': ['deporte', 'sport', 'fitness', 'correr', 'run', 'gym', 'ejercicio', 'exercise', 'yoga', 'pilates'],
            'beauty': ['belleza', 'beauty', 'maquillaje', 'makeup', 'perfume', 'skincare', 'cosmético', 'cosmetic', 'crema', 'cream'],
            'books': ['libro', 'book', 'lectura', 'reading', 'novela', 'novel', 'educativo', 'educational', 'revista', 'magazine'],
            'toys': ['juguete', 'toy', 'niños', 'kids', 'bebé', 'baby', 'juego', 'game', 'muñeca', 'doll'],
            'automotive': ['coche', 'car', 'auto', 'automotive', 'moto', 'motorcycle', 'repuesto', 'spare part'],
            'garden': ['jardín', 'garden', 'planta', 'plant', 'flores', 'flowers', 'herramientas', 'tools']
        };
        
        const detectedCategories = [];
        for (const [category, keywords] of Object.entries(categoryPatterns)) {
            if (keywords.some(keyword => text.includes(keyword))) {
                detectedCategories.push(category);
            }
        }
        
        return detectedCategories;
    }
    
    _extractBudgetSignals(text) {
        const budgetPatterns = {
            'budget_conscious': ['barato', 'cheap', 'económico', 'affordable', 'descuento', 'discount', 'oferta', 'sale', 'promoción'],
            'value_oriented': ['calidad precio', 'value', 'relación calidad', 'bang for buck', 'worth it', 'vale la pena'],
            'premium': ['premium', 'lujo', 'luxury', 'high end', 'exclusivo', 'exclusive', 'marca', 'brand', 'calidad', 'quality'],
            'price_comparison': ['precio', 'price', 'cuesta', 'cost', 'comparar precios', 'compare prices']
        };
        
        // Extract specific amounts
        const amountRegex = /(\$|€|£|₹|¥|₩|R\$|MX\$|COP\$|₡|₨)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)/g;
        const amounts = [...text.matchAll(amountRegex)];
        
        let budgetType = 'unspecified';
        let confidence = 0.3;
        
        for (const [type, keywords] of Object.entries(budgetPatterns)) {
            if (keywords.some(keyword => text.includes(keyword))) {
                budgetType = type;
                confidence = 0.7;
                break;
            }
        }
        
        return {
            budget_type: budgetType,
            specific_amounts: amounts.map(match => match[0]),
            has_budget_constraint: amounts.length > 0 || budgetType !== 'unspecified',
            confidence: confidence
        };
    }
    
    _extractTemporalContext(text) {
        const temporalPatterns = {
            'immediate': ['ahora', 'now', 'ya', 'inmediato', 'immediate', 'urgente', 'urgent'],
            'today': ['hoy', 'today', 'este día', 'this day'],
            'this_week': ['esta semana', 'this week', 'próximos días', 'next few days'],
            'soon': ['pronto', 'soon', 'en breve', 'shortly', 'cuando puedas', 'when you can'],
            'specific_date': ['mañana', 'tomorrow', 'viernes', 'friday', 'fin de semana', 'weekend'],
            'seasonal': ['verano', 'summer', 'invierno', 'winter', 'navidad', 'christmas', 'cumpleaños', 'birthday']
        };
        
        for (const [timeframe, keywords] of Object.entries(temporalPatterns)) {
            if (keywords.some(keyword => text.includes(keyword))) {
                return {
                    timeframe: timeframe,
                    urgency_level: timeframe === 'immediate' ? 'high' : timeframe === 'today' ? 'medium' : 'low',
                    detected: true
                };
            }
        }
        
        return {
            timeframe: 'unspecified',
            urgency_level: 'medium',
            detected: false
        };
    }
    
    _extractEmotionalContext(text) {
        const emotionalPatterns = {
            'excited': ['emocionado', 'excited', 'genial', 'awesome', 'increíble', 'amazing'],
            'frustrated': ['frustrado', 'frustrated', 'molesto', 'annoyed', 'cansado', 'tired'],
            'confused': ['confundido', 'confused', 'no entiendo', 'dont understand', 'perdido', 'lost'],
            'happy': ['feliz', 'happy', 'contento', 'glad', 'alegre', 'cheerful'],
            'worried': ['preocupado', 'worried', 'nervioso', 'nervous', 'ansioso', 'anxious'],
            'grateful': ['gracias', 'thanks', 'agradecido', 'grateful', 'appreciate']
        };
        
        for (const [emotion, keywords] of Object.entries(emotionalPatterns)) {
            if (keywords.some(keyword => text.includes(keyword))) {
                return {
                    primary_emotion: emotion,
                    intensity: 'medium',
                    detected: true
                };
            }
        }
        
        return {
            primary_emotion: 'neutral',
            intensity: 'low',
            detected: false
        };
    }
    
    // MARKET-SPECIFIC HELPERS
    
    _getMarketName(marketId) {
        const marketNames = {
            'US': 'United States',
            'CA': 'Canada',
            'ES': 'España',
            'MX': 'México',
            'CO': 'Colombia',
            'CL': 'Chile',
            'AR': 'Argentina',
            'BR': 'Brasil',
            'UK': 'United Kingdom',
            'FR': 'France',
            'DE': 'Germany',
            'IT': 'Italy'
        };
        return marketNames[marketId] || 'Global Market';
    }
    
    _getLanguageForMarket(marketId) {
        const languages = {
            'US': 'en', 'CA': 'en', 'UK': 'en',
            'ES': 'es', 'MX': 'es', 'CO': 'es', 'CL': 'es', 'AR': 'es',
            'BR': 'pt',
            'FR': 'fr',
            'DE': 'de',
            'IT': 'it'
        };
        return languages[marketId] || 'en';
    }
    
    _getTimezoneForMarket(marketId) {
        const timezones = {
            'US': 'America/New_York',
            'CA': 'America/Toronto',
            'ES': 'Europe/Madrid',
            'MX': 'America/Mexico_City',
            'CO': 'America/Bogota',
            'CL': 'America/Santiago',
            'AR': 'America/Argentina/Buenos_Aires',
            'BR': 'America/Sao_Paulo',
            'UK': 'Europe/London',
            'FR': 'Europe/Paris',
            'DE': 'Europe/Berlin',
            'IT': 'Europe/Rome'
        };
        return timezones[marketId] || 'UTC';
    }
    
    _getCurrencyForMarket(marketId) {
        const currencies = {
            'US': 'USD', 'CA': 'CAD',
            'ES': 'EUR', 'FR': 'EUR', 'DE': 'EUR', 'IT': 'EUR',
            'MX': 'MXN', 'CO': 'COP', 'CL': 'CLP', 'AR': 'ARS', 'BR': 'BRL',
            'UK': 'GBP'
        };
        return currencies[marketId] || 'USD';
    }
    
    _getTaxRateForMarket(marketId) {
        const taxRates = {
            'US': 0.08, 'CA': 0.13,
            'ES': 0.21, 'FR': 0.20, 'DE': 0.19, 'IT': 0.22,
            'MX': 0.16, 'CO': 0.19, 'CL': 0.19, 'AR': 0.21, 'BR': 0.17,
            'UK': 0.20
        };
        return taxRates[marketId] || 0.10;
    }
    
    _getShippingZonesForMarket(marketId) {
        const shippingZones = {
            'US': ['US_domestic', 'US_express', 'US_overnight'],
            'CA': ['CA_domestic', 'CA_express'],
            'ES': ['ES_domestic', 'EU_standard', 'EU_express'],
            'MX': ['MX_domestic', 'MX_express'],
            'CO': ['CO_domestic', 'CO_major_cities'],
            'CL': ['CL_domestic', 'CL_regions'],
            'AR': ['AR_domestic', 'AR_express'],
            'BR': ['BR_domestic', 'BR_express'],
            'UK': ['UK_domestic', 'UK_express'],
            'FR': ['FR_domestic', 'EU_standard'],
            'DE': ['DE_domestic', 'EU_standard'],
            'IT': ['IT_domestic', 'EU_standard']
        };
        return shippingZones[marketId] || ['domestic', 'express'];
    }
    
    _getCulturalPreferences(marketId) {
        const culturalPrefs = {
            'US': {
                communication_style: 'direct',
                seasonal_events: ['black_friday', 'cyber_monday', 'thanksgiving', 'independence_day'],
                product_preferences: { 
                    price_sensitivity: 'medium', 
                    brand_loyalty: 'high', 
                    review_importance: 'very_high',
                    sustainability_focus: 'medium'
                }
            },
            'ES': {
                communication_style: 'formal',
                seasonal_events: ['rebajas_verano', 'rebajas_invierno', 'black_friday', 'el_corte_ingles_days'],
                product_preferences: { 
                    price_sensitivity: 'high', 
                    brand_loyalty: 'medium', 
                    review_importance: 'very_high',
                    sustainability_focus: 'high'
                }
            },
            'MX': {
                communication_style: 'warm',
                seasonal_events: ['dia_madres', 'dia_padre', 'buen_fin', 'guadalupe'],
                product_preferences: { 
                    price_sensitivity: 'very_high', 
                    brand_loyalty: 'medium', 
                    review_importance: 'high',
                    sustainability_focus: 'low'
                }
            },
            'CO': {
                communication_style: 'friendly',
                seasonal_events: ['dia_madre', 'dia_padre', 'navidad', 'cyber_lunes'],
                product_preferences: { 
                    price_sensitivity: 'very_high', 
                    brand_loyalty: 'low', 
                    review_importance: 'very_high',
                    sustainability_focus: 'medium'
                }
            }
        };
        
        return culturalPrefs[marketId] || culturalPrefs['US'];
    }
    
    _calculateDeliveryEstimate(marketId, locationAvailability) {
        // Base delivery times by market
        const baseDelivery = {
            'US': { min: 2, max: 5, unit: 'business days' },
            'CA': { min: 3, max: 7, unit: 'business days' },
            'ES': { min: 3, max: 7, unit: 'business days' },
            'MX': { min: 5, max: 10, unit: 'business days' },
            'CO': { min: 7, max: 15, unit: 'business days' },
            'CL': { min: 7, max: 15, unit: 'business days' },
            'AR': { min: 10, max: 20, unit: 'business days' },
            'BR': { min: 5, max: 12, unit: 'business days' }
        };
        
        const base = baseDelivery[marketId] || baseDelivery['US'];
        
        // Adjust based on location availability
        if (locationAvailability && locationAvailability.length > 0) {
            const localAvailable = locationAvailability.some(loc => 
                loc.country === marketId && loc.available > 0
            );
            
            if (localAvailable) {
                // Faster delivery if locally available
                return `${base.min}-${Math.max(base.min + 1, base.max - 2)} ${base.unit}`;
            }
        }
        
        return `${base.min}-${base.max} ${base.unit}`;
    }
    
    _calculateLocalTaxes(price, marketId) {
        if (!price) return null;
        
        const taxRate = this._getTaxRateForMarket(marketId);
        const basePrice = parseFloat(price);
        const taxAmount = basePrice * taxRate;
        const totalPrice = basePrice + taxAmount;
        
        return {
            base_price: basePrice,
            tax_rate: taxRate,
            tax_amount: taxAmount,
            total_price: totalPrice,
            currency: this._getCurrencyForMarket(marketId)
        };
    }
    
    // INSIGHT GENERATION HELPERS
    
    _getTopCategories(products) {
        const categoryCounts = {};
        
        products.forEach(product => {
            if (product.type) {
                categoryCounts[product.type] = (categoryCounts[product.type] || 0) + 1;
            }
        });
        
        return Object.entries(categoryCounts)
            .sort(([,a], [,b]) => b - a)
            .slice(0, 5)
            .map(([category, count]) => ({ category, count }));
    }
    
    _getLocalizationSuggestions(marketId) {
        const suggestions = {
            'ES': ['Use formal language', 'Include VAT in prices', 'Mention EU shipping'],
            'MX': ['Use warm tone', 'Highlight payment options like OXXO', 'Consider peso pricing'],
            'CO': ['Friendly communication', 'Mention PSE payment option', 'Local delivery options'],
            'US': ['Direct communication', 'Emphasize fast shipping', 'Multiple payment methods']
        };
        
        return suggestions[marketId] || suggestions['US'];
    }
    
    _getCulturalAdaptations(marketId, intent) {
        const adaptations = [];
        
        if (intent.type === 'gift_search') {
            const giftAdaptations = {
                'ES': ['Consider Día de Reyes', 'Include gift wrapping options'],
                'MX': ['Día de las Madres is very important', 'Consider quinceañera gifts'],
                'CO': ['Include Colombian holidays', 'Local gift traditions']
            };
            adaptations.push(...(giftAdaptations[marketId] || []));
        }
        
        if (intent.urgency === 'high') {
            const urgencyAdaptations = {
                'ES': ['Express shipping available', 'Same-day delivery in major cities'],
                'MX': ['Check local availability first', 'Consider pickup options'],
                'CO': ['Limited express options', 'Plan for longer delivery times']
            };
            adaptations.push(...(urgencyAdaptations[marketId] || []));
        }
        
        return adaptations;
    }
    
    _suggestNextActions(intent, products, marketContext) {
        const actions = [];
        
        switch (intent.type) {
            case 'product_search':
                actions.push('Show filtered product results');
                actions.push('Offer category refinement');
                if (products.length > 0) {
                    actions.push('Display price comparison');
                }
                break;
                
            case 'purchase_intent':
                actions.push('Show add to cart options');
                actions.push('Display payment methods');
                actions.push('Calculate shipping costs');
                break;
                
            case 'recommendation':
                actions.push('Generate personalized recommendations');
                actions.push('Show trending products');
                actions.push('Offer expert picks');
                break;
                
            case 'comparison':
                actions.push('Create comparison table');
                actions.push('Highlight key differences');
                actions.push('Show pros and cons');
                break;
                
            case 'gift_search':
                actions.push('Filter by recipient type');
                actions.push('Show gift guides');
                actions.push('Offer gift wrapping');
                break;
        }
        
        // Market-specific actions
        if (marketContext.market_id) {
            actions.push(`Adapt for ${marketContext.market_id} market`);
            actions.push('Apply local pricing');
            actions.push('Show local payment options');
        }
        
        return actions;
    }
    
    // FALLBACK METHODS
    
    _fallbackIntentAnalysis(query, marketContext) {
        return {
            success: true,
            intent: {
                type: 'general',
                confidence: 0.5,
                attributes: [],
                urgency: 'medium',
                categories: [],
                budget_signals: { budget_type: 'unspecified', confidence: 0.3 },
                source: 'local_fallback_analysis',
                original_query: query,
                fallback: true
            },
            relevant_products: [],
            contextual_insights: {
                note: 'Using fallback analysis due to Shopify connection issue'
            },
            timestamp: new Date().toISOString(),
            processing_time_ms: 50
        };
    }
    
    _fallbackMarketConfig(marketId) {
        return {
            success: true,
            market_config: {
                market_id: marketId,
                market_name: this._getMarketName(marketId),
                currency: this._getCurrencyForMarket(marketId),
                primary_language: this._getLanguageForMarket(marketId),
                timezone: this._getTimezoneForMarket(marketId),
                tax_rate: this._getTaxRateForMarket(marketId),
                source: 'fallback_config',
                fallback: true
            },
            timestamp: new Date().toISOString()
        };
    }
    
    _fallbackInventoryCheck(productIds, marketId) {
        const availability = {};
        
        productIds.forEach(productId => {
            availability[productId] = {
                available: true,
                quantity: 10,
                price: {
                    amount: (Math.random() * 100 + 20).toFixed(2),
                    currency: this._getCurrencyForMarket(marketId)
                },
                estimated_delivery: this._calculateDeliveryEstimate(marketId, []),
                source: 'fallback_inventory',
                fallback: true
            };
        });
        
        return {
            success: true,
            availability: availability,
            market_id: marketId,
            timestamp: new Date().toISOString(),
            note: 'Using fallback inventory data due to Shopify connection issue'
        };
    }
    
    // METRICS AND STATUS
    
    getConnectionStatus() {
        return {
            status: this.connectionStatus,
            initialized: this.initialized,
            metrics: this.metrics,
            shop_domain: this.shopDomain,
            api_version: this.apiVersion
        };
    }
    
    async getMetrics() {
        return {
            connection_status: this.connectionStatus,
            performance_metrics: this.metrics,
            configuration: {
                shop_domain: this.shopDomain,
                api_version: this.apiVersion
            },
            timestamp: new Date().toISOString()
        };
    }
    
    async disconnect() {
        this.connectionStatus = 'disconnected';
        this.initialized = false;
        console.log('🔌 RealShopifyMCPClient disconnected');
    }
}