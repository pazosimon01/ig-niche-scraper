#!/usr/bin/env python3
"""IG Niche Scraper - Web UI + Selenium backend"""
import http.server
import json
import threading
import time
import os
import shutil
import tempfile
import re
import random
import webbrowser
import socketserver
from urllib.parse import parse_qs, urlparse

PORT = 9876

EXCLUDED = {
    'explore', 'reels', 'direct', 'accounts', 'stories', 'reel', 'p',
    'inbox', 'popular', 'locations', 'web', 'legal', 'about', 'help',
    'terms', 'privacy', 'lite', 'blog', 'careers', 'nometapolygon',
    'meta_verified', 'tags', 'developer', 'session', 'emails', 'directory'
}

HASHTAGS = [
    # Emprendimiento
    'emprendimiento', 'emprendedor', 'emprendedores', 'negociosonline',
    'negociosdigitales', 'negociopropio', 'emprendedoreslatinos',
    'emprendedorescolombianos', 'emprendimientodigital', 'startuplatam',
    'mundoemprendedor', 'vidadeemprendedor', 'emprendedoresexitosos',
    # Dinero y finanzas
    'dinero', 'hacerdinero', 'ganardinero', 'libertadfinanciera',
    'finanzaspersonales', 'educacionfinanciera', 'ingresosonline',
    'ingresospasivos', 'riqueza', 'abundancia', 'inversionista',
    'invertirenbolsa', 'criptomonedas', 'tradingforex',
    # Motivación y mentalidad
    'motivacion', 'motivacionpersonal', 'motivaciondiaria',
    'mentalidadmillonaria', 'mentalidaddeexito', 'mentalidadganadora',
    'mindsetemprendedor', 'mindsetmillonario', 'desarrollopersonal',
    'superacionpersonal', 'crecimientopersonal', 'disciplina',
    # Marketing y ventas
    'marketingdigital', 'marketingonline', 'ventasonline',
    'marcapersonal', 'brandingpersonal', 'socialmedamarketing',
    'funneldeventas', 'copywriting', 'ecommerce',
    # Masculinidad y lifestyle
    'motivacionmasculina', 'masculinidad', 'hombredealto valor',
    'highvalueman', 'estoicismo', 'redpill', 'sigmamale',
    'hustle', 'grindset', 'grinding', 'selfimprovement',
    # Liderazgo y éxito
    'exito', 'exitoso', 'liderazgo', 'lider', 'ceo', 'founder',
    'productividad', 'habitosexitosos', 'metasyobjetivos',
    # English variants for broader reach
    'entrepreneur', 'entrepreneurlife', 'entrepreneurmindset',
    'makemoney', 'moneymindset', 'sidehustle', 'passiveincome',
    'wealthbuilding', 'financialfreedom', 'motivation',
    'successmindset', 'millionairemindset', 'businessowner',
]

HISTORY_FILE = os.path.expanduser("~/.ig_scraper_history.json")

state = {
    'running': False,
    'profiles': [],
    'count': 0,
    'target': 100,
    'status': 'Listo para iniciar',
    'hashtag': '',
}
driver_ref = {'driver': None, 'tmp': None}


def load_history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()


def save_history(profiles):
    existing = load_history()
    existing.update(profiles)
    # Keep last 5000 to avoid infinite growth
    trimmed = list(existing)[-5000:]
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(trimmed, f)
    except:
        pass


