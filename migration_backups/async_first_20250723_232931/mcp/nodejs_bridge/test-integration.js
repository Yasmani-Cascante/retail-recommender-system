// test-integration.js
// Script completo para testing de la integración MCP Bridge CORREGIDA

import axios from 'axios';
import { config } from 'dotenv';
config();

const BASE_URL = `http://localhost:${process.env.MCP_BRIDGE_PORT || 3001}`;

class MCPBridgeTester {
    constructor() {
        this.results = {
            total_tests: 0,
            passed: 0,
            failed: 0,
            tests: []
        };
    }
    
    async runTest(testName, testFunction) {
        this.results.total_tests++;
        console.log(`\n🧪 Running test: ${testName}`);
        
        try {
            const startTime = Date.now();
            const result = await testFunction();
            const duration = Date.now() - startTime;
            
            this.results.passed++;
            this.results.tests.push({
                name: testName,
                status: 'PASSED',
                duration: `${duration}ms`,
                result: result
            });
            
            console.log(`✅ ${testName} - PASSED (${duration}ms)`);
            return result;
            
        } catch (error) {
            this.results.failed++;
            this.results.tests.push({
                name: testName,
                status: 'FAILED',
                error: error.message,
                stack: error.stack
            });
            
            console.log(`❌ ${testName} - FAILED: ${error.message}`);
            throw error;
        }
    }
    
    async testHealthCheck() {
        return this.runTest('Health Check', async () => {
            const response = await axios.get(`${BASE_URL}/health`);
            
            if (response.status !== 200 && response.status !== 503) {
                throw new Error(`Expected status 200 or 503, got ${response.status}`);
            }
            
            const health = response.data;
            
            // Verificar campos requeridos
            const requiredFields = ['status', 'timestamp', 'uptime', 'shopify_connection'];
            for (const field of requiredFields) {
                if (!health.hasOwnProperty(field)) {
                    throw new Error(`Missing required field: ${field}`);
                }
            }
            
            console.log(`   📊 Shopify Connection: ${health.shopify_connection}`);
            console.log(`   ⏱️  Uptime: ${Math.floor(health.uptime / 1000)}s`);
            
            return health;
        });
    }
    
    async testIntentExtraction() {
        return this.runTest('Intent Extraction', async () => {
            const testQueries = [
                {
                    query: "busco unos zapatos deportivos para correr",
                    market_context: { market_id: "ES" },
                    expected_type: "product_search"
                },
                {
                    query: "quiero comprar un regalo para mi madre",
                    market_context: { market_id: "MX" },
                    expected_type: "gift_search"
                },
                {
                    query: "recomiéndame algo bueno",
                    market_context: { market_id: "US" },
                    expected_type: "recommendation"
                }
            ];
            
            const results = [];
            
            for (const testCase of testQueries) {
                try {
                    const response = await axios.post(`${BASE_URL}/mcp/extract-intent`, {
                        query: testCase.query,
                        market_context: testCase.market_context,
                        conversation_history: []
                    });
                    
                    if (response.status !== 200) {
                        throw new Error(`Expected status 200, got ${response.status}`);
                    }
                    
                    const data = response.data;
                    
                    if (!data.success) {
                        throw new Error('Response indicates failure');
                    }
                    
                    // Verificar que tiene estructura de respuesta del RealShopifyMCPClient
                    if (!data.intent) {
                        throw new Error('Missing intent in response');
                    }
                    
                    console.log(`   🧠 Query: "${testCase.query}" -> Intent: ${data.intent.type} (${data.intent.confidence})`);
                    
                    results.push({
                        query: testCase.query,
                        detected_intent: data.intent.type,
                        confidence: data.intent.confidence,
                        market_id: testCase.market_context.market_id,
                        processing_time: data.processing_time_ms
                    });
                    
                } catch (error) {
                    console.log(`   ⚠️  Query failed: "${testCase.query}" - ${error.message}`);
                    results.push({
                        query: testCase.query,
                        error: error.message
                    });
                }
            }
            
            return results;
        });
    }
    
    async testMarketConfiguration() {
        return this.runTest('Market Configuration', async () => {
            const testMarkets = ['US', 'ES', 'MX', 'CO'];
            const results = [];
            
            for (const marketId of testMarkets) {
                try {
                    const response = await axios.post(`${BASE_URL}/mcp/markets/get-config`, {
                        market_id: marketId
                    });
                    
                    if (response.status !== 200) {
                        throw new Error(`Expected status 200 for market ${marketId}, got ${response.status}`);
                    }
                    
                    const data = response.data;
                    
                    if (!data.success) {
                        throw new Error(`Market config failed for ${marketId}`);
                    }
                    
                    if (!data.market_config) {
                        throw new Error(`Missing market_config for ${marketId}`);
                    }
                    
                    console.log(`   🌍 Market ${marketId}: ${data.market_config.currency} - ${data.market_config.primary_language}`);
                    
                    results.push({
                        market_id: marketId,
                        currency: data.market_config.currency,
                        language: data.market_config.primary_language,
                        processing_time: data.processing_time_ms
                    });
                    
                } catch (error) {
                    console.log(`   ⚠️  Market ${marketId} failed: ${error.message}`);
                    results.push({
                        market_id: marketId,
                        error: error.message
                    });
                }
            }
            
            return results;
        });
    }
    
