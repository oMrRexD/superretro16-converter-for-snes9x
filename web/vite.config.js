import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf8'),
);

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      manifestFilename: 'manifest.webmanifest',
      manifest: {
        name: 'SaveShift',
        short_name: 'SaveShift',
        description: 'Convert save states between SuperRetro16 and Snes9X.',
        id: '/',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait-primary',
        background_color: '#0a0612',
        theme_color: '#0a0612',
        icons: [
          {
            src: '/icons/web-app-manifest-192x192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any maskable',
          },
          {
            src: '/icons/web-app-manifest-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        cleanupOutdatedCaches: true,
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webp,woff,woff2,wasm,zip,json,pybundle,webmanifest}'],
        ignoreURLParametersMatching: [/^v$/],
        maximumFileSizeToCacheInBytes: 20 * 1024 * 1024,
        navigateFallback: '/index.html',
      },
    }),
  ],
  define: {
    __SAVESHIFT_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    target: 'es2020',
  },
});
