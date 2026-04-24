const API_URL = 'https://notification1-30ha.onrender.com';
const VAPID_PUBLIC_KEY = 'BOLuHvg6Tm6kwYlmWhPLQebHS5FCVMuu3Dc59cVRa8R4MKNu4nxQeGZpn2pzk4QclNOcrFZ-f0pXpcqPQClDOI8';

let registration = null;
let subscription = null;

const statusEl = document.getElementById('status');
const subscribeBtn = document.getElementById('subscribeBtn');
const unsubscribeBtn = document.getElementById('unsubscribeBtn');
const subscriptionInfo = document.getElementById('subscriptionInfo');
const subscriptionJson = document.getElementById('subscriptionJson');

function updateStatus(message, type = 'neutral') {
    statusEl.textContent = message;
    statusEl.className = '';

    if (type === 'success') {
        statusEl.classList.add('status-success');
    } else if (type === 'error') {
        statusEl.classList.add('status-error');
    }
}

function checkSupport() {
    if (!('serviceWorker' in navigator)) {
        updateStatus('Service Workers not supported', 'error');
        return false;
    }

    if (!('PushManager' in window)) {
        updateStatus('Push notifications not supported', 'error');
        return false;
    }

    if (!('Notification' in window)) {
        updateStatus('Notifications not supported', 'error');
        return false;
    }

    return true;
}

// Utility: convert a Base64URL VAPID public key to Uint8Array for subscribe().
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, '+')
        .replace(/_/g, '/');

    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; i += 1) {
        outputArray[i] = rawData.charCodeAt(i);
    }

    return outputArray;
}

async function getReadyServiceWorkerRegistration() {
    if (!registration) {
        await navigator.serviceWorker.register('/sw.js');
    }

    // Critical: wait for an ACTIVE worker before pushManager.subscribe().
    registration = await navigator.serviceWorker.ready;
    return registration;
}

async function getSubscription() {
    const readyRegistration = await getReadyServiceWorkerRegistration();
    return readyRegistration.pushManager.getSubscription();
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

        updateStatus('Preparing service worker...');
        const readyRegistration = await getReadyServiceWorkerRegistration();

        const existingSubscription = await readyRegistration.pushManager.getSubscription();
        if (existingSubscription) {
            subscription = existingSubscription;
            updateStatus('Already subscribed', 'success');
            updateUI(true);
            return;
        }

        updateStatus('Creating push subscription...');
        subscription = await readyRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
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
        if (!subscription) {
            subscription = await getSubscription();
        }

        if (!subscription) {
            updateStatus('No active subscription found');
            updateUI(false);
            return;
        }

        const endpoint = subscription.endpoint;
        const unsubscribed = await subscription.unsubscribe();

        if (unsubscribed) {
            await removeSubscriptionFromBackend(endpoint);
            subscription = null;
            updateStatus('Successfully unsubscribed', 'success');
            updateUI(false);
        } else {
            updateStatus('Unsubscribe failed', 'error');
        }
    } catch (error) {
        console.error('Unsubscribe failed:', error);
        updateStatus(`Unsubscribe failed: ${error.message}`, 'error');
    }
}

async function sendSubscriptionToBackend(currentSubscription) {
    const response = await fetch(`${API_URL}/api/subscribe`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
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
        const response = await fetch(`${API_URL}/api/unsubscribe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ endpoint })
        });

        if (!response.ok) {
            console.warn('Failed to remove subscription from backend');
        }
    } catch (error) {
        console.error('Failed to remove subscription:', error);
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
        await getReadyServiceWorkerRegistration();
        subscription = await getSubscription();

        if (subscription) {
            updateStatus('Already subscribed to notifications', 'success');
            updateUI(true);
        } else {
            updateStatus('Click "Subscribe" to enable notifications');
            updateUI(false);
        }
    } catch (error) {
        console.error('Initialization failed:', error);
        updateStatus('Initialization failed', 'error');
    }
}

subscribeBtn.addEventListener('click', subscribeToPush);
unsubscribeBtn.addEventListener('click', unsubscribeFromPush);
document.addEventListener('DOMContentLoaded', init);
