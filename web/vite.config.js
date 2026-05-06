import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf8'),
);

export default defineConfig({
  plugins: [react()],
  define: {
    __SAVESHIFT_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    target: 'es2020',
  },
});
