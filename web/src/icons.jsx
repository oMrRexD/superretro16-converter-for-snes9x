const stroke = {
  stroke: 'currentColor',
  strokeWidth: 1.7,
  fill: 'none',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

export function IconCartArrow({ size = 36, dir = 'right' }) {
  return (
    <svg width={size * 2.4} height={size} viewBox="0 0 96 36" {...stroke}>
      <g>
        <rect x="3" y="6" width="28" height="16" rx="2" />
        <rect x="6" y="9" width="9" height="8" />
        <line x1="18" y1="11" x2="28" y2="11" />
        <line x1="18" y1="14" x2="28" y2="14" />
        <line x1="18" y1="17" x2="25" y2="17" />
        <path d="M3 22 L3 26 L8 26 L10 24 L24 24 L26 26 L31 26 L31 22" />
      </g>
      {dir === 'right' ? (
        <g>
          <line x1="36" y1="16" x2="58" y2="16" strokeWidth="2.2" />
          <polyline points="52,11 58,16 52,21" strokeWidth="2.2" />
        </g>
      ) : (
        <g>
          <line x1="58" y1="16" x2="36" y2="16" strokeWidth="2.2" />
          <polyline points="42,11 36,16 42,21" strokeWidth="2.2" />
        </g>
      )}
      <g transform="translate(62 0)">
        <rect x="3" y="6" width="28" height="16" rx="2" />
        <rect x="6" y="9" width="9" height="8" />
        <line x1="18" y1="11" x2="28" y2="11" />
        <line x1="18" y1="14" x2="28" y2="14" />
        <line x1="18" y1="17" x2="25" y2="17" />
        <path d="M3 22 L3 26 L8 26 L10 24 L24 24 L26 26 L31 26 L31 22" />
      </g>
    </svg>
  );
}

export function IconChip({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" {...stroke}>
      <rect x="9" y="9" width="18" height="18" rx="1" />
      <rect x="13" y="13" width="10" height="10" rx="0.5" />
      {[12, 18, 24].map((p) => <line key={`t${p}`} x1={p} y1="3" x2={p} y2="9" />)}
      {[12, 18, 24].map((p) => <line key={`b${p}`} x1={p} y1="27" x2={p} y2="33" />)}
      {[12, 18, 24].map((p) => <line key={`l${p}`} x1="3" y1={p} x2="9" y2={p} />)}
      {[12, 18, 24].map((p) => <line key={`r${p}`} x1="27" y1={p} x2="33" y2={p} />)}
      <circle cx="11" cy="11" r="0.8" fill="currentColor" />
    </svg>
  );
}

export function IconDoc({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" {...stroke}>
      <path d="M9 4 L23 4 L29 10 L29 32 L9 32 Z" />
      <path d="M23 4 L23 10 L29 10" />
      <line x1="13" y1="16" x2="25" y2="16" />
      <line x1="13" y1="20" x2="25" y2="20" />
      <line x1="13" y1="24" x2="22" y2="24" />
      <circle cx="27" cy="27" r="4" />
      <line x1="30" y1="30" x2="33" y2="33" />
    </svg>
  );
}

export function IconCheck({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...stroke} strokeWidth="2.6">
      <polyline points="5,12 10,17 19,7" />
    </svg>
  );
}

export function IconX({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...stroke} strokeWidth="2.6">
      <line x1="7" y1="7" x2="17" y2="17" />
      <line x1="17" y1="7" x2="7" y2="17" />
    </svg>
  );
}

export function IconBolt({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
      <path d="M9 0 L2 9 L7 9 L7 16 L14 7 L9 7 Z" />
    </svg>
  );
}

export function IconDownload({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" {...stroke} strokeWidth="2">
      <line x1="8" y1="2" x2="8" y2="11" />
      <polyline points="4,7 8,11 12,7" />
      <line x1="2" y1="14" x2="14" y2="14" />
    </svg>
  );
}

export function IconRefresh({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" {...stroke} strokeWidth="1.6">
      <path d="M2 8 A6 6 0 0 1 13 5" />
      <polyline points="13,2 13,5 10,5" />
      <path d="M14 8 A6 6 0 0 1 3 11" />
      <polyline points="3,14 3,11 6,11" />
    </svg>
  );
}

export function IconLock({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" {...stroke}>
      <rect x="3" y="7" width="10" height="7" rx="1" />
      <path d="M5 7 V5 A3 3 0 0 1 11 5 V7" />
    </svg>
  );
}

export function IconMoon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
      <path d="M20 14.5 A8 8 0 1 1 9.5 4 A6 6 0 0 0 20 14.5 Z" />
    </svg>
  );
}

export function IconSun({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="2" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="2" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="22" y2="12" />
      <line x1="5" y1="5" x2="7" y2="7" />
      <line x1="17" y1="17" x2="19" y2="19" />
      <line x1="5" y1="19" x2="7" y2="17" />
      <line x1="17" y1="7" x2="19" y2="5" />
    </svg>
  );
}
