(function() {
  'use strict';
  
  // Configuration
  const WIDGET_VERSION = '1.0.0';
  const DEFAULT_CONFIG = {
    theme: 'light',
    position: 'bottom-right',
    marketId: 'US',
    language: 'en'
  };

  // Load widget script
  function loadWidget(config) {
    return new Promise((resolve, reject) => {
      // Check if widget is already loaded
      if (window.RetailRecommenderWidget) {
        resolve(window.RetailRecommenderWidget);
        return;
      }

      // Create script element
      const script = document.createElement('script');
      script.src = config.scriptUrl || `${config.apiUrl}/static/widget/widget.js`;
      script.onload = () => {
        if (window.RetailRecommenderWidget) {
          resolve(window.RetailRecommenderWidget);
        } else {
          reject(new Error('Widget failed to load'));
        }
      };
      script.onerror = () => reject(new Error('Failed to load widget script'));
      
      // Add script to head
      document.head.appendChild(script);
    });
  }

  // Initialize widget
  async function initWidget(userConfig) {
    try {
      // Merge with defaults
      const config = { ...DEFAULT_CONFIG, ...userConfig };
      
      // Validate required fields
      if (!config.apiUrl || !config.apiKey) {
        throw new Error('apiUrl and apiKey are required');
      }

      // Load and initialize widget
      const widget = await loadWidget(config);
      widget.init(config);
      
      console.log(`✅ Retail Recommender Widget v${WIDGET_VERSION} loaded successfully`);
      
    } catch (error) {
      console.error('❌ Widget initialization failed:', error);
    }
  }

  // Expose global initialization function
  window.initRetailRecommenderWidget = initWidget;

  // Auto-initialize based on script data attributes
  document.addEventListener('DOMContentLoaded', () => {
    const currentScript = document.currentScript || 
      document.querySelector('script[src*="embed.js"]');
    
    if (currentScript && currentScript.hasAttribute('data-auto-init')) {
      const apiUrl = currentScript.getAttribute('data-api-url');
      const apiKey = currentScript.getAttribute('data-api-key');
      
      if (apiUrl && apiKey) {
        initWidget({
          apiUrl,
          apiKey,
          marketId: currentScript.getAttribute('data-market-id') || 'US',
          theme: currentScript.getAttribute('data-theme') || 'light',
        });
      }
    }
  });
})();