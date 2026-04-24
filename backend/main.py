"""
Web Push Notification Backend - FastAPI
Handles VAPID key generation, subscription management, and push notification delivery
"""

import os
import json
import sqlite3
import base64
from contextlib import contextmanager
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, EmailStr
from webpush import WebPush, WebPushSubscription, VAPID
import httpx
import uvicorn

# ============================================================================
# Configuration
# ============================================================================

class Settings:
    """Application settings from environment variables"""
    
    # VAPID Keys - Generate using: python generate_vapid_keys.py
    vapid_private_key: str = os.getenv("VAPID_PRIVATE_KEY", "")
    vapid_public_key: str = os.getenv("VAPID_PUBLIC_KEY", "")
    
    # Contact email for VAPID (required by spec)
    vapid_contact: str = os.getenv("VAPID_CONTACT", "admin@example.com")
    
    # Frontend URL for CORS
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # Database path
    database_path: str = os.getenv("DATABASE_PATH", "subscriptions.db")
    
    @property
    def is_configured(self) -> bool:
        """Check if VAPID keys are configured"""
        return bool(self.vapid_private_key and self.vapid_public_key)

settings = Settings()

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Web Push Notification Server",
    description="Backend service for managing Web Push subscriptions and sending notifications",
    version="1.0.0"
)

# CORS Middleware - Allow requests from Vercel frontend
# NOTE: FastAPI CORSMiddleware does NOT support wildcard subdomains like "https://*.vercel.app"
# You must list exact origins. Set FRONTEND_URL env var on Render to your Vercel URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:8080",
        "https://notification1-inky.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["*"],
)

# ============================================================================
# Database Setup
# ============================================================================

def init_database():
    """Initialize SQLite database for storing subscriptions"""
    conn = sqlite3.connect(settings.database_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT UNIQUE NOT NULL,
            keys_p256dh TEXT NOT NULL,
            keys_auth TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_endpoint ON subscriptions(endpoint)
    """)
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {settings.database_path}")

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# ============================================================================
# Pydantic Models
# ============================================================================

class SubscriptionKeys(BaseModel):
    """Push subscription keys"""
    p256dh: str
    auth: str

class PushSubscription(BaseModel):
    """Web Push subscription object"""
    endpoint: HttpUrl
    keys: SubscriptionKeys

class UnsubscribeRequest(BaseModel):
    """Request model for unsubscription"""
    endpoint: str

class NotificationPayload(BaseModel):
    """Notification payload model"""
    title: str = "New Notification"
    body: str = "You have a new message"
    icon: Optional[str] = None
    badge: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None
    tag: Optional[str] = "default"
    requireInteraction: Optional[bool] = False

class SendNotificationRequest(BaseModel):
    """Request to send notification to specific endpoint"""
    endpoint: str
    payload: NotificationPayload

class BroadcastRequest(BaseModel):
    """Request to broadcast notification to all subscribers"""
    payload: NotificationPayload

class VAPIDKeysResponse(BaseModel):
    """Response containing VAPID public key"""
    public_key: str
    contact: str

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    vapid_configured: bool
    subscription_count: int

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM subscriptions")
        count = cursor.fetchone()[0]
    
    return HealthResponse(
        status="healthy",
        vapid_configured=settings.is_configured,
        subscription_count=count
    )

@app.get("/api/vapid-keys", response_model=VAPIDKeysResponse)
async def get_vapid_keys():
    """Get VAPID public key for client-side subscription"""
    if not settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID keys not configured on server"
        )
    
    return VAPIDKeysResponse(
        public_key=settings.vapid_public_key,
        contact=settings.vapid_contact
    )

@app.post("/api/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(subscription: PushSubscription):
    """
    Register a new push subscription
    
    Stores the subscription in the database for later use
    """
    if not settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID keys not configured"
        )
    
    endpoint = str(subscription.endpoint)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if subscription already exists
        cursor.execute(
            "SELECT id FROM subscriptions WHERE endpoint = ?",
            (endpoint,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing subscription
            cursor.execute(
                """
                UPDATE subscriptions 
                SET keys_p256dh = ?, keys_auth = ?, updated_at = CURRENT_TIMESTAMP
                WHERE endpoint = ?
                """,
                (subscription.keys.p256dh, subscription.keys.auth, endpoint)
            )
            print(f"Updated existing subscription: {endpoint}")
        else:
            # Insert new subscription
            cursor.execute(
                """
                INSERT INTO subscriptions (endpoint, keys_p256dh, keys_auth)
                VALUES (?, ?, ?)
                """,
                (endpoint, subscription.keys.p256dh, subscription.keys.auth)
            )
            print(f"Created new subscription: {endpoint}")
        
        conn.commit()
    
    return {"status": "success", "message": "Subscription registered"}

@app.post("/api/unsubscribe")
async def unsubscribe(request: UnsubscribeRequest):
    """
    Remove a push subscription
    
    Deletes the subscription from the database
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM subscriptions WHERE endpoint = ?",
            (request.endpoint,)
        )
        deleted = cursor.rowcount
        conn.commit()
    
    if deleted == 0:
        return {"status": "not_found", "message": "Subscription not found"}
    
    print(f"Deleted subscription: {request.endpoint}")
    return {"status": "success", "message": "Subscription removed"}

