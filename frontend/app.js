// Backend API URL - Update this for production deployment
const API_URL = process.env.API_URL || 'https://notification1-30ha.onrender.com';

// VAPID Public Key - Replace with your actual public key from backend
const VAPID_PUBLIC_KEY = 'BOLuHvg6Tm6kwYlmWhPLQebHS5FCVMuu3Dc59cVRa8R4MKNu4nxQeGZpn2pzk4QclNOcrFZ-f0pXpcqPQClDOI8';

let registration = null;
let subscription = null;

const statusEl = document.getElementById('status');
const subscribeBtn = document.getElementById('subscribeBtn');
const unsubscribeBtn = document.getElementById('unsubscribeBtn');
const subscriptionInfo = document.getElementById('subscriptionInfo');
const subscriptionJson = document.getElementById('subscriptionJson');

/**
 * Convert Uint8Array to Base64URL string
 */
function uint8ToBase64URL(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer)))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
}

/**
 * Convert Base64URL string to Uint8Array
 */
function base64URLToUint8(base64URL) {
    const base64 = base64URL.replace(/-/g, '+').replace(/_/g, '/');
    const padding = '='.repeat((4 - base64.length % 4) % 4);
    const padded = base64 + padding;
    const binaryString = atob(padded);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
}

/**
 * Update UI status message
 */
function updateStatus(message, type = 'neutral') {
    statusEl.textContent = message;
    statusEl.className = '';
    if (type === 'success') {
        statusEl.classList.add('status-success');
    } else if (type === 'error') {
        statusEl.classList.add('status-error');
    }
}

/**
 * Check if push notifications are supported
 */
function checkSupport() {
    if (!('serviceWorker' in navigator)) {
        updateStatus('Service Workers not supported', 'error');
        return false;
    }
    if (!('PushManager' in window)) {
        updateStatus('Push Notifications not supported', 'error');
        return false;
    }
    if (!('Notification' in window)) {
        updateStatus('Notifications not supported', 'error');
        return false;
    }
    return true;
}

/**
 * Register the Service Worker
 */
async function registerServiceWorker() {
    try {
        registration = await navigator.serviceWorker.register('/sw.js');
        console.log('Service Worker registered:', registration.scope);
        
        // Handle updates
        registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            console.log('Service Worker update found');
        });
        
        return registration;
    } catch (error) {
        console.error('Service Worker registration failed:', error);
        throw error;
    }
}

/**
 * Get existing subscription or create new one
 */
async function getSubscription() {
    if (!registration) {
        throw new Error('Service Worker not registered');
    }
    return await registration.pushManager.getSubscription();
}

/**
 * Subscribe to push notifications
 */
async function subscribeToPush() {
    try {
        updateStatus('Requesting notification permission...');
        
        // Request permission
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            updateStatus('Notification permission denied', 'error');
            return;
        }

        updateStatus('Registering service worker...');
        await registerServiceWorker();

        updateStatus('Creating push subscription...');
        
        // Convert VAPID key to Uint8Array
        const vapidKeyUint8 = base64URLToUint8(VAPID_PUBLIC_KEY);

        // Subscribe with VAPID
        subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: vapidKeyUint8
        });

        console.log('Push subscription created:', subscription);

        // Send subscription to backend
        updateStatus('Sending subscription to server...');
        await sendSubscriptionToBackend(subscription);

        updateStatus('Successfully subscribed!', 'success');
        updateUI(true);

    } catch (error) {
        console.error('Subscription failed:', error);
        updateStatus(`Subscription failed: ${error.message}`, 'error');
    }
}

/**
 * Unsubscribe from push notifications
 */
async function unsubscribeFromPush() {
    try {
        if (!subscription) {
            subscription = await getSubscription();
        }

        if (subscription) {
            const result = await subscription.unsubscribe();
            if (result) {
                // Notify backend to remove subscription
                await removeSubscriptionFromBackend(subscription);
                
                updateStatus('Successfully unsubscribed', 'success');
                subscription = null;
                updateUI(false);
            } else {
                updateStatus('Unsubscribe failed', 'error');
            }
        }
    } catch (error) {
        console.error('Unsubscribe failed:', error);
        updateStatus(`Unsubscribe failed: ${error.message}`, 'error');
    }
}

/**
 * Send subscription to backend server
 */
async function sendSubscriptionToBackend(subscription) {
    try {
        const response = await fetch(`${API_URL}/api/subscribe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(subscription)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save subscription');
        }

        return await response.json();
    } catch (error) {
        console.error('Failed to send subscription:', error);
        throw error;
    }
}

/**
 * Remove subscription from backend server
 */
async function removeSubscriptionFromBackend(subscription) {
    try {
        const response = await fetch(`${API_URL}/api/unsubscribe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                endpoint: subscription.endpoint
            })
        });

        if (!response.ok) {
            console.warn('Failed to remove subscription from backend');
        }

        return await response.json();
    } catch (error) {
        console.error('Failed to remove subscription:', error);
    }
}

/**
 * Update UI based on subscription state
 */
async function updateUI(isSubscribed) {
    if (isSubscribed) {
        subscribeBtn.disabled = true;
        unsubscribeBtn.disabled = false;
        subscriptionInfo.classList.remove('hidden');
        subscriptionJson.textContent = JSON.stringify(subscription, null, 2);
    } else {
        subscribeBtn.disabled = false;
        unsubscribeBtn.disabled = true;
        subscriptionInfo.classList.add('hidden');
    }
}

/**
 * Initialize the application
 */
async function init() {
    if (!checkSupport()) {
        subscribeBtn.disabled = true;
        unsubscribeBtn.disabled = true;
        return;
    }

    try {
        // Check for existing subscription
        await registerServiceWorker();
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

// Event listeners
subscribeBtn.addEventListener('click', subscribeToPush);
unsubscribeBtn.addEventListener('click', unsubscribeFromPush);

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
