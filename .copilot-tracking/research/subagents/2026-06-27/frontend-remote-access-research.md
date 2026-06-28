# Frontend Dashboard & Remote Access Research

## Research Topics

1. React dashboard vs Streamlit for wildlife camera monitoring
2. Cloudflare Tunnel for remote access
3. Streamlit deployment considerations
4. React + Vite lightweight setup
5. Dashboard features for wildlife camera system
6. Grafana as an alternative
7. Push notification options

---

## 1. React Dashboard vs Streamlit

### Streamlit

**Pros:**
- Extremely fast development speed — pure Python, no JS/HTML/CSS needed
- Ideal for data-heavy dashboards with built-in charting (`st.line_chart`, `st.bar_chart`, plotly)
- Built-in image display (`st.image`), file upload, and data tables
- Hot-reload during development
- Single file can create a full dashboard
- Already in the Python ecosystem (matches your FastAPI backend)

**Cons:**
- **Mobile responsiveness is limited** — Streamlit's layout is not truly mobile-first; columns collapse but the experience is mediocre on phones
- **No native WebSocket/real-time** — Streamlit uses a polling mechanism; `st.rerun()` or `st.fragment` can simulate real-time but it's not true push-based updates
- **Image gallery performance** — loading many thumbnails requires custom components or pagination; no native lightbox
- **Customization ceiling** — you're constrained to Streamlit's layout system; complex UIs require custom components (iframes with React inside Streamlit)
- **State management** — session state can be quirky; every interaction triggers a full rerun of the script
- **Single-threaded** — one user session runs one Python process; scaling is resource-intensive on a Pi 5
- **Not a production web framework** — no built-in auth, no URL routing, limited API integration

**Resource usage on Pi 5:** Streamlit itself uses ~150-300MB RAM per session. On a Pi 5 (8GB), this is workable for 1-2 concurrent users but not ideal.

### React (Vite + TailwindCSS)

**Pros:**
- **Full control over mobile responsiveness** — TailwindCSS gives you first-class responsive design
- **Real-time updates via WebSocket** — native browser WebSocket support, can connect directly to FastAPI WebSocket endpoints
- **Image gallery/lightbox** — many lightweight libraries (react-photo-album, yet-another-react-lightbox)
- **Performance** — static files served by nginx or FastAPI; minimal server resources for the frontend itself
- **PWA support** — can be installed as a mobile app with push notifications
- **Separation of concerns** — frontend is decoupled from backend API

**Cons:**
- **Slower initial development** — need to build components, set up state management
- **JavaScript/TypeScript ecosystem** — different language from backend
- **More moving parts** — build tooling, bundler config, etc.
- **Ongoing maintenance** — npm dependency updates, security patches

### Other Options

| Option | Verdict |
|--------|---------|
| **Next.js** | Overkill for this use case. SSR adds complexity without benefit when serving from a Pi. |
| **Remix** | Similar to Next.js — too heavy for a single-purpose dashboard. |
| **htmx** | Excellent middle ground! Minimal JS, works with FastAPI templates (Jinja2). Progressive enhancement. Good for a solo dev who wants simplicity without Streamlit limitations. |
| **Svelte/SvelteKit** | Lighter than React, excellent DX, smaller bundle sizes. Worth considering. |
| **Vue + Vite** | Similar tradeoffs to React but simpler API. |

### Recommendation

**For a solo developer** with an existing FastAPI backend:

1. **Best balance: htmx + Jinja2 templates + TailwindCSS** — You stay in Python, get server-rendered HTML with dynamic updates (htmx handles partial page updates, WebSocket support via `hx-ws`), TailwindCSS for responsive design, and zero build step. Extremely low maintenance overhead.

2. **If you want a richer SPA: React + Vite + TailwindCSS** — More upfront work but gives you the best mobile experience, real-time WebSocket updates, and rich image gallery components.

3. **If speed-to-prototype matters most: Streamlit** — Get something working in hours, but accept mobile/real-time limitations.

---

## 2. Cloudflare Tunnel for Remote Access

### Overview

Cloudflare Tunnel (`cloudflared`) creates an outbound-only connection from your Pi 5 to Cloudflare's global network. No port forwarding, no exposed public IP, no dynamic DNS needed.

### Free Tier

- **Cloudflare Tunnel is FREE** on the Cloudflare Zero Trust free plan
- Free plan includes: up to 50 users, 1 tunnel (unlimited connections within it)
- You need a domain registered with or using Cloudflare DNS (domain registration is at-cost, ~$10/year for a .com)
- No bandwidth limits on tunnel traffic for HTTP/HTTPS

### Setup on Raspberry Pi 5

