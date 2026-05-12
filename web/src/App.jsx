import { useEffect, useMemo, useState } from 'react';
import { track } from '@vercel/analytics';
import { Analytics } from '@vercel/analytics/react';
import {
  IconBolt,
  IconCartArrow,
  IconCheck,
  IconChip,
  IconDoc,
  IconDownload,
  IconMoon,
  IconRefresh,
  IconSun,
  IconX,
} from './icons.jsx';
import { CatSunsetLogo, PixelCat, PixelCatLaptop, PixelSave } from './pixel-art.jsx';
import { makeDownload, runBatchConversion } from './converterClient.js';

const THEMES = ['purple', 'cyan', 'phosphor', 'amber', 'hotpink', 'ice', 'crt'];
const DETECTED_TYPES = new WeakMap();
const CONTACT_DISCORD = '.2by.';
const DONATE_URL = 'https://buymeacoffee.com/mrrexd';
const GITHUB_URL = 'https://github.com/oMrRexD/superretro16-converter-for-snes9x';
const APP_VERSION = __SAVESHIFT_VERSION__;
// Keep the native Windows file picker stable: a giant `accept` list with
// hundreds of slot extensions can make Explorer hang. Real blocking is done
// after selection/drop by extension + magic/header detection below.

const STRINGS = {
  pt: {
    documentTitle: 'SaveShift - Conversor de Save State',
    description: 'SaveShift converte save states entre SuperRetro16 e Snes9X com processamento local.',
    nav: ['CONTATO', 'DOAR', 'GITHUB'],
    brandSub: 'CONVERSOR SR16 SNES9X',
    title: ['CONVERTA SEUS', 'SAVE STATES', 'ENTRE EMULADORES'],
    lead: 'Conversor online de save states entre SuperRetro16 (antigo SuperGNES) e Snes9X. Converta um arquivo ou um lote inteiro com processamento local.',
    pills: ['OPEN-SOURCE', 'MÚLTIPLOS SAVES', '100% LOCAL'],
    offlineReady: 'OFFLINE PRONTO',
    heroFoot: 'Processamento local via Pyodide, com conversão, extração de SRAM e inspeção técnica.',
    catIdle: 'arraste seus saves\naqui, humano!',
    catReady: 'beleza! agora\nescolha a ação',
    catWorking: 'trabalhando...\nnão me distraia!',
    catDone: 'tcharaa!\nfica de boa',
    dropTitle: 'ARRASTE SEUS SAVE STATES AQUI',
    dropSub: 'ou clique para selecionar um ou vários arquivos',
    dropFormats: '.s00-.s999  .000-.999  .00.frz',
    privacy: '',
    loaded: 'ARQUIVO CARREGADO',
    loadedMany: 'ARQUIVOS CARREGADOS',
    change: 'Trocar arquivos',
    addFiles: 'Adicionar saves',
    size: 'Tamanho',
    type: 'Tipo detectado',
    ready: 'PRONTO PARA PROCESSAR',
    actionsTitle: 'O QUE VOCÊ QUER FAZER?',
    outputTitle: 'CONVERTER PARA:',
    process: 'PROCESSAR SAVE',
    processMany: 'PROCESSAR LOTE',
    back: 'VOLTAR',
    processing: 'PROCESSANDO...',
    readyDone: 'PRONTO!',
    download: 'DOWNLOAD DO ARQUIVO',
    downloadZip: 'DOWNLOAD DO ZIP',
    again: 'PROCESSAR OUTRO ARQUIVO',
    done: 'CONCLUÍDO!',
    doneBatch: 'LOTE CONCLUÍDO!',
    conversionComplete: 'CONVERSÃO CONCLUÍDA!',
    extractComplete: 'SRAM EXTRAÍDA!',
    infoComplete: 'ANÁLISE COMPLETA!',
    errorTitle: 'ERRO!',
    failed: 'NÃO FOI POSSÍVEL PROCESSAR',
    success: 'Seu arquivo foi processado com sucesso!',
    successBatch: 'Seus arquivos foram processados com sucesso!',
    infoDone: 'Veja abaixo as informações técnicas do save.',
    tech: 'INFORMAÇÕES TÉCNICAS',
    preview: 'IMAGEM DO SAVE',
    how: 'COMO FUNCIONA?',
    steps: [
      ['Arraste e solte', ' um ou vários save states.'],
      ['Escolha a ação', ': converter, extrair SRAM ou analisar.'],
      ['Baixe o resultado', ' direto ou em ZIP quando houver lote.'],
    ],
    legal: 'Sem ROMs, emuladores ou arquivos proprietários inclusos.',
    noDetails: 'Nenhum detalhe técnico para mostrar.',
    credit: 'Desenvolvido por MrRexD',
    footer: 'Projeto independente, sem afiliação com Neutron Emulation ou com o time do Snes9X.',
    contactTitle: 'FALAR COMIGO',
    contactLead: 'Quer relatar um bug, mandar feedback ou trocar ideia sobre saves?',
    contactPlatform: 'Discord',
    contactCopy: 'COPIAR DISCORD',
    contactCopied: 'COPIADO!',
    contactClose: 'FECHAR',
    donateTitle: 'Consegui te ajudar?',
    donateText: 'Se o SaveShift foi útil pra você, considere me apoiar com um cafezinho!',
    donateButton: 'APOIAR COM UM CAFÉ',
    techSummary: 'chunks, seções e avisos do arquivo',
    resultReady: 'STATUS:',
    sourceSave: 'SAVE ORIGINAL',
    outputSave: 'SAVE GERADO',
    resultMeta: 'METADADOS',
    noPreview: 'SEM IMAGEM DO SAVE',
    unsupported: 'Arquivos .srm/.sav não são entrada do conversor. Use save states SR16 ou Snes9X.',
    undetected: 'Não consegui detectar nenhum save state SR16 ou Snes9X válido nesses arquivos.',
    rejected: 'arquivo(s) ignorado(s): formato não detectado ou não suportado.',
    mixed: 'Lote misto',
    unknown: 'Desconhecido',
    saveStates: 'save states',
    moreItems: 'itens',
    mode: 'Alternar modo claro/escuro',
    theme: 'Trocar tema de cor',
    themeButton: 'TEMAS',
    menu: 'Abrir menu',
    closeMenu: 'Fechar menu',
    resultKeys: {
      file: 'Arquivo',
      type: 'Tipo',
      action: 'Ação',
      size: 'Tamanho',
      crc32: 'CRC32',
      output: 'Saída',
    },
    outputOptions: {
      snes9x: ['Snes9X (.000)', 'Formato padrão do Snes9X.'],
      explus: ['Snes9X EX+ (.00.frz)', 'Formato usado no Snes9X EX+.'],
    },
    progressLabels: {
      read: 'Lendo arquivo...',
      pythonReady: 'Conversor Python pronto.',
      loadingPyodide: 'Carregando Pyodide...',
      downloadingBundle: 'Baixando pacote do conversor...',
      preparingConverter: 'Preparando conversor local...',
      analyzing: 'Analisando arquivo...',
      converting: 'Convertendo...',
      preparingDownload: 'Preparando download...',
      finished: 'Finalizado.',
      unknownError: 'Falha desconhecida',
      batchLabel: 'Lote de save states',
      batchFailed: 'arquivo(s) falharam e ficaram fora do ZIP.',
      loadPackageFailed: 'Nao foi possivel carregar o pacote Python',
      corruptedBundle: 'O pacote local do conversor veio corrompido. Se voce usa gerenciador de downloads como IDM, desative a captura para este site e recarregue a pagina.',
      zipInfoName: 'saveshift-info.zip',
      zipSramName: 'sram-extraida.zip',
      zipConvertedName: 'saves-convertidos.zip',
    },
    actions: {
      'sr16-to-snes9x': ['CONVERSOR', 'SR16 → Snes9X / EX+', 'Converte save state do SuperRetro16 para slot state Snes9X.'],
      'sr16-to-snes9x-explus': ['CONVERSOR', 'SR16 → Snes9X EX+', 'Converte para save state Snes9X EX+ (.00.frz).'],
      'snes9x-to-sr16': ['CONVERSOR', 'Snes9X → SR16', 'Converte slot state Snes9X para SuperRetro16.'],
      'snes9x-to-snes9x-explus': ['RENOMEAR', 'Snes9X → Snes9X EX+', 'Renomeia o slot state Snes9X para o padrão Snes9X EX+ (.frz).'],
      'snes9x-explus-to-snes9x': ['RENOMEAR', 'Snes9X EX+ → Snes9X', 'Renomeia o slot state Snes9X EX+ para o padrão Snes9X (.000).'],
      extract: ['EXTRAIR SRAM', '', 'Extrai a SRAM de save states SR16, Snes9X ou Snes9X EX+.'],
      info: ['VER INFORMAÇÕES', '', 'Mostra chunks, seções, CRC32 e detalhes do arquivo.'],
    },
  },
  en: {
    documentTitle: 'SaveShift - Save State Converter',
    description: 'SaveShift converts save states between SuperRetro16 and Snes9X with local processing.',
    nav: ['CONTACT', 'DONATE', 'GITHUB'],
    brandSub: 'SR16 SNES9X CONVERTER',
    title: ['CONVERT YOUR', 'SAVE STATES', 'BETWEEN EMULATORS'],
    lead: 'Online save-state converter for SuperRetro16 (formerly SuperGNES) and Snes9X. Convert one file or an entire batch with local processing.',
    pills: ['OPEN-SOURCE', 'MULTIPLE SAVES', '100% LOCAL'],
    offlineReady: 'OFFLINE READY',
    heroFoot: 'Local processing through Pyodide, with conversion, SRAM extraction and technical inspection.',
    catIdle: 'drop your saves\nhere, human!',
    catReady: 'cool! now\npick an action',
    catWorking: 'working...\ndon\'t distract me!',
    catDone: 'ta-daa!\nyou\'re good',
    dropTitle: 'DROP YOUR SAVE STATES HERE',
    dropSub: 'or click to select one or many files',
    dropFormats: '.s00-.s999  .000-.999  .00.frz',
    privacy: '',
    loaded: 'FILE LOADED',
    loadedMany: 'FILES LOADED',
    change: 'Change files',
    addFiles: 'Add saves',
    size: 'Size',
    type: 'Detected type',
    ready: 'READY TO PROCESS',
    actionsTitle: 'WHAT DO YOU WANT TO DO?',
    outputTitle: 'CONVERT TO:',
    process: 'PROCESS SAVE',
    processMany: 'PROCESS BATCH',
    back: 'BACK',
    processing: 'PROCESSING...',
    readyDone: 'READY!',
    download: 'DOWNLOAD FILE',
    downloadZip: 'DOWNLOAD ZIP',
    again: 'PROCESS ANOTHER FILE',
    done: 'DONE!',
    doneBatch: 'BATCH DONE!',
    conversionComplete: 'CONVERSION COMPLETE!',
    extractComplete: 'SRAM EXTRACTED!',
    infoComplete: 'ANALYSIS COMPLETE!',
    errorTitle: 'ERROR!',
    failed: 'COULD NOT PROCESS',
    success: 'Your file was processed successfully!',
    successBatch: 'Your files were processed successfully!',
    infoDone: 'Technical save information is listed below.',
    tech: 'TECHNICAL INFO',
    preview: 'SAVE IMAGE',
    how: 'HOW IT WORKS?',
    steps: [
      ['Drag and drop', ' one or many save states.'],
      ['Pick an action', ': convert, extract SRAM or inspect.'],
      ['Download the result', ' directly or as ZIP for batches.'],
    ],
    legal: 'No ROMs, emulators or proprietary files are included.',
    noDetails: 'No technical details to show.',
    credit: 'Developed by MrRexD',
    footer: 'Independent project, not affiliated with Neutron Emulation or the Snes9X team.',
    contactTitle: 'CONTACT',
    contactLead: 'Want to report a bug, send feedback, or talk save states?',
    contactPlatform: 'Discord',
    contactCopy: 'COPY DISCORD',
    contactCopied: 'COPIED!',
    contactClose: 'CLOSE',
    donateTitle: 'Did this help?',
    donateText: 'If SaveShift was useful to you, consider supporting me with a coffee!',
    donateButton: 'BUY ME A COFFEE',
    techSummary: 'chunks, sections and file warnings',
    resultReady: 'STATUS:',
    sourceSave: 'SOURCE SAVE',
    outputSave: 'GENERATED SAVE',
    resultMeta: 'METADATA',
    noPreview: 'NO SAVE IMAGE',
    unsupported: '.srm/.sav files are not converter inputs. Use SR16 or Snes9X save states.',
    undetected: 'No valid SR16 or Snes9X save state could be detected in those files.',
    rejected: 'file(s) ignored: format not detected or not supported.',
    mixed: 'Mixed batch',
    unknown: 'Unknown',
    saveStates: 'save states',
    moreItems: 'items',
    mode: 'Toggle light/dark mode',
    theme: 'Change color theme',
    themeButton: 'THEME',
    menu: 'Open menu',
    closeMenu: 'Close menu',
    resultKeys: {
      file: 'File',
      type: 'Type',
      action: 'Action',
      size: 'Size',
      crc32: 'CRC32',
      output: 'Output',
    },
    outputOptions: {
      snes9x: ['Snes9X (.000)', 'Standard Snes9X format.'],
      explus: ['Snes9X EX+ (.00.frz)', 'Format used by Snes9X EX+.'],
    },
    progressLabels: {
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
      loadPackageFailed: 'Could not load the Python package',
      corruptedBundle: 'The local converter package is corrupted. If you use a download manager such as IDM, disable capture for this site and reload the page.',
      zipInfoName: 'saveshift-info.zip',
      zipSramName: 'extracted-sram.zip',
      zipConvertedName: 'converted-saves.zip',
    },
    actions: {
      'sr16-to-snes9x': ['CONVERT', 'SR16 → Snes9X / EX+', 'Convert a SuperRetro16 save state to a Snes9X slot state.'],
      'sr16-to-snes9x-explus': ['CONVERT', 'SR16 → Snes9X EX+', 'Convert to a Snes9X EX+ save state (.00.frz).'],
      'snes9x-to-sr16': ['CONVERT', 'Snes9X → SR16', 'Convert a Snes9X slot state to SuperRetro16.'],
      'snes9x-to-snes9x-explus': ['RENAME', 'Snes9X → Snes9X EX+', 'Rename a Snes9X slot state to the Snes9X EX+ (.frz) naming style.'],
      'snes9x-explus-to-snes9x': ['RENAME', 'Snes9X EX+ → Snes9X', 'Rename a Snes9X EX+ slot state to the Snes9X (.000) naming style.'],
      extract: ['EXTRACT SRAM', '', 'Extract SRAM from SR16, Snes9X or Snes9X EX+ save states.'],
      info: ['VIEW INFO', '', 'Show chunks, sections, CRC32 and file details.'],
    },
  },
};

