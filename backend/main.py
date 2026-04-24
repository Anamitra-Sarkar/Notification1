"""
Web Push Notification Backend - FastAPI
"""

import os
import json
import sqlite3
import base64
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from pywebpush import webpush, WebPushException
import uvicorn

# ============================================================================
# Configuration
# ============================================================================

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CONTACT = os.getenv("VAPID_CONTACT", "mailto:admin@example.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
DATABASE_PATH = os.getenv("DATABASE_PATH", "subscriptions.db")

def is_configured():
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(title="Web Push Notification Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:8080",
        "https://notification1-inky.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["*"],
)

# ============================================================================
# Database
# ============================================================================

def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT UNIQUE NOT NULL,
            keys_p256dh TEXT NOT NULL,
            keys_auth TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# ============================================================================
# Models
# ============================================================================

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys

class UnsubscribeRequest(BaseModel):
    endpoint: str

class NotificationPayload(BaseModel):
    title: str = "New Notification"
    body: str = "You have a new message"
    icon: Optional[str] = None
    url: Optional[str] = None
    tag: Optional[str] = "default"

class SendRequest(BaseModel):
    endpoint: str
    payload: NotificationPayload

class BroadcastRequest(BaseModel):
    payload: NotificationPayload

# ============================================================================
# Helper: send one push
# ============================================================================

def send_push(endpoint: str, p256dh: str, auth: str, payload: NotificationPayload):
    """Send a single push notification using pywebpush."""
    data = json.dumps({
        "title": payload.title,
        "body": payload.body,
        "icon": payload.icon,
        "data": {"url": payload.url or "/"},
        "tag": payload.tag,
    })

    # pywebpush expects the VAPID contact to start with mailto:
    contact = VAPID_CONTACT if VAPID_CONTACT.startswith("mailto:") else f"mailto:{VAPID_CONTACT}"

    webpush(
        subscription_info={
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        },
        data=data,
        vapid_private_key=VAPID_PRIVATE_KEY,
        vapid_claims={"sub": contact},
    )

# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
    return {"status": "healthy", "vapid_configured": is_configured(), "subscription_count": count}

@app.get("/api/vapid-keys")
async def get_vapid_keys():
    if not is_configured():
        raise HTTPException(status_code=503, detail="VAPID keys not configured")
    return {"public_key": VAPID_PUBLIC_KEY, "contact": VAPID_CONTACT}

@app.post("/api/subscribe", status_code=201)
async def subscribe(sub: PushSubscription):
    if not is_configured():
        raise HTTPException(status_code=503, detail="VAPID keys not configured")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE endpoint = ?", (sub.endpoint,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE subscriptions SET keys_p256dh = ?, keys_auth = ? WHERE endpoint = ?",
                (sub.keys.p256dh, sub.keys.auth, sub.endpoint),
            )
        else:
            conn.execute(
                "INSERT INTO subscriptions (endpoint, keys_p256dh, keys_auth) VALUES (?, ?, ?)",
                (sub.endpoint, sub.keys.p256dh, sub.keys.auth),
            )
        conn.commit()

    return {"status": "success", "message": "Subscription registered"}

@app.post("/api/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    with get_db() as conn:
        deleted = conn.execute(
            "DELETE FROM subscriptions WHERE endpoint = ?", (req.endpoint,)
        ).rowcount
        conn.commit()
    return {"status": "success" if deleted else "not_found"}

@app.get("/api/subscriptions")
async def list_subscriptions():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, endpoint, created_at FROM subscriptions ORDER BY created_at DESC"
        ).fetchall()
    return {"count": len(rows), "subscriptions": [dict(r) for r in rows]}

@app.post("/api/send")
async def send_notification(req: SendRequest):
    if not is_configured():
        raise HTTPException(status_code=503, detail="VAPID keys not configured")

    with get_db() as conn:
        row = conn.execute(
            "SELECT keys_p256dh, keys_auth FROM subscriptions WHERE endpoint = ?",
            (req.endpoint,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")

    try:
        send_push(req.endpoint, row["keys_p256dh"], row["keys_auth"], req.payload)
        return {"status": "success", "message": "Notification sent"}
    except WebPushException as e:
        raise HTTPException(status_code=500, detail=f"Push failed: {e.response.text if e.response else str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    if not is_configured():
        raise HTTPException(status_code=503, detail="VAPID keys not configured")

    with get_db() as conn:
        subs = conn.execute(
            "SELECT endpoint, keys_p256dh, keys_auth FROM subscriptions"
        ).fetchall()

    if not subs:
        return {"status": "no_subscribers", "sent_count": 0}

    success, failed, errors = 0, 0, []
    for sub in subs:
        try:
            send_push(sub["endpoint"], sub["keys_p256dh"], sub["keys_auth"], req.payload)
            success += 1
        except WebPushException as e:
            failed += 1
            errors.append({"endpoint": sub["endpoint"], "error": e.response.text if e.response else str(e)})
        except Exception as e:
            failed += 1
            errors.append({"endpoint": sub["endpoint"], "error": str(e)})

    return {"status": "completed", "sent_count": success, "failed_count": failed, "errors": errors[:10]}

@app.delete("/api/subscriptions")
async def clear_subscriptions():
    with get_db() as conn:
        deleted = conn.execute("DELETE FROM subscriptions").rowcount
        conn.commit()
    return {"status": "success", "deleted_count": deleted}

# ============================================================================
# Startup
# ============================================================================

@app.on_event("startup")
async def startup_event():
    init_database()
    if not is_configured():
        print("\n⚠️  WARNING: VAPID keys not configured! Set VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY env vars.\n")
    else:
        print(f"\n✅ VAPID configured. Public key: {VAPID_PUBLIC_KEY[:20]}...\n")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