def scrape_thread(target):
    global state
    state['running'] = True
    state['profiles'] = []
    state['count'] = 0
    state['target'] = target
    tmp_profile = None

    history = load_history()

    try:
        state['status'] = 'Preparando Chrome...'
        src = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        tmp_profile = tempfile.mkdtemp(prefix="ig_scraper_")
        driver_ref['tmp'] = tmp_profile
        default_src = os.path.join(src, "Default")
        default_dst = os.path.join(tmp_profile, "Default")
        os.makedirs(default_dst, exist_ok=True)
        for item in ["Cookies", "Login Data", "Web Data", "Preferences",
                      "Secure Preferences", "Local State", "Network"]:
            s = os.path.join(default_src, item)
            d = os.path.join(default_dst, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            elif os.path.exists(s):
                shutil.copy2(s, d)
        ls = os.path.join(src, "Local State")
        if os.path.exists(ls):
            shutil.copy2(ls, tmp_profile)

        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={tmp_profile}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")

        state['status'] = 'Abriendo Chrome...'
        driver = uc.Chrome(options=options, version_main=None)
        driver_ref['driver'] = driver
        driver.set_window_size(1200, 900)

        state['status'] = 'Navegando a Instagram...'
        driver.get("https://www.instagram.com/")
        time.sleep(3)

        own_user = None
        try:
            link = driver.execute_script("""
                const a = document.querySelector('a[href*="/"][role="link"] img[alt]');
                if (a) { const l = a.closest('a'); if (l) return l.getAttribute('href'); }
                return null;
            """)
            if link:
                m = re.match(r'^/([a-zA-Z0-9_.]+)/?$', link)
                if m:
                    own_user = m.group(1).lower()
        except:
            pass

        collected = set()
        skip = EXCLUDED | history | ({own_user} if own_user else set())

        # Shuffle hashtags so each run explores different ones
        tags = list(HASHTAGS)
        random.shuffle(tags)
        tag_index = 0

        while len(collected) < target and state['running']:
            if tag_index >= len(tags):
                # Reshuffle and go again
                random.shuffle(tags)
                tag_index = 0

            tag = tags[tag_index]
            tag_index += 1

            state['hashtag'] = tag
            state['status'] = f'Buscando en #{tag}...'
            print(f"[scrape] Visiting #{tag}")

            driver.get(f"https://www.instagram.com/explore/tags/{tag}/")
            time.sleep(3)

            # Scroll to load more posts
            for _ in range(5):
                if not state['running']:
                    break
                driver.execute_script("window.scrollBy(0, window.innerHeight)")
                time.sleep(0.7)

            try:
                post_links = driver.execute_script("""
                    return Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
                        .map(a => a.getAttribute('href'))
                        .filter((v,i,a) => a.indexOf(v) === i);
                """) or []
            except:
                post_links = []

            if not post_links:
                print(f"[scrape] #{tag}: no posts found, skipping")
                continue

            # Shuffle posts to avoid always hitting the same ones
            random.shuffle(post_links)
            state['status'] = f'#{tag}: {len(post_links)} posts, scrapeando...'
            print(f"[scrape] #{tag}: {len(post_links)} posts")

            # Open first post
            driver.get("https://www.instagram.com" + post_links[0])
            time.sleep(2)

            stale = 0
            for post_idx in range(len(post_links)):
                if len(collected) >= target or not state['running']:
                    break

                # Extract ALL usernames from the current page
                new_users = extract_all_usernames(driver, skip)
                added = 0
                for u in new_users:
                    if u not in collected and len(collected) < target:
                        collected.add(u)
                        state['profiles'].append(u)
                        added += 1

                state['count'] = len(collected)

                if added > 0:
                    stale = 0
                    state['status'] = f'#{tag}: {len(collected)}/{target} (+{added})'
                    print(f"[scrape] #{tag} post {post_idx}: +{added} = {len(collected)}")
                else:
                    stale += 1

                if stale > 5:
                    break

                # Navigate to next post via "Next" button
                if not click_next(driver):
                    # Try opening the next post directly
                    if post_idx + 1 < len(post_links):
                        driver.get("https://www.instagram.com" + post_links[post_idx + 1])
                        time.sleep(1.5)
                    else:
                        break
                else:
                    time.sleep(0.5)

        # Save to history
        save_history(collected)

        state['status'] = f'Completado: {len(collected)} perfiles únicos'
        print(f"[done] {len(collected)} profiles")

    except Exception as e:
        print(f"[error] {e}")
        state['status'] = f'Error: {str(e)[:100]}'
    finally:
        state['running'] = False
        if driver_ref['driver']:
            try:
                driver_ref['driver'].quit()
            except:
                pass
            driver_ref['driver'] = None
        if tmp_profile and os.path.exists(tmp_profile):
            shutil.rmtree(tmp_profile, ignore_errors=True)


def extract_all_usernames(driver, skip):
    try:
        raw = driver.execute_script("""
            const out = new Set();
            // Author from header
            document.querySelectorAll('header a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            // All profile links
            document.querySelectorAll('a[role="link"][href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            // Comment authors
            document.querySelectorAll('ul a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            // Catch-all
            document.querySelectorAll('a[href^="/"]').forEach(a => {
                const m = a.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                if (m) out.add(m[1].toLowerCase());
            });
            return [...out];
        """)
        return [u for u in (raw or []) if u not in skip]
    except Exception as e:
        print(f"[extract] error: {e}")
        return []


def click_next(driver):
    try:
        clicked = driver.execute_script("""
            const labels = ['Siguiente', 'Next', 'Próximo', 'Avançar'];
            for (const label of labels) {
                const svg = document.querySelector(`svg[aria-label="${label}"]`);
                if (svg) {
                    const btn = svg.closest('button') || svg.closest('[role="button"]') || svg;
                    btn.click();
                    return true;
                }
                const el = document.querySelector(`[aria-label="${label}"]`);
                if (el) {
                    const btn = el.closest('button') || el;
                    btn.click();
                    return true;
                }
            }
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


# ── HTML ──
HTML_PAGE = '''<!DOCTYPE html>
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
.btn-clear { padding: 14px; border: 2px solid #6b2d2d; border-radius: 10px; background: transparent; color: #e74c3c; font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.btn-clear:hover { background: #6b2d2d; color: #fff; }
.toast { position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); background: #00ff88; color: #000; padding: 12px 24px; border-radius: 8px; font-weight: 700; display: none; z-index: 999; }
.history-info { text-align: center; color: #444; font-size: 11px; margin-top: 8px; }
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
        <button class="btn-clear" onclick="clearHistory()">LIMPIAR HISTORIAL</button>
    </div>
    <div class="history-info" id="historyInfo"></div>
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

fetch('/history_count').then(r=>r.json()).then(d => {
    if (d.count > 0) document.getElementById('historyInfo').textContent =
        d.count + ' perfiles en historial (no se repetiran)';
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
            fetch('/history_count').then(r=>r.json()).then(d => {
                document.getElementById('historyInfo').textContent =
                    d.count + ' perfiles en historial (no se repetiran)';
            });
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

function clearHistory() {
    if (confirm('Borrar historial? Esto permite volver a encontrar perfiles anteriores.')) {
        fetch('/clear_history').then(() => {
            document.getElementById('historyInfo').textContent = 'Historial limpiado';
            showToast('Historial borrado');
        });
    }
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 2500);
}
</script>
</body>
</html>'''


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

        elif path == '/start':
            amount = int(params.get('amount', [100])[0])
            if not state['running']:
                threading.Thread(target=scrape_thread, args=(amount,), daemon=True).start()
            self._json({'ok': True})

        elif path == '/stop':
            state['running'] = False
            self._json({'ok': True})

        elif path == '/status':
            self._json({
                'running': state['running'],
                'count': state['count'],
                'target': state['target'],
                'status': state['status'],
                'hashtag': state.get('hashtag', ''),
                'profiles': state['profiles'],
            })

        elif path == '/history_count':
            self._json({'count': len(load_history())})

        elif path == '/clear_history':
            try:
                os.remove(HISTORY_FILE)
            except:
                pass
            self._json({'ok': True})

        else:
            self.send_error(404)

    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        print(f"IG Niche Scraper corriendo en http://localhost:{PORT}")
        webbrowser.open(f'http://localhost:{PORT}')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