```bash
# Install cloudflared (ARM64 for Pi 5)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Authenticate (opens browser)
cloudflared tunnel login

# Create a tunnel
cloudflared tunnel create piwatcher

# Configure the tunnel (config.yml)
cat > ~/.cloudflared/config.yml << EOF
tunnel: <TUNNEL_UUID>
credentials-file: /home/pi/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: piwatcher.yourdomain.com
    service: http://localhost:8000
  - hostname: grafana.yourdomain.com
    service: http://localhost:3000
  - service: http_status:404
EOF

# Create DNS record
cloudflared tunnel route dns piwatcher piwatcher.yourdomain.com

# Run as a service
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### Authentication with Cloudflare Access

Cloudflare Access (part of Zero Trust free plan) provides authentication without modifying your app:

- **One-time PIN (OTP)** — enter email, get a code (free, no IdP needed)
- **Google/GitHub/Microsoft OAuth** — SSO login
- **Service tokens** — for API/programmatic access

Configuration via Cloudflare dashboard:
1. Go to Zero Trust > Access > Applications
2. Add application > Self-hosted
3. Set domain: `piwatcher.yourdomain.com`
4. Add policy: Allow specific email addresses or email domains

This gives you enterprise-grade auth (with MFA) in front of your Pi dashboard at no cost.

### SSL/TLS

- Cloudflare provides automatic SSL certificates for your domain
- Traffic between user and Cloudflare: encrypted (HTTPS)
- Traffic between Cloudflare and your Pi: travels through the encrypted tunnel
- No need to manage SSL certificates on the Pi

### Limitations

- Requires a domain (can be cheap: ~$10/year)
- Depends on Cloudflare's infrastructure (very reliable, but external dependency)
- Adds ~20-50ms latency vs direct connection (negligible for dashboard use)
- Video streaming works but high-bandwidth continuous streams may hit fair-use limits
- Max upload size: 100MB on free plan (fine for images, not for large video files)

### Verdict

**Cloudflare Tunnel is the ideal solution** for this project. Free, secure, no port forwarding, automatic SSL, built-in authentication.

---

## 3. Streamlit Deployment via Cloudflare Tunnel

### Can Streamlit be exposed via Cloudflare Tunnel?

**Yes**, but with caveats:

- Streamlit runs on port 8501 by default; point the tunnel to `http://localhost:8501`
- WebSocket connections (Streamlit uses them internally) work through Cloudflare Tunnel
- You may need to set `server.enableXsrfProtection = false` and configure `server.headless = true`

```toml
# .streamlit/config.toml
[server]
headless = true
enableCORS = false
enableXsrfProtection = false
port = 8501

[browser]
serverAddress = "piwatcher.yourdomain.com"
serverPort = 443
```

### Performance with Image Galleries

- Streamlit loads all images into the browser via base64 encoding or file serving
- For 50+ thumbnails, expect sluggish performance without pagination
- No native lazy loading — all images in a page load immediately
- Workaround: use `st.columns()` with pagination or `streamlit-image-select` component

### Real-time Updates

- No true push — must use `st.rerun()` triggered by a timer or `st.fragment` (Streamlit 1.33+)
- `st.fragment` allows partial re-execution of decorated functions every N seconds
- Acceptable for 5-30 second polling intervals; not suitable for live feed

### Mobile Responsiveness

- Streamlit has basic responsive behavior (columns stack vertically on narrow screens)
- Sidebar collapses into a hamburger menu
- No fine-grained control over mobile layout
- Text and widgets scale but image galleries don't adapt well

### Verdict

Streamlit works as a quick prototype behind Cloudflare Tunnel but is **not recommended for the production dashboard** due to mobile limitations, image gallery performance, and real-time constraints.

---

## 4. React + Vite Lightweight Setup

### Minimal Stack

```
React 18 + Vite + TailwindCSS + React Router
```

No need for: Redux, Next.js, heavy state management. Use React's built-in `useState`/`useContext` + a lightweight fetch library.

### Project Setup

```bash
npm create vite@latest piwatcher-dashboard -- --template react-ts
cd piwatcher-dashboard
npm install tailwindcss @tailwindcss/vite
npm install react-router-dom
npm install swr  # lightweight data fetching with auto-revalidation
```

### Serving Options

**Option A: Built into FastAPI (recommended for simplicity)**

```python
# In your FastAPI app
from fastapi.staticfiles import StaticFiles

# Build React app: npm run build -> dist/
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
```

- Single deployment unit
- No separate web server needed
- Works perfectly with Cloudflare Tunnel (one port)

**Option B: nginx (better for production)**

```nginx
server {
    listen 80;
    root /var/www/piwatcher/dist;
    index index.html;

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### State Management for Real-time

```typescript
// SWR for data fetching with auto-refresh
import useSWR from 'swr';

function useEvents() {
  return useSWR('/api/events/recent', fetcher, {
    refreshInterval: 10000, // poll every 10s
  });
}

