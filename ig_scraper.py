#!/usr/bin/env python3
"""IG Niche Scraper - Web UI + Selenium backend"""
import http.server
import json
import threading
import time
import os
import re
import shutil
import tempfile
import socketserver
from urllib.parse import urlparse, parse_qs

# ── Config ──
PORT = 9876
HASHTAGS = ["emprendimiento", "motivacion", "dinero"]

EXCLUDED = {
    'explore', 'reels', 'direct', 'accounts', 'stories', 'reel', 'p',
    'inbox', 'popular', 'locations', 'web', 'legal', 'about', 'help',
    'terms', 'privacy', 'lite', 'blog', 'careers', 'nometapolygon',
    'meta_verified', 'tags', 'developer', 'session', 'emails', 'directory',
}

# ── Shared state ──
state = {
    "running": False,
    "count": 0,
    "target": 100,
    "status": "Listo para iniciar",
    "hashtag": "",
    "profiles": [],
    "error": "",
}
state_lock = threading.Lock()
scrape_thread = None
driver_ref = [None]


def update_state(**kw):
    with state_lock:
        state.update(kw)


def get_state():
    with state_lock:
        return dict(state)


# ── Scraping logic ──
def extract_usernames(driver):
    """Pull every /<username>/ link from the current page."""
    try:
        raw = driver.execute_script("""
            const out = new Set();
            document.querySelectorAll('a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            return [...out];
        """)
        return [u for u in (raw or []) if u not in EXCLUDED]
    except Exception as e:
        print(f"[extract] error: {e}")
        return []


def extract_from_post_page(driver):
    """Extract username from a post's detail page via multiple selectors."""
    try:
        raw = driver.execute_script("""
            const out = new Set();
            // Method 1: header links (post author)
            document.querySelectorAll('header a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            // Method 2: all profile links with role=link
            document.querySelectorAll('a[role="link"][href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            // Method 3: comment authors
            document.querySelectorAll('ul a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            // Method 4: any <a> matching username pattern
            document.querySelectorAll('a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            return [...out];
        """)
        return [u for u in (raw or []) if u not in EXCLUDED]
    except Exception as e:
        print(f"[extract_post] error: {e}")
        return []


