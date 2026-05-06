let worker;
let nextId = 1;
const pending = new Map();

const DEFAULT_PROGRESS_LABELS = {
  read: 'Reading file...',
  pythonReady: 'Python converter ready.',
  loadingPyodide: 'Loading Pyodide...',
  downloadingBundle: 'Loading converter bundle...',
  preparingConverter: 'Preparing local converter...',
  analyzing: 'Inspecting file...',
  converting: 'Converting...',
  preparingDownload: 'Preparing download...',
  finished: 'Finished.',
  unknownError: 'Unknown failure',
  batchLabel: 'Save-state batch',
  batchFailed: 'file(s) failed and were left out of the ZIP.',
  zipInfoName: 'saveshift-info.zip',
  zipSramName: 'extracted-sram.zip',
  zipConvertedName: 'converted-saves.zip',
};

function getWorker() {
  if (!worker) {
    worker = new Worker(new URL('./converter.worker.js', import.meta.url));
    worker.addEventListener('message', (event) => {
      const msg = event.data || {};
      const entry = pending.get(msg.id);
      if (!entry) return;
      if (msg.type === 'progress') {
        entry.onProgress?.(msg.progress);
      } else if (msg.type === 'result') {
        pending.delete(msg.id);
        entry.resolve(msg.result);
      } else if (msg.type === 'error') {
        pending.delete(msg.id);
        entry.reject(new Error(msg.error || 'Worker failed'));
      }
    });
    worker.addEventListener('error', (event) => {
      for (const [id, entry] of pending) {
        entry.reject(new Error(event.message || 'Worker failed'));
        pending.delete(id);
      }
    });
  }
  return worker;
}

export async function runConversion(action, file, onProgress, progressLabels = DEFAULT_PROGRESS_LABELS) {
  const labels = { ...DEFAULT_PROGRESS_LABELS, ...progressLabels };
  onProgress?.({ label: labels.read, percent: 4 });
  const buffer = await file.arrayBuffer();
  const id = nextId++;
  const activeWorker = getWorker();
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject, onProgress });
    activeWorker.postMessage(
      {
        id,
        type: 'run',
        action,
        filename: file.name || 'save',
        bytes: buffer,
        progressLabels: labels,
      },
      [buffer],
    );
  });
}

export async function runBatchConversion(action, files, onProgress, progressLabels = DEFAULT_PROGRESS_LABELS) {
  const labels = { ...DEFAULT_PROGRESS_LABELS, ...progressLabels };
  const list = Array.from(files);
  if (list.length === 1) {
    const result = await runConversion(action, list[0], onProgress, labels);
    return {
      ...result,
      outputName: result.ok ? outputNameForAction(action, list[0].name, result.outputName) : result.outputName,
      batch: false,
    };
  }

  const outputs = [];
  const errors = [];
  for (let index = 0; index < list.length; index += 1) {
    const file = list[index];
    const basePercent = (index / list.length) * 100;
    const span = 100 / list.length;
    const result = await runConversion(action, file, (progress) => {
      onProgress?.({
        label: `${index + 1}/${list.length} - ${file.name}: ${progress.label}`,
        percent: Math.min(99, basePercent + ((progress.percent || 0) / 100) * span),
      });
    }, labels);
    if (result.ok) {
      const outputName = outputNameForAction(action, file.name, result.outputName);
      outputs.push({
        name: uniqueZipName(outputName, outputs.map((item) => item.name)),
        bytes: decodeBase64(result.dataBase64),
      });
    } else {
      errors.push({ file: file.name, error: result.error || labels.unknownError });
    }
  }

  if (outputs.length === 0) {
    return {
      ok: false,
      batch: true,
      error: errors.map((item) => `${item.file}: ${item.error}`).join('\n'),
      info: { type: 'batch', size: list.reduce((sum, file) => sum + file.size, 0) },
    };
  }

  const zipBytes = createStoredZip(outputs);
  const outputName = batchOutputName(action, labels);
  return {
    ok: true,
    batch: true,
    outputName,
    mime: 'application/zip',
    dataBase64: bytesToBase64(zipBytes),
    size: zipBytes.length,
    outputInfo: {
      type: 'zip',
      label: 'ZIP archive',
      filename: outputName,
      size: zipBytes.length,
      crc32: crc32Hex(zipBytes),
    },
    info: {
      type: 'batch',
      label: labels.batchLabel,
      size: list.reduce((sum, file) => sum + file.size, 0),
      files: outputs.map((item) => ({ code: item.name, size: item.bytes.length })),
      warnings: errors.map((item) => `${item.file}: ${item.error}`),
    },
    error: errors.length ? `${errors.length} ${labels.batchFailed}` : '',
  };
}