const ACTIONS = [
  { id: 'sr16-to-snes9x', icon: <IconCartArrow dir="right" /> },
  { id: 'snes9x-to-sr16', icon: <IconCartArrow dir="left" /> },
  { id: 'snes9x-to-snes9x-explus', icon: <IconCartArrow dir="right" /> },
  { id: 'snes9x-explus-to-snes9x', icon: <IconCartArrow dir="left" /> },
  { id: 'extract', icon: <IconChip size={48} /> },
  { id: 'info', icon: <IconDoc size={48} /> },
];

function quickType(file) {
  const detected = file ? DETECTED_TYPES.get(file) : null;
  if (detected) return detected;
  const lower = (file?.name || '').toLowerCase();
  if (/\.(srm|sav)$/.test(lower)) return 'unsupported';
  if (/\.(s\d{1,3})$/.test(lower)) return 'sr16';
  if (/\.[0-9]{3}$/.test(lower)) return 'snes9x';
  if (/\.[0-9]{1,3}\.frz$/.test(lower)) return 'snes9x-explus';
  return 'unknown';
}

async function detectFileType(file) {
  const typeFromName = quickType(file);
  if (typeFromName !== 'unknown') return typeFromName;

  const head = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  if (startsWithAscii(head, '@sgnes@')) return 'sr16';
  if (startsWithAscii(head, '#!s9xsnp:')) return 'snes9x';

  if (head[0] === 0x1f && head[1] === 0x8b && await gzipLooksLikeSnes9x(file)) {
    return 'snes9x';
  }
  return 'unknown';
}

