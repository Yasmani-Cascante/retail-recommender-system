import { createRoot } from 'react-dom/client';
import { ChatWidget } from './components/ChatWidget';
import type { WidgetConfig } from './types/widget';
import './styles/main.css';

// Global widget interface
declare global {
  interface Window {
    RetailRecommenderWidget: {
      init: (config: WidgetConfig & { containerId?: string }) => void;
      destroy: () => void;
      show: () => void;
      hide: () => void;
    };
  }
}

class WidgetManager {
  private root: any = null;
  private container: HTMLElement | null = null;

  init(config: WidgetConfig & { containerId?: string }) {
    try {
      // Validate required config
      if (!config.apiUrl || !config.apiKey) {
        throw new Error('Widget requires apiUrl and apiKey');
      }

      // Create or find container
      if (config.containerId) {
        this.container = document.getElementById(config.containerId);
        if (!this.container) {
          throw new Error(`Container with id "${config.containerId}" not found`);
        }
      } else {
        // Create default container
        this.container = document.createElement('div');
        this.container.id = 'retail-recommender-widget';
        this.container.style.position = 'fixed';
        this.container.style.zIndex = '9999';
        this.container.style.pointerEvents = 'none';
        this.container.style.top = '0';
        this.container.style.left = '0';
        this.container.style.width = '100%';
        this.container.style.height = '100%';
        document.body.appendChild(this.container);
      }

      // Enable pointer events for the widget
      this.container.style.pointerEvents = 'none';
      this.container.style.position = 'relative';

      // Create React root and render
      this.root = createRoot(this.container);
      this.root.render(
        <div style={{ pointerEvents: 'auto' }}>
          <ChatWidget config={config} />
        </div>
      );

      console.log('✅ Retail Recommender Widget initialized successfully');

    } catch (error) {
      console.error('❌ Widget initialization failed:', error);
      throw error;
    }
  }

  destroy() {
    if (this.root) {
      this.root.unmount();
      this.root = null;
    }

    if (this.container && !this.container.id.includes('custom')) {
      document.body.removeChild(this.container);
      this.container = null;
    }

    console.log('🗑️ Widget destroyed');
  }

  show() {
    if (this.container) {
      this.container.style.display = 'block';
    }
  }

  hide() {
    if (this.container) {
      this.container.style.display = 'none';
    }
  }
}

// Create global widget instance
const widgetManager = new WidgetManager();

// Expose global API
window.RetailRecommenderWidget = {
  init: (config) => widgetManager.init(config),
  destroy: () => widgetManager.destroy(),
  show: () => widgetManager.show(),
  hide: () => widgetManager.hide(),
};

// Auto-initialize if config is provided via data attributes
document.addEventListener('DOMContentLoaded', () => {
  const scripts = document.querySelectorAll('script[data-rr-auto-init]');
  
  scripts.forEach((script) => {
    const apiUrl = script.getAttribute('data-api-url');
    const apiKey = script.getAttribute('data-api-key');
    const marketId = script.getAttribute('data-market-id') || 'US';
    const theme = script.getAttribute('data-theme') || 'light';
    
    if (apiUrl && apiKey) {
      widgetManager.init({
        apiUrl,
        apiKey,
        marketId,
        theme: theme as 'light' | 'dark' | 'auto',
      });
    }
  });
});