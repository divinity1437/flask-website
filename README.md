# Flask Website

A Flask-based web application showcasing **osu! profile inspector** and **Circleguard replay analysis** features. This project can serve as a learning resource or a foundation for building more advanced Flask applications.

---

## Features

- **osu! Profile Inspector**
  - Search for osu! player profiles by username.
  - View statistics such as PP, rank, accuracy, play count, and country flag.
  - Supports all osu! game modes (osu!, Taiko, Catch the Beat, Mania).

- **Circleguard Replay Analysis**
  - Upload `.osr` replay files for analysis.
  - Provides statistics like UR (Unstable Rate), frame times, snaps, mods, and score.
  - Highlights suspicious values with color-coded tables (danger/warning/ok).

---

## TODO

- [ ] Add user authentication via **osu!okayu** to download scores.
- [ ] Implement osu! API caching for faster user lookups
- [ ] Add detailed stats visualization (charts/graphs)
- [ ] Improve error handling for API failures
- [ ] Add support for additional osu! mods and modes

### UI/UX
- [ ] Make the navbar responsive for mobile devices
- [ ] Add dark mode support
- [ ] Improve file upload button styling
- [ ] Enhance card layouts for inspector and Circleguard results
- [ ] Display charts for UR, frametime, and snaps

### Performance
- [ ] Optimize database queries for Circleguard library
- [ ] Add caching layer for repeated beatmap/replay lookups
- [ ] Reduce page load time for heavy replay analysis

### Documentation
- [ ] Add more examples in README
- [ ] Document all routes and template usage
- [ ] Provide troubleshooting section for common errors

### Deployment
- [ ] Configure environment variables for API keys
- [ ] Setup production-ready server configuration
- [ ] Add automated deployment scripts

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/divinity1437/flask-website.git
   cd flask-website
2. **Create a virtual environment
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux / macOS
   venv\Scripts\activate     # Windows
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
4. **Set environment variables**
   Create a .env file (based on .env.example) with your configuration, e.g.:
   ```bash
   Circleguard=YOUR_OSU_API_KEY

---

## Usage

1. **Run the Flask app**
   ```bash
   python app.py

2. **Access the app**
Open your browser at http://127.0.0.1:5000

3. **Available routes**
   - /inspector – osu! profile inspector.
   - /circleguard – upload and analyze .osr replay files.
   - / - Home page.
  
## Project Structure

```csharp
  flask-website/
  ├─ app.py
  ├─ routes/
  │  ├─ inspector.py
  │  └─ circleguard.py
  ├─ templates/
  │  ├─ base.html
  │  ├─ inspector.html
  │  ├─ circleguard.html
  │  └─ circleguard-upload.html
  ├─ static/
  │  ├─ css/
  │  │  ├─ base.css
  │  │  └─ circleguard.css
  │  └─ fonts/
  ├─ uploads/  # Stores uploaded .osr files temporarily
  ├─ requirements.txt
  └─ .env.example
