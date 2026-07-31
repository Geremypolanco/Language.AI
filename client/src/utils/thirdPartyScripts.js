const LOADED_SCRIPT_IDS = new Set();

function loadScript(id, src, attrs = {}) {
  if (LOADED_SCRIPT_IDS.has(id) || document.getElementById(id)) return;
  const script = document.createElement('script');
  script.id = id;
  script.src = src;
  script.async = true;
  Object.entries(attrs).forEach(([key, value]) => script.setAttribute(key, value));
  document.head.appendChild(script);
  LOADED_SCRIPT_IDS.add(id);
}

function removeScript(id) {
  document.getElementById(id)?.remove();
  LOADED_SCRIPT_IDS.delete(id);
}

const GA_MEASUREMENT_ID = import.meta.env.VITE_GA_MEASUREMENT_ID || '';

/**
 * Zero-cookie-load by default: none of these run on page load. They are only
 * invoked by ConsentContext once the user explicitly grants the matching
 * consent category, and are torn down immediately if consent is revoked.
 */
export function loadAnalyticsScripts() {
  if (!GA_MEASUREMENT_ID) return;
  loadScript('ga-script', `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`);
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() {
    window.dataLayer.push(arguments);
  };
  window.gtag('js', new Date());
  window.gtag('config', GA_MEASUREMENT_ID, { anonymize_ip: true });
}

export function unloadAnalyticsScripts() {
  removeScript('ga-script');
  delete window.gtag;
  delete window.dataLayer;
}

export function loadMarketingScripts() {
  // Placeholder for marketing pixels (e.g. Meta Pixel, LinkedIn Insight).
  // Wire real snippets here, gated identically to analytics.
}

export function unloadMarketingScripts() {
  // Mirror teardown for whatever loadMarketingScripts() adds.
}
