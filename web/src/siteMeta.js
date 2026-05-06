import appleTouchIconUrl from '../assets/favicon/apple-touch-icon.png?url';
import favicon96Url from '../assets/favicon/favicon-96x96.png?url';
import faviconIcoUrl from '../assets/favicon/favicon.ico?url';
import manifestIcon192Url from '../assets/favicon/web-app-manifest-192x192.png?url';
import manifestIcon512Url from '../assets/favicon/web-app-manifest-512x512.png?url';

function upsertLink(key, attrs) {
  let link = document.head.querySelector(`link[data-saveshift="${key}"]`);
  if (!link) {
    link = document.createElement('link');
    link.dataset.saveshift = key;
    document.head.appendChild(link);
  }
  for (const [name, value] of Object.entries(attrs)) {
    link.setAttribute(name, value);
  }
}

function upsertMeta(name, content) {
  let meta = document.head.querySelector(`meta[name="${name}"]`);
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', name);
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', content);
}

export function installSiteIcons() {
  upsertLink('favicon-ico', { rel: 'icon', href: faviconIcoUrl, sizes: 'any' });
  upsertLink('favicon-96', { rel: 'icon', type: 'image/png', sizes: '96x96', href: favicon96Url });
  upsertLink('apple-touch-icon', { rel: 'apple-touch-icon', sizes: '180x180', href: appleTouchIconUrl });

  const manifest = {
    name: 'SaveShift',
    short_name: 'SaveShift',
    icons: [
      { src: manifestIcon192Url, sizes: '192x192', type: 'image/png', purpose: 'maskable' },
      { src: manifestIcon512Url, sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
    theme_color: '#0a0612',
    background_color: '#0a0612',
    display: 'standalone',
  };
  const manifestUrl = URL.createObjectURL(
    new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' }),
  );
  upsertLink('manifest', { rel: 'manifest', href: manifestUrl });
  upsertMeta('theme-color', '#0a0612');
}
