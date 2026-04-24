/**
 * Service Worker for Web Push Notifications
 * Handles push events and notification interactions
 */

const CACHE_NAME = 'push-notification-cache-v1';

/**
 * Install event - cache assets if needed
 */
self.addEventListener('install', (event) => {
    console.log('[SW] Service Worker installing...');
    self.skipWaiting();
});

/**
 * Activate event - clean up old caches
 */
self.addEventListener('activate', (event) => {
    console.log('[SW] Service Worker activated');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

/**
 * Push event - handle incoming push notifications
 */
self.addEventListener('push', (event) => {
    console.log('[SW] Push event received', event);

    let data = {};
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'Notification', body: event.data.text() };
        }
    }

    const title = data.title || 'New Notification';
    const options = {
        body: data.body || 'You have a new message',
        icon: data.icon || '/icon-192.png',
        badge: data.badge || '/badge-72.png',
        image: data.image || null,
        data: data.data || {},
        tag: data.tag || 'default-tag',
        requireInteraction: data.requireInteraction || false,
        actions: data.actions || [
            { action: 'open', title: 'Open' },
            { action: 'dismiss', title: 'Dismiss' }
        ],
        vibrate: data.vibrate || [200, 100, 200],
        silent: data.silent || false
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

/**
 * Notification click event - handle user interaction
 */
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] Notification clicked', event);
    
    event.notification.close();

    const urlToOpen = event.notification.data?.url || '/';
    const action = event.action;

    if (action === 'dismiss') {
        // User dismissed the notification
        console.log('[SW] Notification dismissed');
        return;
    }

    // Default action: open or focus the app
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // Check if there's already a window open
            for (const client of clientList) {
                if (client.url === urlToOpen && 'focus' in client) {
                    return client.focus();
                }
            }
            // No window open, open a new one
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});

/**
 * Handle background sync if needed
 */
self.addEventListener('sync', (event) => {
    console.log('[SW] Sync event:', event.tag);
});

/**
 * Handle periodic background sync if supported
 */
self.addEventListener('periodicsync', (event) => {
    console.log('[SW] Periodic sync event:', event.tag);
});
