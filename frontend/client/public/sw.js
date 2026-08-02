// Minimal offline-first service worker for Language.AI — hand-rolled
// (no vite-plugin-pwa) specifically to avoid a stale precache list, since
// Vite's build output uses content-hashed filenames that change on every
// deploy. Uses runtime caching instead of a build-time precache manifest:
//
// - Navigation requests and static assets (JS/CSS/images): cache-first,
//   refreshing the cache in the background — lets the app shell at least
//   LOAD offline after the first real visit.
// - Same-origin GET /api/* requests: network-first, falling back to the
//   last cached response — lets a learner re-open a lesson/unit/course
//   they already viewed online, even without a connection.
//
// Deliberately NOT attempted here: intercepting POST/PUT/PATCH (submitting
// answers, completing a lesson) to queue them for replay once back online.
// That's real, separate offline-sync work — queuing writes safely (order,
// conflicts, partial failures) is a different problem than caching reads,
// and pretending to solve it with a half-measure would be worse than not
// touching it at all. Writes made while offline currently just fail
// normally, same as before this file existed.

const RUNTIME_CACHE = "langai-runtime-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== RUNTIME_CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // never intercept writes

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // same-origin only

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request));
  } else {
    event.respondWith(cacheFirst(request));
  }
});

async function cacheFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);
  const networkFetch = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => undefined);
  if (cached) return cached;
  const fromNetwork = await networkFetch;
  return fromNetwork || Response.error();
}

async function networkFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw new Error("offline and no cached response for " + request.url);
  }
}
