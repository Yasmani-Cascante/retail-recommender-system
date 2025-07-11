// simple-test.js - Test simplificado sin muchas dependencias
import axios from 'axios';

const BASE_URL = 'http://localhost:3001';

console.log('🧪 Starting simple tests...');

async function simpleHealthTest() {
    try {
        console.log('\n1️⃣ Testing health endpoint...');
        const response = await axios.get(`${BASE_URL}/health`);
        console.log('✅ Health check passed:', response.data.status);
        console.log('🏪 Shopify connection:', response.data.shopify_connection);
        return true;
    } catch (error) {
        console.log('❌ Health check failed:', error.message);
        return false;
    }
}

async function simpleIntentTest() {
    try {
        console.log('\n2️⃣ Testing intent extraction...');
        const response = await axios.post(`${BASE_URL}/mcp/extract-intent`, {
            query: "busco zapatos deportivos",
            market_context: { market_id: "CL" }
        });
        
        console.log('✅ Intent extraction passed');
        console.log('🧠 Detected intent:', response.data.intent?.type);
        console.log('📊 Confidence:', response.data.intent?.confidence);
        return true;
    } catch (error) {
        console.log('❌ Intent extraction failed:', error.message);
        if (error.response) {
            console.log('📄 Response status:', error.response.status);
            console.log('📄 Response data:', error.response.data);
        }
        return false;
    }
}

async function simpleMarketTest() {
    try {
        console.log('\n3️⃣ Testing market configuration...');
        const response = await axios.post(`${BASE_URL}/mcp/markets/get-config`, {
            market_id: "CL"
        });
        
        console.log('✅ Market config passed');
        console.log('💰 Currency:', response.data.market_config?.currency);
        console.log('🌍 Language:', response.data.market_config?.primary_language);
        return true;
    } catch (error) {
        console.log('❌ Market config failed:', error.message);
        if (error.response) {
            console.log('📄 Response status:', error.response.status);
        }
        return false;
    }
}

async function runTests() {
    console.log('🚀 Simple MCP Bridge Tests');
    console.log('=' .repeat(40));
    
    let passed = 0;
    let total = 3;
    
    if (await simpleHealthTest()) passed++;
    if (await simpleIntentTest()) passed++;
    if (await simpleMarketTest()) passed++;
    
    console.log('\n' + '='.repeat(40));
    console.log(`📊 Results: ${passed}/${total} tests passed`);
    console.log(passed === total ? '🎉 ALL TESTS PASSED!' : '⚠️ SOME TESTS FAILED');
    
    process.exit(passed === total ? 0 : 1);
}

// Ejecutar tests
runTests().catch(error => {
    console.error('💥 Test runner crashed:', error);
    process.exit(1);
});