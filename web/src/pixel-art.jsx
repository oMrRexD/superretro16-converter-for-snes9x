import catUrl from '../assets/gatim.webp';
import catCodingUrl from '../assets/gato_programando.webp';

const SAVE_PATTERN = [
  '.##############.',
  '.#aaaaaaaaaaaa#.',
  '.#a##########a#.',
  '.#a#bbbbbbbb#a#.',
  '.#a#bbbbbbbb#a#.',
  '.#a#bbbbbbbb#a#.',
  '.#a##########a#.',
  '.#aaaaaaaaaaaa#.',
  '.#aaaaaaaaaaaa#.',
  '.#a##########a#.',
  '.#a#cccccccc#a#.',
  '.#a#c######c#a#.',
  '.#a#c######c#a#.',
  '.#a#c######c#a#.',
  '.#a##########a#.',
  '.##############.',
];

const CART_PATTERN = [
  '..############..',
  '..#aaaaaaaaaa#..',
  '..#abbbbbbbba#..',
  '..#abccccccba#..',
  '..#abcdddccba#..',
  '..#abcdddccba#..',
  '..#abccccccba#..',
  '..#abbbbbbbba#..',
  '..#aaaaaaaaaa#..',
  '################',
  '#aaaaaaaaaaaaaa#',
  '################',
];

function PixelGrid({ pattern, palette, scale = 4 }) {
  const cols = pattern[0].length;
  return (
    <div
      style={{
        width: cols * scale,
        height: pattern.length * scale,
        display: 'grid',
        gridTemplateColumns: `repeat(${cols}, ${scale}px)`,
        gridTemplateRows: `repeat(${pattern.length}, ${scale}px)`,
        imageRendering: 'pixelated',
      }}
    >
      {pattern.flatMap((row, y) =>
        row.split('').map((ch, x) => (
          <div
            key={`${x}-${y}`}
            style={{
              background: palette[ch] || 'transparent',
              width: scale,
              height: scale,
            }}
          />
        )),
      )}
    </div>
  );
}

export function PixelCat({ size = 120 }) {
  return (
    <img
      src={catUrl}
      alt="cat mascot"
      className="pixel-img"
      style={{ width: size }}
    />
  );
}

export function PixelCatLaptop({ size = 240 }) {
  return (
    <img
      src={catCodingUrl}
      alt="cat coding"
      className="pixel-img cat-coding"
      style={{ width: size }}
    />
  );
}

export function PixelSave({ scale = 5, color = 'var(--accent)' }) {
  const palette = {
    '#': color,
    a: color,
    b: 'rgba(255,255,255,0.08)',
    c: 'rgba(255,255,255,0.05)',
  };
  return (
    <div style={{ filter: 'drop-shadow(0 0 16px var(--accent-glow))' }}>
      <PixelGrid pattern={SAVE_PATTERN} palette={palette} scale={scale} />
    </div>
  );
}

export function PixelCart({ scale = 3, color = 'var(--accent)' }) {
  const palette = {
    '#': color,
    a: 'rgba(255,255,255,0.08)',
    b: color,
    c: 'rgba(0,0,0,0.4)',
    d: color,
  };
  return <PixelGrid pattern={CART_PATTERN} palette={palette} scale={scale} />;
}

export function CatSunsetLogo() {
  return (
    <svg
      className="cat-sunset-logo"
      viewBox="0 0 500 500"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="saveshiftSunGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="1" />
          <stop offset="100%" stopColor="var(--accent-2)" stopOpacity="1" />
        </linearGradient>
        <filter id="saveshiftLogoGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      <circle cx="250" cy="220" r="180" fill="url(#saveshiftSunGradient)" />
      <g fill="var(--logo-ink)">
        <rect x="70" y="240" width="360" height="8" />
        <rect x="70" y="260" width="360" height="12" />
        <rect x="70" y="285" width="360" height="18" />
        <rect x="70" y="315" width="360" height="25" />
      </g>

      <g transform="translate(125, 120)">
        <rect width="250" height="240" rx="10" fill="var(--logo-panel)" stroke="var(--logo-stroke)" strokeWidth="4" />
        <rect x="50" y="0" width="150" height="80" rx="5" fill="var(--logo-stroke)" opacity="0.6" />
        <rect x="65" y="10" width="120" height="50" rx="2" fill="var(--logo-screen)" opacity="0.55" />
      </g>

      <path
        d="M250,230 C230,230 215,245 215,265 C215,280 225,295 210,330 C200,360 210,420 250,430 C290,420 300,360 290,330 C275,295 285,280 285,265 C285,245 270,230 250,230 Z"
        fill="var(--logo-ink)"
        stroke="var(--logo-stroke)"
        strokeWidth="5"
        filter="url(#saveshiftLogoGlow)"
      />
      <path d="M218,245 L210,215 L235,235 Z" fill="var(--logo-ink)" stroke="var(--logo-stroke)" strokeWidth="3" />
      <path d="M282,245 L290,215 L265,235 Z" fill="var(--logo-ink)" stroke="var(--logo-stroke)" strokeWidth="3" />
      <path
        d="M290,380 C330,380 340,430 300,435 C280,435 270,410 270,410"
        fill="none"
        stroke="var(--logo-stroke)"
        strokeWidth="12"
        strokeLinecap="round"
        filter="url(#saveshiftLogoGlow)"
      />
      <path d="M80,150 L85,135 L90,150 L105,155 L90,160 L85,175 L80,160 L65,155 Z" fill="var(--accent)" />
      <path d="M420,160 L425,145 L430,160 L445,165 L430,170 L425,185 L420,170 L405,165 Z" fill="var(--accent)" />
    </svg>
  );
}