function startsWithAscii(bytes, text) {
  if (bytes.length < text.length) return false;
  for (let index = 0; index < text.length; index += 1) {
    if (bytes[index] !== text.charCodeAt(index)) return false;
  }
  return true;
}

async function gzipLooksLikeSnes9x(file) {
  if (typeof DecompressionStream === 'undefined') return false;
  try {
    const reader = file.stream().pipeThrough(new DecompressionStream('gzip')).getReader();
    const chunks = [];
    let total = 0;
    while (total < 16) {
      const { value, done } = await reader.read();
      if (done) break;
      const slice = value.subarray(0, Math.min(value.length, 16 - total));
      chunks.push(slice);
      total += slice.length;
    }
    try {
      await reader.cancel();
    } catch (_error) {
      // Best-effort stream cleanup only.
    }
    const out = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      out.set(chunk, offset);
      offset += chunk.length;
    }
    return startsWithAscii(out, '#!s9xsnp:');
  } catch (_error) {
    return false;
  }
}

function batchType(files) {
  if (!files.length) return 'unknown';
  const types = files.map(quickType);
  const supported = types.filter((type) => type !== 'unsupported');
  if (!supported.length) return 'unsupported';
  if (supported.every((type) => type === supported[0])) return supported[0];
  return 'mixed';
}

