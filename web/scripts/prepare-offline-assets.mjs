import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDir = path.join(root, 'public');
const pyodideDir = path.dirname(require.resolve('pyodide/package.json'));

const pyodideFiles = [
  'pyodide.js',
  'pyodide.asm.js',
  'pyodide.asm.wasm',
  'python_stdlib.zip',
  'pyodide-lock.json',
];

const iconFiles = [
  'apple-touch-icon.png',
  'favicon-96x96.png',
  'favicon.ico',
  'web-app-manifest-192x192.png',
  'web-app-manifest-512x512.png',
];

async function copyFileSet(files, fromDir, toDir) {
  await fs.rm(toDir, { recursive: true, force: true });
  await fs.mkdir(toDir, { recursive: true });
  await Promise.all(
    files.map((file) => fs.copyFile(path.join(fromDir, file), path.join(toDir, file))),
  );
}

await fs.mkdir(publicDir, { recursive: true });
await copyFileSet(pyodideFiles, pyodideDir, path.join(publicDir, 'pyodide'));
await copyFileSet(iconFiles, path.join(root, 'assets', 'favicon'), path.join(publicDir, 'icons'));

console.log(`Prepared offline assets in ${path.relative(root, publicDir)}`);
