# Frontend Configuration

## Environment Variables

Update `app.js` with your actual values:

```javascript
const API_URL = 'https://your-backend.onrender.com';  // Your Render backend URL
const VAPID_PUBLIC_KEY = 'your-vapid-public-key';     // From backend .env
```

## Local Development

```bash
npm install
npm run dev
```

The app will be available at `http://localhost:3000`

## Deployment to Vercel

1. Install Vercel CLI:
```bash
npm i -g vercel
```

2. Deploy:
```bash
vercel --prod
```

3. Set environment variables in Vercel dashboard if needed (though for vanilla JS, you'll need to update `app.js` directly or use a build step)

## Important Notes

- The Service Worker (`sw.js`) must be served from the root directory
- HTTPS is required for push notifications (except on localhost)
- Update `VAPID_PUBLIC_KEY` in `app.js` with the public key from your backend
