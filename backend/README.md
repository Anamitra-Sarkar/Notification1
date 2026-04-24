# Web Push Notification Backend

FastAPI backend for handling Web Push notifications with VAPID authentication.

## Quick Start

### 1. Generate VAPID Keys

```bash
python generate_vapid_keys.py
```

This will output your keys and create a `.env.example` file.

### 2. Configure Environment

Copy the generated keys to a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
VAPID_PRIVATE_KEY=your_private_key_here
VAPID_PUBLIC_KEY=your_public_key_here
VAPID_CONTACT=your-email@example.com
FRONTEND_URL=https://your-app.vercel.app
PORT=8000
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --reload --port 8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/vapid-keys` | Get VAPID public key |
| POST | `/api/subscribe` | Register push subscription |
| POST | `/api/unsubscribe` | Remove push subscription |
| GET | `/api/subscriptions` | List all subscriptions |
| POST | `/api/send` | Send notification to specific endpoint |
| POST | `/api/broadcast` | Broadcast to all subscribers |
| DELETE | `/api/subscriptions` | Clear all subscriptions |

## Deploy to Render

1. Create a new Web Service on [Render](https://render.com)
2. Connect your repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables in Render dashboard:
   - `VAPID_PRIVATE_KEY`
   - `VAPID_PUBLIC_KEY`
   - `VAPID_CONTACT`
   - `FRONTEND_URL` (your Vercel URL)

## Testing

### Test Subscription Flow

1. Open frontend in browser
2. Click "Subscribe to Notifications"
3. Grant permission when prompted
4. Verify subscription appears in UI

### Test Sending Notifications

```bash
# Get VAPID public key
curl http://localhost:8000/api/vapid-keys

# Check health
curl http://localhost:8000/health

# List subscriptions
curl http://localhost:8000/api/subscriptions

# Send test notification (broadcast)
curl -X POST http://localhost:8000/api/broadcast \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "title": "Test Notification",
      "body": "Hello from the backend!",
      "url": "/"
    }
  }'
```

## Database

The backend uses SQLite by default (`subscriptions.db`). The database is automatically created on first run.

Schema:
```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT UNIQUE NOT NULL,
    keys_p256dh TEXT NOT NULL,
    keys_auth TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Security Notes

- Never commit `.env` to version control
- VAPID private key must be kept secret
- Use HTTPS in production (required for Web Push anyway)
- CORS is configured to only allow your frontend domain

## Troubleshooting

### "VAPID keys not configured"
Run `python generate_vapid_keys.py` and set the environment variables.

### CORS errors
Ensure `FRONTEND_URL` matches your frontend domain exactly (including https).

### Notifications not showing
- Check browser notification permissions
- Verify Service Worker is registered correctly
- Ensure you're using HTTPS (or localhost)
