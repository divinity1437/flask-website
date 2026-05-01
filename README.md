# osu! Web Toolkit

**Personal learning project** — a web tool for osu! players to inspect profiles (both on official Bancho and private Okayu server) and analyze replay files (.osr) using Circleguard.

> **No license, no warranty.** This is a private project created for self-education. Feel free to explore but use at your own risk.

---

## 🎯 Features (implemented)

### 🔍 Profile Inspector
- Search by username or user ID
- Two server backends:
  - **Bancho** – official osu! API v2
  - **Okayu** – private server (includes Relax / Autopilot sub‑modes)
- Game modes: osu!, Taiko, Catch, Mania
- Displays:
  - Avatar, cover banner, country flag, online status (Okayu only)
  - PP, global rank, accuracy, playcount, country rank & level (where available)
- Top 5 scores with **modal detail view** – shows:
  - PP, score, accuracy, mods
  - Hit counts (300/100/50/miss)
  - Max combo, beatmap background, direct beatmap download link

### 📊 Replay Analysis (Circleguard)
- Upload `.osr` files (drag & drop or file picker)
- Extracted metrics:
  - **Unstable Rate (UR)** – highlighted if suspicious
  - **Average frame time** + coefficient of variation (CV)
  - **Snaps** – suspicious cursor jumps (angle/distance)
- Visualisation:
  - Snaps display as a scatter plot (angle vs distance)
  - Snaps table with severity colouring (critical / warning / normal)
- Export results to PDF

### 🔐 osu! OAuth (Bancho)
- Login with your osu! account
- One‑click “Show my profile” after login

---

## 📦 Tech Stack

| Component        | Technologies |
|------------------|--------------|
| Backend          | Python 3.9, Flask, Circleguard (circlecore) |
| Frontend         | HTML5, CSS3, JavaScript, Bootstrap 5 + custom CSS |
| Charts           | Chart.js (scatter plot for snaps) |
| APIs             | osu! API v2 (OAuth client_credentials), Okayu private API |
| HTTP server      | Nginx + Gunicorn (production) / Flask dev server |

---

## 🧱 Project Structure
------

flask-website/
```bash

├── app.py 
├── .env 
├── routes/ 
│ ├── home.py 
│ ├── inspector.py 
│ ├── circleguard.py 
│ └── auth.py 
├── templates/ 
│ ├── base.html 
│ ├── inspector.html 
│ ├── circleguard.html 
│ └── circleguard-upload.html 
├── static/ 
│ ├── css/ 
│ ├── js/ 
│ └── uploads/ (temporary) 
└── requirements.txt

```
------

## 🚀 Quick Start (development)

```bash
# Clone the repository
git clone https://github.com/divinity1437/flask-website.git
cd flask-website

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables (create .env file)
cp .env.example .env
# Edit .env with your keys:
#   OSU_CLIENT_ID, OSU_CLIENT_SECRET, SECRET_KEY
#   Circleguard=your_circleguard_key

# Run the app
python app.py
# Then open http://localhost:5120

```
For production use Gunicorn (or Waitress) behind a reverse proxy like Nginx.

### 🗺️ Environment Variables (.env)

| Variable | Description | Required |
|----------|-------------|----------|
| `OSU_CLIENT_ID` | OAuth app ID from osu! | ✅ Yes (for Bancho API / OAuth) |
| `OSU_CLIENT_SECRET` | OAuth app secret | ✅ Yes (for Bancho API / OAuth) |
| `SECRET_KEY` | Flask session secret | ✅ Yes |
| `Circleguard` | API key for Circleguard | ⚠️ Only if using replay analysis |

> **Note:** `Circleguard` is optional – replay analysis will still work but may have limited features without it.

### 📌 TODO (future ideas)

- [ ] Replay visualizer (web‑based) – integrate a lightweight replay playback view
- [ ] Detailed beatmap stats inside modal windows
- [ ] Caching API (Redis?)

### ⚠️ License & Status

No license. This repository is exclusively for my personal learning. It is not open‑source in the traditional sense — you may read the code for educational purposes, but you are not granted permission to redistribute, host, or use it commercially.

### The project is under active development and may change without notice.
🙏 Credits

------

- [CircleGuard](https://github.com/circleguard/circleguard) | Replay analysis backend
- [osu!Okayu](https://okayu.click) | Private osu! server & API
- [osu!bancho](https://osu.ppy.sh) | Our beauty and wonder game that we love <3


Made for fun and learning.