export function decodeBase64(base64) {
  const binary = atob(base64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

export function makeDownload(result) {
  const bytes = decodeBase64(result.dataBase64);
  const blob = new Blob([bytes], { type: result.mime || 'application/octet-stream' });
  return {
    url: URL.createObjectURL(blob),
    size: bytes.length,
  };
}

function batchOutputName(action, labels = DEFAULT_PROGRESS_LABELS) {
  if (action === 'info') return labels.zipInfoName;
  if (action === 'extract') return labels.zipSramName;
  return labels.zipConvertedName;
}

export function outputNameForAction(action, inputName, fallback) {
  const base = baseName(inputName);
  if (action === 'sr16-to-snes9x') {
    const slot = sr16OutputSlot(inputName) ?? 0;
    return `${base}.${String(slot).padStart(3, '0')}`;
  }
  if (action === 'sr16-to-snes9x-explus') {
    const snes9xSlotNumber = sr16OutputSlot(inputName) ?? 0;
    const width = snes9xSlotNumber < 100 ? 2 : 3;
    return `${base}.${String(snes9xSlotNumber).padStart(width, '0')}.frz`;
  }
  if (action === 'snes9x-to-snes9x-explus') {
    const slot = snes9xSlot(inputName);
    const snes9xSlotNumber = slot ?? 0;
    const width = snes9xSlotNumber < 100 ? 2 : 3;
    return `${base}.${String(snes9xSlotNumber).padStart(width, '0')}.frz`;
  }
  if (action === 'snes9x-explus-to-snes9x') {
    const slot = snes9xSlot(inputName) ?? 0;
    return `${base}.${String(slot).padStart(3, '0')}`;
  }
  if (action === 'snes9x-to-sr16') {
    const slot = snes9xSlot(inputName);
    const sr16SlotNumber = slot === 0 || slot == null ? 1 : slot;
    return `${base}.s${String(sr16SlotNumber).padStart(2, '0')}`;
  }
  if (action === 'extract') return `${base}.srm`;
  if (action === 'info') return `${base}.info.json`;
  return fallback || `${base}.bin`;
}

function baseName(filename = 'save') {
  const name = filename.split(/[\\/]/).pop() || 'save';
  const slot = sr16Slot(name);
  if (slot != null) {
    const stem = name.replace(/\.s\d{1,3}$/i, '');
    if (slot === 1 && sr16ParentheticalSlotHint(name) != null) {
      return stem.replace(/\(\d{1,3}\)$/i, '').trim() || 'save';
    }
    return stem || 'save';
  }
  if (snes9xSlot(name) != null) {
    return name.replace(/\.[0-9]{1,3}\.frz$/i, '').replace(/\.[^.]+$/, '') || 'save';
  }
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(0, dot) : name;
}

function sr16OutputSlot(filename = '') {
  const slot = sr16Slot(filename);
  if (slot == null) return null;
  if (slot === 1) return sr16ParentheticalSlotHint(filename) ?? 0;
  return slot;
}

function sr16Slot(filename = '') {
  const match = /\.s(\d{1,3})$/i.exec(filename);
  if (!match) return null;
  const value = Number.parseInt(match[1], 10);
  return value >= 0 && value <= 999 ? value : null;
}

function sr16ParentheticalSlotHint(filename = '') {
  const name = filename.split(/[\\/]/).pop() || '';
  const stem = name.replace(/\.s\d{1,3}$/i, '');
  const match = /\((\d{1,3})\)$/.exec(stem);
  if (!match) return null;
  const value = Number.parseInt(match[1], 10);
  return value >= 0 && value <= 999 ? value : null;
}

function snes9xSlot(filename = '') {
  const frzMatch = /\.(\d{1,3})\.frz$/i.exec(filename);
  if (frzMatch) return Number.parseInt(frzMatch[1], 10);
  const match = /\.(\d{3})$/i.exec(filename);
  return match ? Number.parseInt(match[1], 10) : null;
}

function uniqueZipName(name, used) {
  if (!used.includes(name)) return name;
  const dot = name.lastIndexOf('.');
  const stem = dot >= 0 ? name.slice(0, dot) : name;
  const ext = dot >= 0 ? name.slice(dot) : '';
  let index = 2;
  while (used.includes(`${stem}-${index}${ext}`)) index += 1;
  return `${stem}-${index}${ext}`;
}

function bytesToBase64(bytes) {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xFFFFFFFF;
  for (const b of bytes) {
    c = CRC_TABLE[(c ^ b) & 0xFF] ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function crc32Hex(bytes) {
  return crc32(bytes).toString(16).toUpperCase().padStart(8, '0');
}

function createStoredZip(files) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  const dosTime = 0;
  const dosDate = (46 << 9) | (1 << 5) | 1;

  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = file.bytes;
    const crc = crc32(data);
    const local = concatBytes(
      u32(0x04034B50), u16(20), u16(0x0800), u16(0), u16(dosTime), u16(dosDate),
      u32(crc), u32(data.length), u32(data.length), u16(name.length), u16(0), name,
    );
    localParts.push(local, data);

    const central = concatBytes(
      u32(0x02014B50), u16(20), u16(20), u16(0x0800), u16(0), u16(dosTime), u16(dosDate),
      u32(crc), u32(data.length), u32(data.length), u16(name.length), u16(0), u16(0),
      u16(0), u16(0), u32(0), u32(offset), name,
    );
    centralParts.push(central);
    offset += local.length + data.length;
  }

  const centralDir = concatBytes(...centralParts);
  const end = concatBytes(
    u32(0x06054B50), u16(0), u16(0), u16(files.length), u16(files.length),
    u32(centralDir.length), u32(offset), u16(0),
  );
  return concatBytes(...localParts, centralDir, end);
}

function u16(value) {
  return new Uint8Array([value & 0xFF, (value >>> 8) & 0xFF]);
}

function u32(value) {
  return new Uint8Array([
    value & 0xFF,
    (value >>> 8) & 0xFF,
    (value >>> 16) & 0xFF,
    (value >>> 24) & 0xFF,
  ]);
}

function concatBytes(...parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}