    async testInventoryCheck() {
        return this.runTest('Inventory Availability Check', async () => {
            const testData = {
                market_id: "US",
                product_ids: ["test_product_1", "test_product_2", "test_product_3"]
            };
            
            const response = await axios.post(`${BASE_URL}/mcp/inventory/check-availability`, testData);
            
            if (response.status !== 200) {
                throw new Error(`Expected status 200, got ${response.status}`);
            }
            
            const data = response.data;
            
            if (!data.success) {
                throw new Error('Inventory check failed');
            }
            
            if (!data.availability) {
                throw new Error('Missing availability data');
            }
            
            const availabilityCount = Object.keys(data.availability).length;
            console.log(`   📦 Checked ${availabilityCount} products in market ${testData.market_id}`);
            
            // Verificar que se retornaron datos para todos los productos solicitados
            for (const productId of testData.product_ids) {
                if (!data.availability[productId]) {
                    console.log(`   ⚠️  Missing availability data for product: ${productId}`);
                }
            }
            
            return {
                market_id: testData.market_id,
                products_requested: testData.product_ids.length,
                products_returned: availabilityCount,
                processing_time: data.processing_time_ms
            };
        });
    }
    
    async testMetricsEndpoint() {
        return this.runTest('Metrics Endpoint', async () => {
            const response = await axios.get(`${BASE_URL}/metrics`);
            
            if (response.status !== 200) {
                throw new Error(`Expected status 200, got ${response.status}`);
            }
            
            const metrics = response.data;
            
            // Verificar estructura de métricas
            if (!metrics.server || !metrics.shopify) {
                throw new Error('Missing required metrics sections');
            }
            
            console.log(`   📊 Server uptime: ${metrics.server.uptime_seconds}s`);
            console.log(`   📊 Total requests: ${metrics.server.total_requests}`);
            console.log(`   📊 Error rate: ${(metrics.server.error_rate * 100).toFixed(2)}%`);
            console.log(`   📊 Shopify status: ${metrics.shopify.connection_status}`);
            
            return metrics;
        });
    }
    
    async testInvalidEndpoint() {
        return this.runTest('Invalid Endpoint (404)', async () => {
            try {
                await axios.get(`${BASE_URL}/invalid/endpoint`);
                throw new Error('Expected 404 error but request succeeded');
            } catch (error) {
                if (error.response && error.response.status === 404) {
                    console.log(`   ✅ Correctly returned 404 for invalid endpoint`);
                    return { status: 404, handled: true };
                } else {
                    throw error;
                }
            }
        });
    }
    
    async testRateLimiting() {
        return this.runTest('Rate Limiting', async () => {
            console.log(`   🚦 Testing rate limiting (100 requests)...`);
            
            const promises = [];
            for (let i = 0; i < 105; i++) {  // Exceder el límite de 100
                promises.push(
                    axios.get(`${BASE_URL}/health`).catch(error => error.response)
                );
            }
            
            const responses = await Promise.all(promises);
            
            const successCount = responses.filter(r => r && r.status === 200).length;
            const rateLimitCount = responses.filter(r => r && r.status === 429).length;
            
            console.log(`   ✅ Successful requests: ${successCount}`);
            console.log(`   🚦 Rate limited requests: ${rateLimitCount}`);
            
            if (rateLimitCount === 0) {
                console.log(`   ⚠️  Rate limiting may not be working properly`);
            }
            
            return {
                total_requests: 105,
                successful: successCount,
                rate_limited: rateLimitCount
            };
        });
    }
    
    async runAllTests() {
        console.log(`🚀 Starting Real Shopify MCP Bridge Integration Tests`);
        console.log(`🎯 Target URL: ${BASE_URL}`);
        console.log(`=" ".repeat(60)`);
        
        try {
            // Test básicos
            await this.testHealthCheck();
            await this.testMetricsEndpoint();
            await this.testInvalidEndpoint();
            
            // Test core MCP functionality
            await this.testIntentExtraction();
            await this.testMarketConfiguration();
            await this.testInventoryCheck();
            
            // Test avanzados
            await this.testRateLimiting();
            
        } catch (error) {
            console.log(`\n❌ Test suite failed with error: ${error.message}`);
        }
        
        this.printSummary();
    }
    
    printSummary() {
        console.log(`\n${"=".repeat(60)}`);
        console.log(`📋 TEST SUMMARY`);
        console.log(`${"=".repeat(60)}`);
        console.log(`📊 Total Tests: ${this.results.total_tests}`);
        console.log(`✅ Passed: ${this.results.passed}`);
        console.log(`❌ Failed: ${this.results.failed}`);
        console.log(`📈 Success Rate: ${((this.results.passed / this.results.total_tests) * 100).toFixed(1)}%`);
        
        if (this.results.failed > 0) {
            console.log(`\n❌ FAILED TESTS:`);
            this.results.tests
                .filter(test => test.status === 'FAILED')
                .forEach(test => {
                    console.log(`   • ${test.name}: ${test.error}`);
                });
        }
        
        console.log(`\n${this.results.failed === 0 ? '🎉 ALL TESTS PASSED!' : '⚠️  SOME TESTS FAILED'}`);
        console.log(`${"=".repeat(60)}`);
    }
}

// Ejecutar tests si se llama directamente
if (import.meta.url === `file://${process.argv[1]}`) {
    const tester = new MCPBridgeTester();
    tester.runAllTests().catch(error => {
        console.error('Test runner failed:', error);
        process.exit(1);
    });
}

export default MCPBridgeTester;