const API_URL = 'https://notification1-30ha.onrender.com';
const FALLBACK_VAPID_PUBLIC_KEY = 'BPXjI5L6TwWAzXqMqlz_pxPpFgScBV3BAV5e4hGQAihYLb_NFcArKzzGtAJAuJHDrHNOcdMW8ui72TS_-FL7hpA';

let vapidPublicKey = null;
let swRegistration = null;
let subscription = null;

const statusEl = document.getElementById('status');
const subscribeBtn = document.getElementById('subscribeBtn');
const unsubscribeBtn = document.getElementById('unsubscribeBtn');
const subscriptionInfo = document.getElementById('subscriptionInfo');
const subscriptionJson = document.getElementById('subscriptionJson');

function updateStatus(message, type = 'neutral') {
    statusEl.textContent = message;
    statusEl.className = '';
    if (type === 'success') statusEl.classList.add('status-success');
    else if (type === 'error') statusEl.classList.add('status-error');
}

function checkSupport() {
    if (!('serviceWorker' in navigator)) { updateStatus('Service Workers not supported', 'error'); return false; }
    if (!('PushManager' in window)) { updateStatus('Push notifications not supported', 'error'); return false; }
    if (!('Notification' in window)) { updateStatus('Notifications not supported', 'error'); return false; }
    if (!window.isSecureContext) { updateStatus('Push notifications require HTTPS', 'error'); return false; }
    return true;
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
}

async function getVapidPublicKey() {
    if (vapidPublicKey) return vapidPublicKey;
    try {
        const response = await fetch(`${API_URL}/api/vapid-keys`);
        if (!response.ok) throw new Error(`Backend returned ${response.status}`);
        const data = await response.json();
        if (!data.public_key) throw new Error('VAPID public key missing in response');
        vapidPublicKey = data.public_key;
        return vapidPublicKey;
    } catch (error) {
        console.warn('Failed to fetch VAPID key, using fallback:', error);
        vapidPublicKey = FALLBACK_VAPID_PUBLIC_KEY;
        return vapidPublicKey;
    }
}

async function getReadyServiceWorkerRegistration() {
    // Always register fresh, store the result, then wait for it to be active
    swRegistration = await navigator.serviceWorker.register('/sw.js');

    // If SW is installing, wait for it to finish
    if (swRegistration.installing) {
        await new Promise((resolve) => {
            swRegistration.installing.addEventListener('statechange', function handler(e) {
                if (e.target.state === 'activated') {
                    swRegistration.installing && swRegistration.installing.removeEventListener('statechange', handler);
                    resolve();
                }
            });
        });
    }

    // navigator.serviceWorker.ready guarantees an active+controlling SW
    swRegistration = await navigator.serviceWorker.ready;
    return swRegistration;
}

async function subscribeToPush() {
    try {
        if (Notification.permission === 'denied') {
            updateStatus('Notifications are blocked in browser settings', 'error');
            return;
        }

        if (Notification.permission !== 'granted') {
            updateStatus('Requesting notification permission...');
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                updateStatus('Notification permission not granted', 'error');
                return;
            }
        }

        updateStatus('Registering service worker...');
        const reg = await getReadyServiceWorkerRegistration();

        const existingSubscription = await reg.pushManager.getSubscription();
        if (existingSubscription) {
            // Unsubscribe old subscription to avoid stale key issues
            await existingSubscription.unsubscribe();
        }

        const publicKey = await getVapidPublicKey();

        updateStatus('Creating push subscription...');
        subscription = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey)
        });

        await sendSubscriptionToBackend(subscription);
        updateStatus('Successfully subscribed!', 'success');
        updateUI(true);
    } catch (error) {
        console.error('Subscription failed:', error);
        updateStatus(`Subscription failed: ${error.message}`, 'error');
    }
}

async function unsubscribeFromPush() {
    try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();

        if (!sub) {
            updateStatus('No active subscription found');
            updateUI(false);
            return;
        }

        const endpoint = sub.endpoint;
        await sub.unsubscribe();
        await removeSubscriptionFromBackend(endpoint);
        subscription = null;
        updateStatus('Successfully unsubscribed', 'success');
        updateUI(false);
    } catch (error) {
        console.error('Unsubscribe failed:', error);
        updateStatus(`Unsubscribe failed: ${error.message}`, 'error');
    }
}

async function sendSubscriptionToBackend(currentSubscription) {
    const response = await fetch(`${API_URL}/api/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentSubscription)
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to save subscription');
    }
    return response.json();
}

async function removeSubscriptionFromBackend(endpoint) {
    try {
        await fetch(`${API_URL}/api/unsubscribe`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ endpoint })
        });
    } catch (error) {
        console.error('Failed to remove subscription from backend:', error);
    }
}

function updateUI(isSubscribed) {
    if (isSubscribed) {
        subscribeBtn.disabled = true;
        unsubscribeBtn.disabled = false;
        subscriptionInfo.classList.remove('hidden');
        subscriptionJson.textContent = JSON.stringify(subscription, null, 2);
        return;
    }
    subscribeBtn.disabled = false;
    unsubscribeBtn.disabled = true;
    subscriptionInfo.classList.add('hidden');
}

async function init() {
    if (!checkSupport()) {
        subscribeBtn.disabled = true;
        unsubscribeBtn.disabled = true;
        return;
    }

    try {
        const reg = await getReadyServiceWorkerRegistration();
        vapidPublicKey = await getVapidPublicKey();
        subscription = await reg.pushManager.getSubscription();

        if (subscription) {
            updateStatus('Already subscribed to notifications', 'success');
            updateUI(true);
        } else {
            updateStatus('Click "Subscribe" to enable notifications');
            updateUI(false);
        }
    } catch (error) {
        console.error('Initialization failed:', error);
        updateStatus('Initialization failed: ' + error.message, 'error');
    }
}

subscribeBtn.addEventListener('click', subscribeToPush);
unsubscribeBtn.addEventListener('click', unsubscribeFromPush);

init();
