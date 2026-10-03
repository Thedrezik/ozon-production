import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['push-worker.js', 'icon.svg', 'icon-192.png', 'icon-512.png'],
      manifest: {
        name: 'Ozon Production',
        short_name: 'Production',
        description: 'Управление мебельным производством',
        theme_color: '#193f69',
        background_color: '#f3f5f8',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        globIgnores: ['**/scanner-*.js', '**/Orders-*.js', '**/ManagerTasks-*.js', '**/Procurement-*.js', '**/Analytics-*.js', '**/PushSettings-*.js', '**/AuditLog-*.js', '**/ProductProfiles-*.js', '**/OzonIntegration-*.js', '**/Notifications-*.js'],
        importScripts: ['/push-worker.js'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [{
          urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
          handler: 'NetworkOnly',
        }],
      },
    }),
  ],
  build: { rollupOptions: { output: { manualChunks: id => id.includes('@zxing') ? 'scanner' : undefined } } },
  server: { proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true,
    configure: proxy => proxy.on('proxyReq', request => request.setHeader('Origin', 'http://localhost:8000')) } } },
})
