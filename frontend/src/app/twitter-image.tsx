// Twitter falls back to `og:image` when `twitter:image` is absent, but naming
// it explicitly keeps the card from depending on that fallback. Same artwork,
// same dimensions — no reason to draw it twice.
export { default, alt, size, contentType } from './opengraph-image';
