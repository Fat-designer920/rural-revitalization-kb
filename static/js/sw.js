/**
 * sw.js — Service Worker v1.0 (离线缓存+离线提问队列)
 * 来源: basic-service-worker 模式 | MIT
 * ES5兼容, 零依赖
 */
var CACHE_NAME = 'rrkb-v1';
var OFFLINE_QUEUE = 'offline-queue';

/* 缓存策略: 核心页面CacheFirst, API NetworkFirst */
var CORE_PAGES = [
  '/', '/landing', '/qa', '/premium', '/admin',
  '/static/css/design-tokens.css',
  '/static/css/typography-chinese.css',
  '/static/css/components.css',
  '/static/css/water.min.css'
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(CORE_PAGES);
    })
  );
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.filter(function(k) { return k !== CACHE_NAME; })
        .map(function(k) { return caches.delete(k); }));
    })
  );
});

self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);
  /* API请求: 网络优先,失败时排队 */
  if (url.pathname.indexOf('/api/') === 0) {
    event.respondWith(
      fetch(event.request).catch(function() {
        return queueOfflineRequest(event.request);
      })
    );
    return;
  }
  /* 页面/CSS/JS: 缓存优先 */
  event.respondWith(
    caches.match(event.request).then(function(cached) {
      return cached || fetch(event.request).then(function(response) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) {
          cache.put(event.request, clone);
        });
        return response;
      });
    })
  );
});

/* 离线请求排队(IndexedDB) */
function queueOfflineRequest(request) {
  return request.json().then(function(body) {
    var dbReq = indexedDB.open(OFFLINE_QUEUE, 1);
    dbReq.onupgradeneeded = function(e) {
      e.target.result.createObjectStore('requests', { keyPath: 'id', autoIncrement: true });
    };
    return new Promise(function(resolve) {
      dbReq.onsuccess = function(e) {
        var tx = e.target.result.transaction('requests', 'readwrite');
        tx.objectStore('requests').add({
          url: request.url, method: request.method,
          body: body, timestamp: Date.now()
        });
        resolve(new Response(JSON.stringify({ ok: true, queued: true }),
          { headers: { 'Content-Type': 'application/json' } }));
      };
    });
  }).catch(function() {
    return new Response(JSON.stringify({ ok: false, error: 'offline-queue-failed' }),
      { headers: { 'Content-Type': 'application/json' } });
  });
}