@app.get("/api/subscriptions")
async def list_subscriptions():
    """List all registered subscriptions (for debugging/admin)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, endpoint, created_at FROM subscriptions ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
    
    subscriptions = [
        {
            "id": row["id"],
            "endpoint": row["endpoint"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]
    
    return {"count": len(subscriptions), "subscriptions": subscriptions}

@app.post("/api/send")
async def send_notification(request: SendNotificationRequest):
    """
    Send a push notification to a specific endpoint
    
    This is useful for targeted notifications
    """
    if not settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID keys not configured"
        )
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT keys_p256dh, keys_auth FROM subscriptions WHERE endpoint = ?",
            (request.endpoint,)
        )
        row = cursor.fetchone()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found"
        )
    
    # Prepare notification data
    notification_data = {
        "title": request.payload.title,
        "body": request.payload.body,
        "icon": request.payload.icon,
        "badge": request.payload.badge,
        "image": request.payload.image,
        "data": {"url": request.payload.url},
        "tag": request.payload.tag,
        "requireInteraction": request.payload.requireInteraction,
    }
    
    try:
        web_push = WebPush(
            private_key=settings.vapid_private_key.encode(),
            public_key=settings.vapid_public_key.encode(),
            subscriber=settings.vapid_contact,
            ttl=86400,
            expiration=86400
        )
        
        subscription = WebPushSubscription(
            endpoint=request.endpoint,
            keys={
                "p256dh": row["keys_p256dh"],
                "auth": row["keys_auth"]
            }
        )
        
        message = web_push.get(
            message=notification_data,
            subscription=subscription
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                request.endpoint,
                headers=message.headers,
                content=message.encrypted
            )
        
        print(f"Notification sent to {request.endpoint}: {response.status_code}")
        
        return {
            "status": "success",
            "message": "Notification sent",
            "response_code": response.status_code
        }
        
    except Exception as e:
        print(f"Failed to send notification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send notification: {str(e)}"
        )

@app.post("/api/broadcast")
async def broadcast_notification(request: BroadcastRequest):
    """
    Broadcast a push notification to all subscribed devices
    
    Useful for announcements or system-wide messages
    """
    if not settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID keys not configured"
        )
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT endpoint, keys_p256dh, keys_auth FROM subscriptions"
        )
        subscriptions = cursor.fetchall()
    
    if not subscriptions:
        return {
            "status": "no_subscribers",
            "message": "No active subscriptions",
            "sent_count": 0
        }
    
    # Prepare notification data
    notification_data = {
        "title": request.payload.title,
        "body": request.payload.body,
        "icon": request.payload.icon,
        "badge": request.payload.badge,
        "image": request.payload.image,
        "data": {"url": request.payload.url},
        "tag": request.payload.tag,
        "requireInteraction": request.payload.requireInteraction,
    }
    
    results = {"success": 0, "failed": 0, "errors": []}
    
    for sub in subscriptions:
        try:
            web_push = WebPush(
                private_key=settings.vapid_private_key.encode(),
                public_key=settings.vapid_public_key.encode(),
                subscriber=settings.vapid_contact,
                ttl=86400,
                expiration=86400
            )
            
            subscription = WebPushSubscription(
                endpoint=sub["endpoint"],
                keys={
                    "p256dh": sub["keys_p256dh"],
                    "auth": sub["keys_auth"]
                }
            )
            
            message = web_push.get(
                message=notification_data,
                subscription=subscription
            )
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    sub["endpoint"],
                    headers=message.headers,
                    content=message.encrypted
                )
            
            if response.status_code in [200, 201, 202, 204]:
                results["success"] += 1
                print(f"Sent to {sub['endpoint']}: {response.status_code}")
            else:
                results["failed"] += 1
                results["errors"].append({
                    "endpoint": sub["endpoint"],
                    "status": response.status_code
                })
                
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "endpoint": sub["endpoint"],
                "error": str(e)
            })
            print(f"Failed to send to {sub['endpoint']}: {e}")
    
    return {
        "status": "completed",
        "sent_count": results["success"],
        "failed_count": results["failed"],
        "total": len(subscriptions),
        "errors": results["errors"][:10]
    }

@app.delete("/api/subscriptions")
async def clear_all_subscriptions():
    """Clear all subscriptions (admin/debugging utility)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions")
        deleted = cursor.rowcount
        conn.commit()
    
    return {"status": "success", "deleted_count": deleted}

# ============================================================================
# Startup Event
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_database()
    
    if not settings.is_configured:
        print("\n\u26a0\ufe0f  WARNING: VAPID keys not configured!")
        print("Run: python generate_vapid_keys.py")
        print("Then set VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY environment variables\n")
    else:
        print("\n\u2705 VAPID keys configured")
        print(f"Public Key: {settings.vapid_public_key[:20]}...\n")

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
