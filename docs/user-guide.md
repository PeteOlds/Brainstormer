# brainstormer — User guide

## Getting started in the browser

1. Start the app (see install-config.md) and open http://127.0.0.1:5000
2. **Register** with an email and a password (at least 8 characters)
3. **Login** with the same credentials
4. Your access token is stored in the browser and used for authenticated requests

## API usage

All API responses follow:
- Success: `{"data": ..., "message": ...}`
- Error: `{"error": ..., "message": ...}`

### Register
```bash
curl -X POST http://127.0.0.1:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

### Login
```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

### Get current user (authenticated)
```bash
curl http://127.0.0.1:5000/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

## Health check
`GET /api/health` returns `{"data": {"status": "ok"}}`.
