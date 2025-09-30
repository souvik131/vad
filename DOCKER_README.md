# Docker Deployment for Advanced VAD

This Docker Compose setup runs the Advanced Voice Activity Detection application with both backend and frontend services.

## Quick Start

1. **Build and start the services:**
   ```bash
   docker-compose up --build
   ```

2. **Access the application:**
   - Frontend: http://localhost:3002
   - Backend WebSocket: ws://localhost:3001

3. **Stop the services:**
   ```bash
   docker-compose down
   ```

## Services

### Backend (vad-backend)
- **Port:** 3001
- **Technology:** Python with WebSocket server
- **Features:** RMS Energy + Spectral Flatness + Zero Crossing Rate VAD
- **Health Check:** WebSocket connection test

### Frontend (vad-frontend)
- **Port:** 3002
- **Technology:** Python HTTP server serving static files
- **Features:** Real-time VAD status display with visual indicators
- **Health Check:** HTTP endpoint test

## Docker Commands

```bash
# Build and start
docker-compose up --build

# Start in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild specific service
docker-compose build vad-backend
docker-compose up vad-backend
```

## Architecture

```
┌─────────────────┐    WebSocket    ┌─────────────────┐
│   Frontend      │◄──────────────►│   Backend       │
│   (Port 3002)   │                │   (Port 3001)   │
│   Static Files  │                │   VAD Engine    │
└─────────────────┘                └─────────────────┘
```

## Features

- **Real-time VAD:** Detects speech vs silence using advanced signal processing
- **Visual Indicators:** Live UI updates showing 🎤 SPEECH or 🔇 SILENCE
- **Health Checks:** Automatic service monitoring and restart
- **Network Isolation:** Services communicate through Docker network
- **Auto-restart:** Services restart automatically on failure

## Troubleshooting

1. **Port conflicts:** Ensure ports 3001 and 3002 are available
2. **Build issues:** Run `docker-compose build --no-cache` to rebuild
3. **Connection issues:** Check that both services are healthy in `docker-compose ps`
4. **Logs:** Use `docker-compose logs vad-backend` or `docker-compose logs vad-frontend`
