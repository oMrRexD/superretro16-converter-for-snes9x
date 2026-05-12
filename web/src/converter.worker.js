const PYODIDE_BASE = '/pyodide/';
const PYTHON_BUNDLE = 'save-converter-python.pybundle';
const PYTHON_BUNDLE_CACHE_KEY = 'saveshift-python-bundle-v2';

let pyodidePromise = null;

const DEFAULT_PROGRESS_LABELS = {
  pythonReady: 'Python converter ready.',
  loadingPyodide: 'Loading Pyodide...',
  downloadingBundle: 'Loading converter bundle...',
  preparingConverter: 'Preparing local converter...',
  analyzing: 'Inspecting file...',
  converting: 'Converting...',
  preparingDownload: 'Preparing download...',
  loadPackageFailed: 'Could not load the Python package',
  corruptedBundle: 'The local converter package is corrupted. If you use a download manager such as IDM, disable capture for this site and reload the page.',
};

function sendProgress(id, label, percent) {
  self.postMessage({ id, type: 'progress', progress: { label, percent } });
}

function labelsFrom(progressLabels) {
  return { ...DEFAULT_PROGRESS_LABELS, ...(progressLabels || {}) };
}

async function ensurePyodide(id, progressLabels) {
  const labels = labelsFrom(progressLabels);
  if (pyodidePromise) {
    sendProgress(id, labels.pythonReady, 68);
    return pyodidePromise;
  }

  pyodidePromise = (async () => {
    sendProgress(id, labels.loadingPyodide, 12);
    importScripts(`${PYODIDE_BASE}pyodide.js`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE });

    sendProgress(id, labels.downloadingBundle, 38);
    const response = await fetch(
      `/${PYTHON_BUNDLE}?v=${PYTHON_BUNDLE_CACHE_KEY}`,
      { cache: 'no-cache' },
    );
    if (!response.ok) {
      throw new Error(`${labels.loadPackageFailed} (${response.status})`);
    }
    const zipBytes = new Uint8Array(await response.arrayBuffer());
    if (
      zipBytes.length < 4 ||
      zipBytes[0] !== 0x50 ||
      zipBytes[1] !== 0x4B ||
      zipBytes[2] !== 0x03 ||
      zipBytes[3] !== 0x04
    ) {
      throw new Error(labels.corruptedBundle);
    }
    pyodide.FS.writeFile(`/tmp/${PYTHON_BUNDLE}`, zipBytes);

    sendProgress(id, labels.preparingConverter, 54);
    await pyodide.runPythonAsync(`
import os
import shutil
import sys
import zipfile

target = "/home/pyodide/save_converter"
if os.path.isdir(target):
    shutil.rmtree(target)
os.makedirs(target, exist_ok=True)
with zipfile.ZipFile("/tmp/save-converter-python.pybundle", "r") as zf:
    zf.extractall(target)
if target not in sys.path:
    sys.path.insert(0, target)
from web_bridge import dispatch_file
`);
    return pyodide;
  })();

  return pyodidePromise;
}

self.addEventListener('message', async (event) => {
  const msg = event.data || {};
  if (msg.type !== 'run') return;
  const { id, action, filename, bytes, progressLabels } = msg;
  const labels = labelsFrom(progressLabels);

  try {
    const pyodide = await ensurePyodide(id, labels);
    sendProgress(id, labels.analyzing, 72);
    const inputPath = `/tmp/saveshift_${id}.bin`;
    pyodide.FS.writeFile(inputPath, new Uint8Array(bytes));
    pyodide.globals.set('js_action', action);
    pyodide.globals.set('js_filename', filename);
    pyodide.globals.set('js_input_path', inputPath);

    sendProgress(id, labels.converting, 84);
    const resultJson = await pyodide.runPythonAsync(
      'dispatch_file(js_action, js_filename, js_input_path)'
    );
    try {
      pyodide.FS.unlink(inputPath);
    } catch (_err) {
      // Best-effort cleanup only.
    }
    sendProgress(id, labels.preparingDownload, 96);
    const result = JSON.parse(resultJson);
    self.postMessage({ id, type: 'result', result });
  } catch (error) {
    self.postMessage({
      id,
      type: 'error',
      error: error?.message || String(error),
    });
  }
});