// WebSocket for instant updates
function useWebSocket(url: string) {
  const [data, setData] = useState(null);
  useEffect(() => {
    const ws = new WebSocket(url);
    ws.onmessage = (event) => setData(JSON.parse(event.data));
    return () => ws.close();
  }, [url]);
  return data;
}
```

### Image Lazy Loading

```tsx
// Native lazy loading
<img src={thumbnail_url} loading="lazy" alt={event.classification} />

// Or use Intersection Observer for more control
import { useInView } from 'react-intersection-observer';
```

### Bundle Size Considerations (for Pi 5 serving)

- Vite produces optimized bundles (~50-100KB gzipped for a dashboard)
- Static files are cached by the browser — Pi only serves them once
- TailwindCSS with purging: ~10KB gzipped
- Total: under 200KB for initial load

---

## 5. Dashboard Features for Wildlife Camera System

### Core Features (MVP)

| Feature | Priority | Notes |
|---------|----------|-------|
| Event timeline | P0 | Scrollable list with thumbnails, timestamps, classifications |
| Photo gallery with lightbox | P0 | Click thumbnail to see full-res, swipe between events |
| Classification results | P0 | Animal type badge, confidence percentage, bounding box overlay |
| Battery/power status | P1 | Current voltage, estimated remaining, charging status |
| Camera status | P1 | Online/offline, last heartbeat, connection quality |
| Basic statistics | P1 | Detections today, this week, most common species |

### Enhanced Features (V2)

| Feature | Priority | Notes |
|---------|----------|-------|
| Filtering by animal type | P2 | Dropdown/chips to filter timeline |
| Time-of-day heatmap | P2 | When are animals most active? |
| Configuration UI | P2 | Motion sensitivity, capture resolution, detection confidence threshold |
| Live camera feed | P2 | MJPEG or WebRTC stream (high bandwidth, use sparingly) |
| Push notifications | P1 | Notify on rare/interesting species |
| Multi-camera view | P3 | If multiple Pi Zeros deployed |
| Export/download | P3 | Download selected images or date range |
| Detection map | P3 | If GPS data available, show detection locations |

### Data Model (API endpoints)

```
GET  /api/events?limit=50&offset=0&animal_type=deer&date_from=2026-06-01
GET  /api/events/{event_id}
GET  /api/events/{event_id}/image  (full-res)
GET  /api/events/{event_id}/thumbnail
GET  /api/stats/daily
GET  /api/stats/species
GET  /api/status/battery
GET  /api/status/camera
GET  /api/config
PUT  /api/config
WS   /ws/events  (real-time event stream)
```

---

## 6. Grafana as an Alternative

### What Grafana Does Well

- **Time-series visualization** — excellent for battery levels, detection counts over time, temperature
- **Alerting** — built-in alert rules with notification channels (email, Slack, webhook, ntfy)
- **Pre-built panels** — stat, gauge, bar chart, heatmap, table
- **Image rendering** — can display images in table panels using URL fields
- **Low maintenance** — mature software, declarative dashboards via JSON

### Limitations for This Use Case

- **Image gallery is poor** — no native lightbox, no image browsing experience; images in table cells are tiny
- **No event detail view** — can't click a detection to see full-size image with bounding boxes
- **Classification display** — can show as text in tables but no rich visual overlay
- **Mobile experience** — Grafana mobile is acceptable for viewing charts but clunky for image-heavy content
- **Configuration UI** — not designed for two-way interaction (viewing settings is fine, changing them requires external mechanisms)
- **Resource usage** — Grafana + InfluxDB/Prometheus uses 300-500MB RAM on Pi 5

### Hybrid Approach (Recommended)

Use Grafana for **monitoring and alerting** alongside a custom dashboard for **browsing events**:

- **Grafana handles:** battery trends, detection frequency graphs, system health, uptime monitoring, alert rules
- **Custom dashboard handles:** image browsing, event timeline, classification results, configuration

This is actually aligned with your existing architecture (README shows InfluxDB + Grafana for health metrics).

### Verdict

**Grafana alone is insufficient** for an image-heavy wildlife dashboard but is **excellent as a complement** for system monitoring and alerting. Keep it for metrics; build a lightweight custom UI for event browsing.

---

## 7. Push Notifications

### Comparison

| Service | Setup Effort | Cost | Features | Mobile App | Self-hosted |
|---------|-------------|------|----------|------------|-------------|
| **ntfy.sh** | Very low | Free (public) | Images, actions, priorities | Android + iOS | Yes |
| **Pushover** | Low | $5 one-time | Rich, reliable, 10k msgs/mo | Android + iOS | No |
| **Telegram Bot** | Medium | Free | Images, buttons, groups | Yes | No |
| **Email** | Low | Free (with SMTP) | Universal | Yes | N/A |
| **Browser Push (Web Push API)** | Medium-High | Free | Only when browser open | N/A | Yes |

### Recommendation: ntfy.sh

**ntfy is the clear winner** for this project:

1. **Simplest integration** — single HTTP POST from Python:
```python
import httpx

