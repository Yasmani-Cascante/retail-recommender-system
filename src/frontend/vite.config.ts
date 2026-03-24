import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * VITE CONFIG — Widget embebible para AI-Shoppings
 *
 * PROBLEMA RESUELTO (23/03/2026):
 * En modo `lib`, Vite genera el CSS en un archivo `style.css` separado.
 * Ese archivo NUNCA se carga en Shopify porque el embed solo inyecta el .cjs.
 * Resultado: widget sin estilos en producción (texto plano sin layout).
 *
 * SOLUCIÓN:
 * El CSS de Tailwind se convierte en un string literal e inyectado en el
 * bundle JS mediante el plugin `vite-plugin-css-injected-by-js`.
 * Al cargar widget.umd.cjs, el CSS se inyecta automáticamente en <head>.
 * Esto es el patrón estándar de widgets embebibles (Intercom, Crisp, etc.).
 *
 * INSTALACIÓN NECESARIA:
 *   npm install -D vite-plugin-css-injected-by-js
 */
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'

export default defineConfig({
  plugins: [
    react(),
    // ← Inyecta el CSS compilado de Tailwind dentro del bundle JS.
    // No genera style.css separado — todo en un solo archivo .cjs.
    cssInjectedByJsPlugin(),
  ],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/main.tsx'),
      name: 'RetailRecommenderWidget',
      fileName: 'widget',
      formats: ['umd']
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {}
      }
    },
    outDir: '../../static/widget',
    emptyOutDir: true,
    sourcemap: true,
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true
      }
    }
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV)
  }
})
