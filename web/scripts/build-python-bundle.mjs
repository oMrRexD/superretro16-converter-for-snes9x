import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = path.resolve(WEB_ROOT, '..');
const OUT_DIR = path.join(WEB_ROOT, 'public');
const OUT_FILE = path.join(OUT_DIR, 'save-converter-python.pybundle');

const INCLUDE_ROOTS = [
  ['converter', path.join(ROOT, 'converter')],
  ['web_bridge.py', path.join(WEB_ROOT, 'python_bridge', 'web_bridge.py')],
];

const ZIP_TIMESTAMP = new Date(1980, 0, 1, 0, 0, 0);

const FORBIDDEN_EXT = new Set([
  '.smc', '.sfc', '.fig', '.swc', '.rom',
  '.srm', '.000', '.001', '.002', '.003', '.004', '.005', '.006', '.007', '.008', '.009',
  '.snd', '.pcm', '.wav', '.rgb565',
  '.png', '.jpg', '.jpeg', '.gif', '.webp',
  '.exe', '.dll', '.so', '.apk', '.aab',
  '.zip', '.7z', '.rar', '.log',
]);

function posixPath(p) {
  return p.split(path.sep).join('/');
}

function shouldInclude(filePath) {
  const base = path.basename(filePath);
  if (base === '__pycache__' || base.endsWith('.pyc')) return false;
  const ext = path.extname(filePath).toLowerCase();
  if (FORBIDDEN_EXT.has(ext)) return false;
  return ext === '.py' || ext === '.json';
}

function collectFiles(label, absPath, out = []) {
  const stat = fs.statSync(absPath);
  if (stat.isFile()) {
    if (shouldInclude(absPath)) {
      out.push({ archiveName: posixPath(label), absPath });
    }
    return out;
  }
  for (const entry of fs.readdirSync(absPath, { withFileTypes: true })) {
    if (entry.name === '__pycache__') continue;
    const childAbs = path.join(absPath, entry.name);
    const childLabel = path.join(label, entry.name);
    if (entry.isDirectory()) {
      collectFiles(childLabel, childAbs, out);
    } else if (shouldInclude(childAbs)) {
      out.push({ archiveName: posixPath(childLabel), absPath: childAbs });
    }
  }
  return out;
}

function makeCrc32Table() {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[i] = c >>> 0;
  }
  return table;
}

const CRC_TABLE = makeCrc32Table();

function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (const b of buf) {
    c = CRC_TABLE[(c ^ b) & 0xFF] ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function dosDateTime(date) {
  const year = Math.max(1980, date.getFullYear());
  const dosTime =
    (date.getHours() << 11) |
    (date.getMinutes() << 5) |
    Math.floor(date.getSeconds() / 2);
  const dosDate =
    ((year - 1980) << 9) |
    ((date.getMonth() + 1) << 5) |
    date.getDate();
  return { dosTime, dosDate };
}

function u16(v) {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(v & 0xFFFF, 0);
  return b;
}

function u32(v) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(v >>> 0, 0);
  return b;
}

function makeStoredZip(files) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  const stamp = dosDateTime(ZIP_TIMESTAMP);

  for (const file of files) {
    const name = Buffer.from(file.archiveName, 'utf8');
    const data = fs.readFileSync(file.absPath);
    const crc = crc32(data);
    const local = Buffer.concat([
      u32(0x04034B50),
      u16(20),
      u16(0),
      u16(0),
      u16(stamp.dosTime),
      u16(stamp.dosDate),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      name,
    ]);
    localParts.push(local, data);

    const central = Buffer.concat([
      u32(0x02014B50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(stamp.dosTime),
      u16(stamp.dosDate),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      name,
    ]);
    centralParts.push(central);
    offset += local.length + data.length;
  }

  const centralDir = Buffer.concat(centralParts);
  const end = Buffer.concat([
    u32(0x06054B50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(centralDir.length),
    u32(offset),
    u16(0),
  ]);
  return Buffer.concat([...localParts, centralDir, end]);
}

const files = INCLUDE_ROOTS.flatMap(([label, absPath]) => collectFiles(label, absPath));
files.sort((a, b) => a.archiveName.localeCompare(b.archiveName));

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(OUT_FILE, makeStoredZip(files));
console.log(`Built ${path.relative(ROOT, OUT_FILE)} with ${files.length} files`);