function allowedActions(type) {
  if (type === 'sr16') return ['sr16-to-snes9x', 'extract', 'info'];
  if (type === 'snes9x') return ['snes9x-to-sr16', 'snes9x-to-snes9x-explus', 'extract', 'info'];
  if (type === 'snes9x-explus') return ['snes9x-explus-to-snes9x', 'snes9x-to-sr16', 'extract', 'info'];
  if (type === 'mixed') return ['info'];
  return ['info'];
}

function formatBytes(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function typeLabel(type, t) {
  if (type === 'sr16') return 'SuperRetro16';
  if (type === 'snes9x') return 'Snes9X';
  if (type === 'snes9x-explus') return 'Snes9X EX+';
  if (type === 'mixed') return t.mixed;
  return t.unknown;
}

function totalSize(files) {
  return files.reduce((sum, file) => sum + file.size, 0);
}

function storedTheme() {
  try {
    const saved = localStorage.getItem('saveshift-theme');
    return THEMES.includes(saved) ? saved : 'purple';
  } catch (_error) {
    return 'purple';
  }
}

function storedLang() {
  try {
    const saved = localStorage.getItem('saveshift-lang');
    if (saved && STRINGS[saved]) return saved;
  } catch (_error) {
    // Language persistence is optional.
  }
  let preferred = 'en';
  try {
    preferred = (navigator.languages?.[0] || navigator.language || 'en').toLowerCase();
  } catch (_error) {
    preferred = 'en';
  }
  return preferred.startsWith('pt') ? 'pt' : 'en';
}

function defaultConvertAction(type) {
  if (type === 'sr16') return 'sr16-to-snes9x';
  if (type === 'snes9x') return 'snes9x-to-sr16';
  if (type === 'snes9x-explus') return 'snes9x-explus-to-snes9x';
  return 'info';
}

function scrollToSection(id) {
  window.requestAnimationFrame(() => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function openExternal(url) {
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
}

function trackUsage(eventName, payload = {}) {
  try {
    track(eventName, payload);
  } catch (_error) {
    // Analytics must never affect conversion.
  }
}

export default function App() {
  const [lang, setLang] = useState(storedLang);
  const [mode, setMode] = useState('dark');
  const [theme, setTheme] = useState(storedTheme);
  const [stage, setStage] = useState('idle');
  const [files, setFiles] = useState([]);
  const [fileWarning, setFileWarning] = useState('');
  const [action, setAction] = useState('sr16-to-snes9x');
  const [sr16Output, setSr16Output] = useState('snes9x');
  const [progress, setProgress] = useState({ label: '', percent: 0 });
  const [result, setResult] = useState(null);
  const [download, setDownload] = useState(null);
  const [contactOpen, setContactOpen] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const t = STRINGS[lang];
  const fileType = batchType(files);

  useEffect(() => {
    document.documentElement.setAttribute('data-mode', mode);
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('saveshift-theme', theme);
    } catch (_error) {
      // Theme persistence is optional.
    }
  }, [mode, theme]);

  useEffect(() => {
    document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en';
    document.title = t.documentTitle;
    const meta = document.querySelector('meta[name="description"]');
    if (meta) {
      meta.setAttribute('content', t.description);
    }
  }, [lang, t]);

  useEffect(() => {
    if (!files.length) return;
    const nextAllowed = allowedActions(fileType);
    if (!nextAllowed.includes(action)) {
      setAction(nextAllowed[0]);
    }
  }, [files, fileType, action]);

  useEffect(() => () => {
    if (download?.url) URL.revokeObjectURL(download.url);
  }, [download]);

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return undefined;
    let cancelled = false;
    const markOfflineReady = () => {
      if (!cancelled) setOfflineReady(true);
    };
    navigator.serviceWorker.ready.then(markOfflineReady).catch(() => {});
    navigator.serviceWorker.addEventListener('controllerchange', markOfflineReady);
    return () => {
      cancelled = true;
      navigator.serviceWorker.removeEventListener('controllerchange', markOfflineReady);
    };
  }, []);

  const currentActions = useMemo(
    () => ACTIONS.filter((item) => allowedActions(fileType).includes(item.id)),
    [fileType],
  );

  const catSays = stage === 'idle' ? t.catIdle
    : stage === 'has-file' ? t.catReady
      : stage === 'processing' ? t.catWorking
        : t.catDone;

  function changeLang(nextLang) {
    setLang(nextLang);
    try {
      localStorage.setItem('saveshift-lang', nextLang);
    } catch (_error) {
      // Language persistence is optional.
    }
  }

  async function setPickedFiles(fileList, append = false) {
    const incoming = Array.from(fileList || []);
    const checked = await Promise.all(
      incoming.map(async (file) => ({ file, type: await detectFileType(file) })),
    );
    const supported = [];
    const rejected = [];
    for (const item of checked) {
      if (item.type === 'sr16' || item.type === 'snes9x' || item.type === 'snes9x-explus') {
        DETECTED_TYPES.set(item.file, item.type);
        supported.push(item.file);
      } else {
        rejected.push(item.file);
      }
    }

    if (!supported.length) {
      setResult({
        ok: false,
        error: rejected.some((file) => /\.(srm|sav)$/i.test(file.name)) ? t.unsupported : t.undetected,
        info: { type: 'unsupported', size: 0 },
      });
      setFileWarning('');
      setStage('done');
      return;
    }
    if (download?.url) URL.revokeObjectURL(download.url);
    setDownload(null);
    setResult(null);
    setFileWarning(rejected.length ? `${rejected.length} ${t.rejected}` : '');
    setFiles((prev) => (append ? [...prev, ...supported] : supported));
    setStage('has-file');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function clearFiles() {
    if (download?.url) URL.revokeObjectURL(download.url);
    setDownload(null);
    setResult(null);
    setFiles([]);
    setFileWarning('');
    setAction('sr16-to-snes9x');
    setSr16Output('snes9x');
    setStage('idle');
  }

  function handleNav(section) {
    if (section === 'contact') {
      setContactOpen(true);
      return;
    }
    if (section === 'donate') {
      openExternal(DONATE_URL);
      return;
    }
    if (section === 'github') {
      openExternal(GITHUB_URL);
    }
  }

  async function processFiles() {
    if (!files.length) return;
    setStage('processing');
    setProgress({ label: t.progressLabels.read, percent: 0 });
    setResult(null);
    setDownload(null);
    try {
      const effectiveAction = (
        action === 'sr16-to-snes9x' && sr16Output === 'explus'
          ? 'sr16-to-snes9x-explus'
          : action
      );
      const response = await runBatchConversion(effectiveAction, files, setProgress, t.progressLabels);
      setResult({ ...response, actionId: effectiveAction });
      if (response.ok && response.dataBase64) {
        setDownload(makeDownload(response));
        trackUsage('Save processed', {
          action: effectiveAction,
          sourceType: fileType || 'unknown',
          batch: files.length > 1,
          fileCount: files.length,
        });
      }
    } catch (error) {
      setResult({
        ok: false,
        error: error?.message || String(error),
        info: { type: fileType, size: totalSize(files) },
      });
    } finally {
      setProgress({ label: t.progressLabels.finished, percent: 100 });
      setStage('done');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  return (
    <div className="page">
      <Header
        t={t}
        lang={lang}
        setLang={changeLang}
        mode={mode}
        setMode={setMode}
        theme={theme}
        setTheme={setTheme}
        goHome={() => setStage(files.length ? 'has-file' : 'idle')}
        onNav={handleNav}
      />
      <ContactModal t={t} open={contactOpen} onClose={() => setContactOpen(false)} />

      {(stage === 'idle' || stage === 'has-file') && (
        <Hero
          t={t}
          files={files}
          fileType={fileType}
          fileWarning={fileWarning}
          catSays={catSays}
          offlineReady={offlineReady}
          onFiles={setPickedFiles}
          onClear={clearFiles}
        />
      )}

      {stage === 'has-file' && (
        <ActionsSection
          t={t}
          action={action}
          setAction={setAction}
          sr16Output={sr16Output}
          setSr16Output={setSr16Output}
          actions={currentActions}
          fileType={fileType}
          files={files}
          onBack={clearFiles}
          onProcess={processFiles}
        />
      )}

      {stage === 'processing' && (
        <ProcessingSection t={t} files={files} progress={progress} />
      )}

      {stage === 'done' && (
        <DoneSection
          t={t}
          action={action}
          files={files}
          result={result}
          download={download}
          onAgain={clearFiles}
        />
      )}

      {stage === 'idle' && <HowItWorks t={t} />}
      <Footer t={t} />
      <Analytics mode="production" />
    </div>
  );
}

function Header({
  t,
  lang,
  setLang,
  mode,
  setMode,
  theme,
  setTheme,
  goHome,
  onNav,
}) {
  const navTargets = ['contact', 'donate', 'github'];
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (!mobileMenuOpen) return undefined;
    function closeOnEscape(event) {
      if (event.key === 'Escape') setMobileMenuOpen(false);
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [mobileMenuOpen]);

  function handleMobileNav(target) {
    setMobileMenuOpen(false);
    onNav(target);
  }

  return (
    <header className="nav">
      <button className="brand" onClick={goHome}>
        <div className="brand-mark"><CatSunsetLogo /></div>
        <span>
          <span className="brand-name">SaveShift</span>
          <span className="brand-sub">{t.brandSub}</span>
        </span>
      </button>
      <button
        className="mobile-menu-button"
        type="button"
        onClick={() => setMobileMenuOpen((open) => !open)}
        aria-label={mobileMenuOpen ? t.closeMenu : t.menu}
        aria-expanded={mobileMenuOpen}
      >
        <span />
        <span />
        <span />
      </button>
      <nav className="nav-links">
        {t.nav.map((item, index) => (
          <button key={item} type="button" onClick={() => onNav(navTargets[index])}>
            {item}
          </button>
        ))}
      </nav>
      <div className="nav-tools">
        <div className={`theme-picker ${themeMenuOpen ? 'open' : ''}`}>
          <button
            className="theme-menu-toggle"
            type="button"
            onClick={() => setThemeMenuOpen((open) => !open)}
            aria-label={t.theme}
            aria-expanded={themeMenuOpen}
          >
            <span className="theme-current" data-swatch={theme} aria-hidden="true" />
            <span>{t.themeButton}</span>
          </button>
          <div className="theme-toggle" role="group" aria-label={t.theme} title={t.theme}>
            {THEMES.map((item) => (
              <button
                key={item}
                type="button"
                className={`theme-swatch ${item === theme ? 'on' : ''}`}
                data-swatch={item}
                onClick={() => {
                  setTheme(item);
                  setThemeMenuOpen(false);
                }}
                aria-label={`${t.theme}: ${item}`}
                aria-pressed={item === theme}
              />
            ))}
          </div>
        </div>
        <button className="lang-toggle" onClick={() => setLang(lang === 'pt' ? 'en' : 'pt')}>
          <span className={lang === 'pt' ? 'on' : ''}>PT</span><span>/</span><span className={lang === 'en' ? 'on' : ''}>EN</span>
        </button>
        <button className="icon-btn" onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')} aria-label={t.mode} title={t.mode}>
          {mode === 'dark' ? <IconMoon /> : <IconSun />}
        </button>
      </div>
      <div className={`mobile-menu ${mobileMenuOpen ? 'open' : ''}`}>
        <div className="mobile-menu-nav">
          {t.nav.map((item, index) => (
            <button key={item} type="button" onClick={() => handleMobileNav(navTargets[index])}>
              {item}
            </button>
          ))}
        </div>
        <div className="mobile-menu-controls">
          <button type="button" className="mobile-lang-toggle" onClick={() => setLang(lang === 'pt' ? 'en' : 'pt')}>
            <span className={lang === 'pt' ? 'on' : ''}>PT</span><span>/</span><span className={lang === 'en' ? 'on' : ''}>EN</span>
          </button>
          <button type="button" className="mobile-mode-toggle" onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')} aria-label={t.mode}>
            {mode === 'dark' ? <IconMoon /> : <IconSun />}
          </button>
        </div>
        <div className="mobile-theme-row" role="group" aria-label={t.theme}>
          <span>{t.themeButton}</span>
          <div>
            {THEMES.map((item) => (
              <button
                key={item}
                type="button"
                className={`theme-swatch ${item === theme ? 'on' : ''}`}
                data-swatch={item}
                onClick={() => setTheme(item)}
                aria-label={`${t.theme}: ${item}`}
                aria-pressed={item === theme}
              />
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}

function ContactModal({ t, open, onClose }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) {
      setCopied(false);
      return undefined;
    }
    function closeOnEscape(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [open, onClose]);

  async function copyDiscord() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(CONTACT_DISCORD);
      } else {
        const helper = document.createElement('textarea');
        helper.value = CONTACT_DISCORD;
        helper.setAttribute('readonly', '');
        helper.style.position = 'fixed';
        helper.style.opacity = '0';
        document.body.appendChild(helper);
        helper.select();
        document.execCommand('copy');
        document.body.removeChild(helper);
      }
      setCopied(true);
    } catch (_error) {
      setCopied(false);
    }
  }

  if (!open) return null;

  return (
    <div className="contact-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="contact-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="contact-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="contact-close" type="button" onClick={onClose} aria-label={t.contactClose}>
          <IconX size={18} />
        </button>
        <div className="contact-emblem" aria-hidden="true">
          <span>DM</span>
        </div>
        <h2 id="contact-title">{t.contactTitle}</h2>
        <p>{t.contactLead}</p>
        <div className="discord-tag">
          <span>{t.contactPlatform}</span>
          <strong>{CONTACT_DISCORD}</strong>
        </div>
        <div className="cta-row compact-row">
          <button className="btn primary" type="button" onClick={copyDiscord}>
            {copied ? t.contactCopied : t.contactCopy}
          </button>
          <button className="btn secondary" type="button" onClick={onClose}>
            {t.contactClose}
          </button>
        </div>
      </section>
    </div>
  );
}

function Hero({ t, files, fileType, fileWarning, catSays, offlineReady, onFiles, onClear }) {
  return (
    <section className="hero" id="converter">
      <div className="hero-copy">
        <h1>
          {t.title[0]}<br />
          {t.title[1]}<br />
          <span>{t.title[2]}</span>
        </h1>
        <p>{t.lead}</p>
        <div className="pills">
          {t.pills.map((pill) => <span key={pill}>{pill}</span>)}
          {offlineReady && <span>{t.offlineReady}</span>}
        </div>
        <p className="hero-foot">{t.heroFoot}</p>
        <div className="mascot-row">
          <PixelCat />
          <div className="bubble">
            {catSays.split('\n').map((line) => <span key={line}>{line}<br /></span>)}
          </div>
        </div>
      </div>
      <Dropzone t={t} files={files} fileType={fileType} fileWarning={fileWarning} onFiles={onFiles} onClear={onClear} />
    </section>
  );
}

function Dropzone({ t, files, fileType, fileWarning, onFiles, onClear }) {
  const [dragging, setDragging] = useState(false);
  const hasFiles = files.length > 0;

  if (hasFiles) {
    return (
      <div
        className={`dropzone has-file ${dragging ? 'dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          onFiles(event.dataTransfer.files, true);
        }}
      >
        <div className="file-card">
          <div className="file-icon"><PixelSave scale={4} /></div>
          <div>
            <div className="file-loaded">{files.length === 1 ? t.loaded : t.loadedMany}</div>
            <div className="file-name">
              {files.length === 1 ? files[0].name : `${files.length} ${t.saveStates}`}
            </div>
            <div className="file-meta">
              <span><b>{t.size}:</b> {formatBytes(totalSize(files))}</span>
              <span><b>{t.type}:</b> <em>{typeLabel(fileType, t)}</em></span>
            </div>
            <div className="file-list">
              {files.slice(0, 6).map((file, index) => (
                <code key={`${file.name}-${file.size}-${index}`}>{file.name}</code>
              ))}
              {files.length > 6 && <code>+{files.length - 6}</code>}
            </div>
            <div className="file-actions">
              <label className="link-btn">
                + {t.addFiles}
                <input type="file" multiple onChange={(event) => onFiles(event.target.files, true)} />
              </label>
              <button className="link-btn" onClick={onClear}>↺ {t.change}</button>
            </div>
            {fileWarning && <p className="file-warning">{fileWarning}</p>}
          </div>
        </div>
        <div className="ready-tag"><IconCheck size={14} /> {t.ready}</div>
      </div>
    );
  }

  return (
    <label
      className={`dropzone ${dragging ? 'dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        onFiles(event.dataTransfer.files);
      }}
    >
      <input
        type="file"
        multiple
        onChange={(event) => onFiles(event.target.files)}
      />
      <PixelSave scale={5} />
      <strong>{t.dropTitle}</strong>
      <span>{t.dropSub}</span>
      <code>{t.dropFormats}</code>
      {t.privacy && <small>{t.privacy}</small>}
    </label>
  );
}

function ActionsSection({
  t,
  action,
  setAction,
  sr16Output,
  setSr16Output,
  actions,
  fileType,
  files,
  onBack,
  onProcess,
}) {
  const showOutputOptions = action === 'sr16-to-snes9x' && fileType === 'sr16';

  return (
    <section className="section" id="actions">
      <h2>{t.actionsTitle}</h2>
      <div className="actions-grid">
        {actions.map((item) => {
          const [label, sub, desc] = t.actions[item.id];
          return (
            <div
              key={item.id}
              className={`action-card ${action === item.id ? 'active' : ''}`}
            >
              <button className="action-select" type="button" onClick={() => setAction(item.id)}>
                <span className="action-icon">{item.icon}</span>
                <strong>{label}</strong>
                {sub && <em>{sub}</em>}
                <span>{desc}</span>
                <i />
              </button>
            </div>
          );
        })}
      </div>
      {showOutputOptions && (
        <div className="output-format-panel">
          <div className="output-title">{t.outputTitle}</div>
          <div className="output-options">
            {Object.entries(t.outputOptions).map(([id, [optionLabel, optionDesc]]) => (
              <button
                key={id}
                type="button"
                className={`output-option ${sr16Output === id ? 'selected' : ''}`}
                onClick={() => {
                  setAction('sr16-to-snes9x');
                  setSr16Output(id);
                }}
              >
                <span className="option-radio" />
                <span>
                  <strong>{optionLabel}</strong>
                  <small>{optionDesc}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="cta-row">
        <button className="btn secondary" onClick={onBack}>← {t.back}</button>
        <button className="btn primary" onClick={onProcess}>
          {files.length > 1 ? t.processMany : t.process} <IconBolt />
        </button>
      </div>
    </section>
  );
}

function ProcessingSection({ t, files, progress }) {
  return (
    <section className="center-stage">
      <div className="panel processing-card">
        <h2>{t.processing}</h2>
        <PixelCatLaptop />
        <p>{progress.label || t.processing}</p>
        <code>{files.length === 1 ? files[0]?.name : `${files.length} ${t.saveStates}`}</code>
        <div className="progress"><span style={{ width: `${progress.percent || 0}%` }} /></div>
        <div className="progress-label">{Math.round(progress.percent || 0)}%</div>
      </div>
    </section>
  );
}

function DoneSection({ t, action, files, result, download, onAgain }) {
  const ok = result?.ok;
  const info = result?.info || {};
  const resultAction = result?.actionId || action;
  const isBatch = result?.batch || files.length > 1;
  const summaryInfo = ok && resultAction !== 'info'
    ? (result?.outputInfo || {
        type: info.type,
        label: info.label,
        size: result?.size,
      })
    : info;
  const sourceName = isBatch ? `${files.length} ${t.saveStates}` : files[0]?.name;
  const outputName = result?.outputName || (ok ? sourceName : '');
  const typeText = summaryInfo.label || typeLabel(summaryInfo.type, t);
  const actionText = t.actions[resultAction]?.[1] || t.actions[resultAction]?.[0];
  const sizeText = formatBytes(summaryInfo.size || result?.size || totalSize(files));
  const isInfoAction = resultAction === 'info';
  const isExtractAction = resultAction === 'extract';
  const hasGeneratedOutput = ok && !isInfoAction && Boolean(result?.outputName);
  const statusTitle = ok ? t.readyDone : t.errorTitle;
  const showTechPanel = isInfoAction || isBatch;
  const resultHeadline = ok
    ? (isBatch ? t.doneBatch : (isInfoAction ? t.infoComplete : (isExtractAction ? t.extractComplete : t.conversionComplete)))
    : t.failed;
  const rawStatusMessage = ok
    ? (isBatch ? t.successBatch : (isInfoAction ? t.infoDone : t.success))
    : result?.error;
  const statusMessage = [statusTitle, t.resultReady, resultHeadline].includes(rawStatusMessage)
    ? ''
    : rawStatusMessage;
  const metaRows = [
    [t.resultKeys.type, typeText],
    [t.resultKeys.action, actionText],
    [t.resultKeys.size, sizeText],
    [t.resultKeys.crc32, summaryInfo.crc32],
  ].filter(([, value]) => value);
  const itemRows = info.files || info.sections || info.chunks || [];
  const preview = !isBatch ? info.preview : null;

  return (
    <section className="section">
      <div className={`done-grid ${showTechPanel ? '' : 'done-grid-single'}`}>
        <div className="panel result-panel">
          <div className="panel-title">{statusTitle}</div>
          <div className="panel-body">
            <div className={`result-hero-card ${ok ? 'ok' : 'bad'}`}>
              <div className="result-emblem">{ok ? <IconCheck size={28} /> : <IconX size={28} />}</div>
              <div className="result-title-block">
                <span>{t.resultReady}</span>
                <h2>{resultHeadline}</h2>
                {statusMessage && <p>{statusMessage}</p>}
              </div>
            </div>

            <div className="result-body">
              <div className="kv-list">
                <div className="kv"><span>{t.sourceSave}</span><b>{sourceName}</b></div>
                {hasGeneratedOutput && <div className="kv"><span>{t.outputSave}</span><b>{outputName}</b></div>}
                {metaRows.map(([key, value]) => (
                  <div className="kv" key={key}><span>{key}</span><b>{value}</b></div>
                ))}
              </div>
              <figure className={`result-mascot ${preview?.dataUrl ? 'has-preview' : ''}`}>
                {preview?.dataUrl ? (
                  <img
                    src={preview.dataUrl}
                    width={preview.width}
                    height={preview.height}
                    alt={`${t.preview}: ${preview.source}`}
                  />
                ) : (
                  <PixelSave scale={4} />
                )}
                {!preview?.dataUrl && <figcaption>{t.noPreview}</figcaption>}
              </figure>
            </div>

            <div className="actions-stack">
              {ok && download?.url && (
                <a className="btn good" href={download.url} download={result.outputName}>
                  <IconDownload /> {isBatch ? t.downloadZip : t.download}
                </a>
              )}
              <button className="btn secondary wide" onClick={onAgain}><IconRefresh /> {t.again}</button>
            </div>
            {ok && <DonateCard t={t} />}
          </div>
        </div>

        {showTechPanel && (
          <div className="panel pixelcut tech-panel" id="technical-info-panel">
            <div className="panel-title">{t.tech}</div>
            <div className="panel-body tech-list">
              <div className="kv-list compact">
                {itemRows.slice(0, 18).map((item, index) => (
                  <div className="kv" key={`${item.code}-${index}`}>
                    <span>{item.code}</span>
                    <b>{formatBytes(item.size)}</b>
                  </div>
                ))}
                {itemRows.length === 0 && <p className="muted">{t.noDetails}</p>}
                {itemRows.length > 18 && <p className="muted">+{itemRows.length - 18} {t.moreItems}</p>}
                {info.warnings?.map((warning) => <p className="muted" key={warning}>{warning}</p>)}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function DonateCard({ t }) {
  return (
    <aside className="donate-card">
      <div className="donate-logo" aria-hidden="true">
        <CoffeeIcon />
      </div>
      <div className="donate-copy">
        <strong>{t.donateTitle}</strong>
        <p>{t.donateText}</p>
      </div>
      <a className="coffee-btn" href={DONATE_URL} target="_blank" rel="noreferrer" aria-label={t.donateButton}>
        {t.donateButton}
      </a>
    </aside>
  );
}

function CoffeeIcon() {
  return (
    <svg viewBox="0 0 100 120" aria-hidden="true">
      <path
        d="M30 45 L35 105 C36 112, 64 112, 65 105 L70 45"
        stroke="currentColor"
        strokeWidth="6"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M25 45 C25 38, 75 38, 75 45 C75 50, 25 50, 25 45 Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M38 38 C38 30, 62 30, 62 38"
        fill="none"
        stroke="currentColor"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path
        d="M75 45 C88 45, 88 75, 70 75"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <circle cx="50" cy="78" r="8" stroke="currentColor" strokeWidth="5" fill="none" />
    </svg>
  );
}

function HowItWorks({ t }) {
  return (
    <section className="section" id="how">
      <h2>{t.how}</h2>
      <div className="how-grid">
        {t.steps.map(([strong, rest], index) => (
          <div className="how-step" key={strong}>
            <b>{index + 1}</b>
            <span><strong>{strong}</strong>{rest}</span>
          </div>
        ))}
      </div>
      <p className="privacy-line">{t.legal}</p>
    </section>
  );
}

function Footer({ t }) {
  return (
    <footer>
      <span className="footer-brandline">
        <span>SaveShift v{APP_VERSION}</span>
        <span aria-hidden="true">•</span>
        <span>{t.credit}</span>
      </span>
      <span className="footer-note">{t.footer}</span>
    </footer>
  );
}