async def notify_detection(event):
    await httpx.post(
        "https://ntfy.sh/piwatcher-alerts",
        headers={
            "Title": f"{event.animal_type} detected!",
            "Priority": "high" if event.is_rare else "default",
            "Tags": "camera,deer" if event.animal_type == "deer" else "camera",
            "Attach": f"https://piwatcher.yourdomain.com/api/events/{event.id}/thumbnail",
            "Click": f"https://piwatcher.yourdomain.com/events/{event.id}",
        },
        content=f"Confidence: {event.confidence:.0%} at {event.timestamp}",
    )
```

2. **Image attachments** — can attach the detection thumbnail directly in the notification
3. **Action buttons** — "View Event" button that opens the dashboard
4. **Self-hostable** — if you want privacy, run ntfy on the Pi 5 itself (Docker image available)
5. **Free tier** — 250 messages/day on ntfy.sh public server (plenty for wildlife detections)
6. **No app lock-in** — works via web app, Android app, iOS app, or curl

### ntfy Self-hosted on Pi 5

```yaml
# docker-compose addition
services:
  ntfy:
    image: binwiederhier/ntfy
    command: serve
    ports:
      - "8080:80"
    volumes:
      - ./ntfy/cache:/var/cache/ntfy
      - ./ntfy/etc:/etc/ntfy
    restart: unless-stopped
```

Then configure Cloudflare Tunnel to expose `ntfy.yourdomain.com` → `http://localhost:8080`.

### Alternative: Pushover

If you want rock-solid reliability and don't mind the $5 one-time fee:
```python
import httpx

async def notify_via_pushover(event):
    await httpx.post("https://api.pushover.net/1/messages.json", data={
        "token": "YOUR_APP_TOKEN",
        "user": "YOUR_USER_KEY",
        "title": f"{event.animal_type} detected!",
        "message": f"Confidence: {event.confidence:.0%}",
        "url": f"https://piwatcher.yourdomain.com/events/{event.id}",
        "priority": 1 if event.is_rare else 0,
    })
```

---

## Summary & Recommendations

### Architecture Decision

| Component | Recommendation | Reason |
|-----------|---------------|--------|
| **Dashboard framework** | htmx + Jinja2 + TailwindCSS (or React+Vite if you want SPA) | Minimal dependencies, stays in Python ecosystem, mobile-friendly |
| **Remote access** | Cloudflare Tunnel (free tier) | Zero port forwarding, auto SSL, built-in auth via Access |
| **Authentication** | Cloudflare Access (OTP or Google OAuth) | Zero code changes needed, enterprise-grade security |
| **Monitoring/metrics** | Grafana (keep existing) | Already in your stack, excellent for time-series |
| **Event browsing** | Custom lightweight dashboard | Grafana can't do image galleries well |
| **Push notifications** | ntfy.sh (or self-hosted ntfy) | Simplest integration, image support, free |
| **Serving** | FastAPI serves both API + static frontend | Single port, single Cloudflare Tunnel ingress rule |

### Recommended Development Path

1. **Phase 1 (MVP):** FastAPI API endpoints for events + htmx/Jinja2 dashboard with TailwindCSS. Expose via Cloudflare Tunnel with Access auth.
2. **Phase 2:** Add ntfy notifications for detections. Add basic statistics page.
3. **Phase 3:** If htmx hits limitations, migrate to React+Vite SPA (API stays the same). Add configuration UI.
4. **Phase 4:** Live camera feed option, multi-camera support.

---

## References

- Cloudflare Tunnel docs: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- Cloudflare Tunnel create: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/
- cloudflared downloads (ARM64 for Pi 5): https://github.com/cloudflare/cloudflared/releases
- Cloudflare Zero Trust free plan: includes tunnels, 50 users, Access policies
- ntfy.sh documentation: https://docs.ntfy.sh/
- ntfy publishing API: https://docs.ntfy.sh/publish/
- Streamlit deployment: https://docs.streamlit.io/deploy/tutorials/kubernetes
- htmx documentation: https://htmx.org/docs/
- Vite: https://vitejs.dev/
- TailwindCSS: https://tailwindcss.com/

---

## Follow-on Questions (for further research if needed)

- What ML model will be used for classification? (affects whether inference runs on Pi Zero or Pi 5)
- Will the Pi Zero send raw images or pre-classified events to the Pi 5?
- How many events per day are expected? (affects database choice and pagination strategy)
- Is there existing InfluxDB data that should be displayed in the custom dashboard?
- Do you want the dashboard to work offline/cached when tunnel is unavailable?