def scrape_hashtag_page(driver, hashtag, collected, target):
    """Scrape profiles from a hashtag's explore page."""
    update_state(status=f"Cargando #{hashtag}...", hashtag=hashtag)
    url = f"https://www.instagram.com/explore/tags/{hashtag}/"
    driver.get(url)
    time.sleep(3)

    # Scroll to load more posts
    for i in range(5):
        if not state["running"] or len(collected) >= target:
            return
        driver.execute_script("window.scrollBy(0, window.innerHeight)")
        time.sleep(0.8)

    # Get all post links
    post_links = driver.execute_script("""
        return Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
            .map(a => a.getAttribute('href'))
            .filter((v,i,a) => a.indexOf(v) === i);
    """) or []

    update_state(status=f"#{hashtag}: {len(post_links)} posts encontrados")
    print(f"[{hashtag}] Found {len(post_links)} posts")

    if not post_links:
        return

    # Open first post
    driver.get("https://www.instagram.com" + post_links[0])
    time.sleep(2)

    visited = 0
    stale = 0

    while len(collected) < target and state["running"]:
        # Extract usernames from current post
        new_users = extract_from_post_page(driver)
        added = 0
        for u in new_users:
            if u not in collected and len(collected) < target:
                collected.add(u)
                added += 1

        if added > 0:
            stale = 0
            with state_lock:
                state["profiles"] = list(collected)
                state["count"] = len(collected)
            update_state(
                status=f"#{hashtag}: {len(collected)}/{target} perfiles (+{added})",
            )
            print(f"[{hashtag}] Post {visited}: +{added} = {len(collected)} total")
        else:
            stale += 1

        visited += 1

        if len(collected) >= target:
            break

        # Click "next" to go to next post
        next_ok = click_next(driver)

        if not next_ok or stale > 8:
            print(f"[{hashtag}] Next failed or stale, trying more posts...")
            # Go back to hashtag page, scroll more, try again
            driver.get(url)
            time.sleep(2)
            for i in range(3 + visited // 3):
                if not state["running"]:
                    return
                driver.execute_script("window.scrollBy(0, window.innerHeight)")
                time.sleep(0.6)

            post_links = driver.execute_script("""
                return Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
                    .map(a => a.getAttribute('href'))
                    .filter((v,i,a) => a.indexOf(v) === i);
            """) or []

            if not post_links:
                break

            # Pick a post we haven't likely visited
            idx = min(visited, len(post_links) - 1)
            driver.get("https://www.instagram.com" + post_links[idx])
            time.sleep(2)
            stale = 0
        else:
            time.sleep(0.6)


def click_next(driver):
    """Click the 'Next' arrow button on a post modal/page."""
    try:
        clicked = driver.execute_script("""
            // Try aria-labels in multiple languages
            const labels = ['Siguiente', 'Next', 'Próximo', 'Avançar'];
            for (const label of labels) {
                // SVG with aria-label
                const svg = document.querySelector(`svg[aria-label="${label}"]`);
                if (svg) {
                    const btn = svg.closest('button') || svg.closest('[role="button"]') || svg;
                    btn.click();
                    return true;
                }
                // Button or div with aria-label
                const el = document.querySelector(`[aria-label="${label}"]`);
                if (el) {
                    const btn = el.closest('button') || el;
                    btn.click();
                    return true;
                }
            }
            // Fallback: right arrow button by position
            const buttons = document.querySelectorAll('button');
            for (const b of buttons) {
                const rect = b.getBoundingClientRect();
                if (rect.right > window.innerWidth * 0.8 && rect.top > 100 && rect.bottom < window.innerHeight - 100) {
                    if (b.querySelector('svg')) {
                        b.click();
                        return true;
                    }
                }
            }
            return false;
        """)
        if clicked:
            time.sleep(0.8)
        return clicked
    except:
        return False


def scrape_explore(driver, collected, target):
    """Fallback: scrape the main Explore grid."""
    update_state(status="Cargando Explorar...", hashtag="explore")
    driver.get("https://www.instagram.com/explore/")
    time.sleep(3)

    for i in range(5):
        if not state["running"]:
            return
        driver.execute_script("window.scrollBy(0, window.innerHeight)")
        time.sleep(0.8)

    post_links = driver.execute_script("""
        return Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
            .map(a => a.getAttribute('href'))
            .filter((v,i,a) => a.indexOf(v) === i);
    """) or []

    if not post_links:
        return

    driver.get("https://www.instagram.com" + post_links[0])
    time.sleep(2)

    for _ in range(len(post_links) * 2):
        if not state["running"] or len(collected) >= target:
            break
        new_users = extract_from_post_page(driver)
        for u in new_users:
            if u not in collected and len(collected) < target:
                collected.add(u)
        with state_lock:
            state["profiles"] = list(collected)
            state["count"] = len(collected)
        update_state(status=f"Explorar: {len(collected)}/{target} perfiles")

        if not click_next(driver):
            break
        time.sleep(0.6)


def run_scraper(target):
    """Main scraping loop."""
    try:
        update_state(running=True, count=0, profiles=[], status="Abriendo Chrome...", error="")

        import undetected_chromedriver as uc

        # Copy Chrome profile to temp dir to avoid conflicts
        update_state(status="Preparando perfil de Chrome...")
        chrome_src = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        tmp_dir = tempfile.mkdtemp(prefix="ig_scraper_")
        default_dst = os.path.join(tmp_dir, "Default")
        os.makedirs(default_dst, exist_ok=True)

        for item in ["Cookies", "Login Data", "Web Data", "Preferences",
                      "Secure Preferences", "Network"]:
            src = os.path.join(chrome_src, "Default", item)
            dst = os.path.join(default_dst, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif os.path.exists(src):
                shutil.copy2(src, dst)

        local_state = os.path.join(chrome_src, "Local State")
        if os.path.exists(local_state):
            shutil.copy2(local_state, tmp_dir)

        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={tmp_dir}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")

        update_state(status="Iniciando Chrome...")
        driver = uc.Chrome(options=options, version_main=None)
        driver_ref[0] = driver
        driver.set_window_size(1200, 900)

        collected = set()

        # Scrape each hashtag
        for hashtag in HASHTAGS:
            if not state["running"] or len(collected) >= target:
                break
            scrape_hashtag_page(driver, hashtag, collected, target)

        # If still not enough, use Explore
        if len(collected) < target and state["running"]:
            scrape_explore(driver, collected, target)

        with state_lock:
            state["profiles"] = list(collected)
            state["count"] = len(collected)

        update_state(
            running=False,
            status=f"Completado: {len(collected)} perfiles únicos",
        )
        print(f"[done] {len(collected)} profiles collected")

    except Exception as e:
        print(f"[error] {e}")
        update_state(running=False, status=f"Error: {str(e)[:120]}", error=str(e))
    finally:
        if driver_ref[0]:
            try:
                driver_ref[0].quit()
            except:
                pass
            driver_ref[0] = None
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Web server ──
HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<title>IG Niche Scraper</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0d0d0d; color: #eee; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif; min-height: 100vh; display: flex; justify-content: center; padding: 30px 20px; }
.app { width: 100%; max-width: 640px; }
h1 { text-align: center; font-size: 32px; font-weight: 800; background: linear-gradient(135deg, #833ab4, #e94560, #fcb045); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 4px; }
.subtitle { text-align: center; color: #555; font-size: 13px; margin-bottom: 24px; letter-spacing: 1px; }
.section { background: #1a1a1a; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
.section-title { font-size: 11px; font-weight: 700; color: #666; letter-spacing: 2px; margin-bottom: 12px; }
.amounts { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
.amt-btn { padding: 14px 0; border: 2px solid #333; border-radius: 10px; background: #222; color: #888; font-size: 16px; font-weight: 700; cursor: pointer; transition: all 0.2s; text-align: center; }
.amt-btn:hover { border-color: #e94560; color: #fff; }
.amt-btn.active { background: #e94560; border-color: #e94560; color: #fff; box-shadow: 0 0 20px rgba(233,69,96,0.3); }
.selected-label { text-align: center; margin-top: 12px; font-size: 14px; color: #e94560; font-weight: 600; }
.actions { display: flex; gap: 10px; margin-bottom: 16px; }
.btn-start { flex: 2; padding: 16px; border: none; border-radius: 12px; background: linear-gradient(135deg, #e94560, #c0392b); color: white; font-size: 17px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.btn-start:hover { transform: scale(1.02); box-shadow: 0 4px 20px rgba(233,69,96,0.4); }
.btn-start:disabled { opacity: 0.4; cursor: not-allowed; transform: none; box-shadow: none; }
.btn-stop { flex: 1; padding: 16px; border: 2px solid #444; border-radius: 12px; background: transparent; color: #999; font-size: 17px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.btn-stop:hover { border-color: #888; color: #fff; }
.counter-box { text-align: center; padding: 20px; }
.counter { font-size: 64px; font-weight: 800; color: #00ff88; font-variant-numeric: tabular-nums; }
.counter span { color: #333; font-size: 40px; }
.status { color: #666; font-size: 13px; margin-top: 6px; }
.hashtag-badge { display: inline-block; background: #1a1a2e; color: #833ab4; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-top: 6px; }
.progress-bar { width: 100%; height: 4px; background: #222; border-radius: 2px; margin-top: 12px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #e94560, #fcb045); border-radius: 2px; transition: width 0.3s; width: 0%; }
.results-header { display: flex; justify-content: space-between; align-items: center; }
.results-list { background: #0a0a0a; border-radius: 8px; padding: 12px 16px; margin-top: 10px; max-height: 280px; overflow-y: auto; font-family: 'Menlo', 'Monaco', monospace; font-size: 13px; color: #00ff88; line-height: 1.8; min-height: 60px; white-space: pre; }
.results-list::-webkit-scrollbar { width: 6px; }
.results-list::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
.bottom-actions { display: flex; gap: 10px; margin-top: 16px; }
.btn-copy, .btn-save { flex: 1; padding: 14px; border: 2px solid #1a5276; border-radius: 10px; background: transparent; color: #3498db; font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.btn-copy:hover, .btn-save:hover { background: #1a5276; color: #fff; }
.toast { position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); background: #00ff88; color: #000; padding: 12px 24px; border-radius: 8px; font-weight: 700; display: none; z-index: 999; }
</style>
</head>
<body>
<div class="app">
    <h1>IG NICHE SCRAPER</h1>
    <p class="subtitle">EMPRENDIMIENTO &middot; MOTIVACION &middot; DINERO</p>

    <div class="section">
        <div class="section-title">CANTIDAD DE PERFILES</div>
        <div class="amounts" id="amounts"></div>
        <div class="selected-label" id="selLabel">Seleccionado: 100 perfiles</div>
    </div>

    <div class="actions">
        <button class="btn-start" id="btnStart" onclick="startScrape()">&#9654;  INICIAR SCRAPING</button>
        <button class="btn-stop" id="btnStop" onclick="stopScrape()">&#9724;  DETENER</button>
    </div>

    <div class="section">
        <div class="counter-box">
            <div class="counter" id="counter">0 <span>/ 100</span></div>
            <div class="status" id="status">Listo para iniciar</div>
            <div id="hashBadge"></div>
            <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
        </div>
    </div>

    <div class="section">
        <div class="results-header">
            <div class="section-title">PERFILES ENCONTRADOS</div>
            <div id="resultCount" style="color:#00ff88;font-size:13px;font-weight:700">0</div>
        </div>
        <div class="results-list" id="resultsList">Aqui apareceran los perfiles...</div>
    </div>

    <div class="bottom-actions">
        <button class="btn-copy" onclick="copyAll()">COPIAR TODO</button>
        <button class="btn-save" onclick="saveFile()">GUARDAR .TXT</button>
    </div>
</div>
<div class="toast" id="toast"></div>

<script>
let selectedAmount = 100;
let polling = null;
const amounts = [50, 100, 200, 300, 500, 1000];

const amountsDiv = document.getElementById('amounts');
amounts.forEach(amt => {
    const btn = document.createElement('div');
    btn.className = 'amt-btn' + (amt === 100 ? ' active' : '');
    btn.textContent = amt;
    btn.onclick = () => selectAmount(amt);
    btn.id = 'amt-' + amt;
    amountsDiv.appendChild(btn);
});

function selectAmount(amt) {
    selectedAmount = amt;
    amounts.forEach(a => {
        document.getElementById('amt-' + a).className = 'amt-btn' + (a === amt ? ' active' : '');
    });
    document.getElementById('selLabel').textContent = 'Seleccionado: ' + amt + ' perfiles';
    document.getElementById('counter').innerHTML = '0 <span>/ ' + amt + '</span>';
}

function startScrape() {
    document.getElementById('btnStart').disabled = true;
    document.getElementById('resultsList').textContent = '';
    document.getElementById('counter').innerHTML = '0 <span>/ ' + selectedAmount + '</span>';
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('resultCount').textContent = '0';

    fetch('/start?amount=' + selectedAmount).then(() => {
        polling = setInterval(pollStatus, 1000);
    });
}

function stopScrape() { fetch('/stop'); }

function pollStatus() {
    fetch('/status').then(r => r.json()).then(data => {
        document.getElementById('counter').innerHTML = data.count + ' <span>/ ' + data.target + '</span>';
        document.getElementById('status').textContent = data.status;
        document.getElementById('resultCount').textContent = data.count;

        const pct = data.target > 0 ? Math.min(Math.round(data.count / data.target * 100), 100) : 0;
        document.getElementById('progressFill').style.width = pct + '%';

        if (data.hashtag) {
            document.getElementById('hashBadge').innerHTML = '<span class="hashtag-badge">#' + data.hashtag + '</span>';
        }

        if (data.profiles && data.profiles.length > 0) {
            document.getElementById('resultsList').textContent = data.profiles.join('\\n');
            document.getElementById('resultsList').scrollTop = document.getElementById('resultsList').scrollHeight;
        }

        if (!data.running && polling) {
            clearInterval(polling);
            polling = null;
            document.getElementById('btnStart').disabled = false;
            if (data.count > 0) showToast('Scraping completado: ' + data.count + ' perfiles');
        }
    }).catch(() => {});
}

function copyAll() {
    fetch('/status').then(r => r.json()).then(data => {
        if (!data.profiles || data.profiles.length === 0) return;
        navigator.clipboard.writeText(data.profiles.join('\\n')).then(() => {
            showToast('Copiados ' + data.profiles.length + ' perfiles');
        });
    });
}

function saveFile() {
    fetch('/status').then(r => r.json()).then(data => {
        if (!data.profiles || data.profiles.length === 0) return;
        const blob = new Blob([data.profiles.join('\\n')], {type: 'text/plain'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'perfiles_nicho_ig.txt';
        a.click();
        showToast('Archivo descargado');
    });
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 2500);
}
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress request logs

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        global scrape_thread
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self._html(HTML)

        elif path == "/status":
            self._json(get_state())

        elif path == "/start":
            if state["running"]:
                self._json({"ok": False, "msg": "already running"})
                return
            target = int(params.get("amount", [100])[0])
            update_state(target=target)
            scrape_thread = threading.Thread(target=run_scraper, args=(target,), daemon=True)
            scrape_thread.start()
            self._json({"ok": True})

        elif path == "/stop":
            update_state(running=False, status="Detenido por el usuario")
            if driver_ref[0]:
                try:
                    driver_ref[0].quit()
                except:
                    pass
                driver_ref[0] = None
            self._json({"ok": True})

        else:
            self.send_error(404)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"IG Niche Scraper corriendo en http://localhost:{PORT}")
    server = ReusableTCPServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
        server.shutdown()
