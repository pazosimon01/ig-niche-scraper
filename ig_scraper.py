#!/usr/bin/env python3
"""IG Niche Scraper - Web UI + Selenium backend"""
import http.server
import json
import threading
import time
import os
import sys
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

        driver_ref['tmp'] = None

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        # Use a dedicated persistent profile — user logs in once, session persists
        scraper_profile = os.path.expanduser("~/.ig_scraper_chrome")

        options = Options()
        options.add_argument(f"--user-data-dir={scraper_profile}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--window-size=1200,900")

        state['status'] = 'Abriendo Chrome...'
        print("[scrape] Launching Chrome with persistent profile...", flush=True)
        driver = webdriver.Chrome(options=options)
        print(f"[scrape] Chrome launched OK", flush=True)

        driver_ref['driver'] = driver

        state['status'] = 'Navegando a Instagram...'
        print("[scrape] Navigating to Instagram...", flush=True)
        driver.get("https://www.instagram.com/")
        time.sleep(5)
        print(f"[scrape] On Instagram, title: {driver.title}", flush=True)

        # Check if logged in — if not, wait for user to log in (up to 3 minutes)
        def check_logged_in():
            try:
                return driver.execute_script("""
                    return document.querySelector('a[href*="/direct/"]') !== null
                        || document.querySelector('svg[aria-label="Inicio"]') !== null
                        || document.querySelector('svg[aria-label="Home"]') !== null
                        || document.querySelector('svg[aria-label="Nueva publicación"]') !== null
                        || document.querySelector('svg[aria-label="New post"]') !== null
                        || document.querySelector('span[aria-label="Inicio"]') !== null;
                """)
            except:
                return False

        is_logged = check_logged_in()
        if is_logged:
            print("[scrape] Already logged in!", flush=True)
        else:
            state['status'] = '⏳ Inicia sesión en Instagram en la ventana de Chrome...'
            print("[scrape] NOT logged in. Waiting for user to log in...", flush=True)
            for wait in range(90):
                if not state['running']:
                    return
                time.sleep(2)
                is_logged = check_logged_in()
                if is_logged:
                    print(f"[scrape] User logged in after {wait*2}s!", flush=True)
                    break
                if wait % 15 == 0 and wait > 0:
                    state['status'] = f'⏳ Esperando login en Chrome... ({180 - wait*2}s restantes)'
            if not is_logged:
                state['status'] = 'Error: no iniciaste sesión en Instagram. Intenta de nuevo.'
                raise Exception("Timeout esperando login de Instagram")

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
                random.shuffle(tags)
                tag_index = 0

            tag = tags[tag_index]
            tag_index += 1

            state['hashtag'] = tag
            state['status'] = f'Buscando en #{tag}...'
            print(f"[scrape] Visiting #{tag}", flush=True)

            driver.get(f"https://www.instagram.com/explore/tags/{tag}/")
            time.sleep(4)

            # Scroll to load more post thumbnails
            for scroll in range(5):
                if not state['running']:
                    break
                driver.execute_script("window.scrollBy(0, window.innerHeight)")
                time.sleep(0.8)

            # Get all post thumbnail links
            post_links = driver.execute_script("""
                return Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
                    .map(a => a.getAttribute('href'))
                    .filter((v,i,a) => a.indexOf(v) === i);
            """) or []

            if not post_links:
                print(f"[scrape] #{tag}: no posts found", flush=True)
                continue

            random.shuffle(post_links)
            print(f"[scrape] #{tag}: {len(post_links)} posts, clicking thumbnails...", flush=True)

            tag_added = 0
            for post_idx, post_href in enumerate(post_links):
                if len(collected) >= target or not state['running']:
                    break

                # Click the thumbnail to open as modal (not navigate)
                try:
                    clicked = driver.execute_script("""
                        var link = document.querySelector('a[href="' + arguments[0] + '"]');
                        if (link) { link.click(); return true; }
                        return false;
                    """, post_href)
                except:
                    clicked = False

                if not clicked:
                    continue

                time.sleep(2)

                # Extract author from the modal
                new_users = extract_post_author(driver, skip)
                added = 0
                for u in new_users:
                    if u not in collected and len(collected) < target:
                        collected.add(u)
                        state['profiles'].append(u)
                        added += 1
                        tag_added += 1

                state['count'] = len(collected)

                if added > 0:
                    state['status'] = f'#{tag}: {len(collected)}/{target} (+{added})'
                    print(f"[scrape] #{tag} post {post_idx}: +{added} = {len(collected)}", flush=True)

                # Close the modal by pressing Escape
                try:
                    from selenium.webdriver.common.keys import Keys
                    driver.find_element("tag name", "body").send_keys(Keys.ESCAPE)
                except:
                    # Fallback: navigate back
                    try:
                        driver.back()
                    except:
                        pass
                time.sleep(1)

            if tag_added == 0:
                print(f"[scrape] #{tag}: no new users found", flush=True)

        # Save to history
        save_history(collected)

        state['status'] = f'Completado: {len(collected)} perfiles únicos'
        print(f"[done] {len(collected)} profiles", flush=True)

    except Exception as e:
        print(f"[error] {e}", flush=True)
        state['status'] = f'Error: {str(e)[:100]}'
    finally:
        state['running'] = False
        if driver_ref['driver']:
            try:
                driver_ref['driver'].quit()
            except:
                pass
            driver_ref['driver'] = None


def extract_post_author(driver, skip):
    try:
        user = driver.execute_script("""
            try {
                // Look inside the modal/dialog first, then fall back to full page
                var scope = document.querySelector('div[role="dialog"]') || document;

                // Method 1: Inside modal — find profile pic alt text
                var imgs = scope.querySelectorAll('img[alt]');
                for (var i = 0; i < imgs.length; i++) {
                    var alt = imgs[i].alt || '';
                    if (alt.indexOf('profile picture') >= 0 || alt.indexOf('Foto del perfil') >= 0) {
                        var name = alt.replace(/foto del perfil de /i, '').replace(/'s profile picture/i, '').replace(/Foto del perfil de /i, '').trim();
                        if (name && /^[a-zA-Z0-9_.]{2,30}$/.test(name)) {
                            var link = imgs[i].closest('a[href^="/"]');
                            if (link) {
                                var hm = link.getAttribute('href').match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                                if (hm) return 'modal-img|' + hm[1].toLowerCase();
                            }
                            return 'modal-alt|' + name.toLowerCase();
                        }
                    }
                }

                // Method 2: Inside modal — first username link
                var links = scope.querySelectorAll('a[href^="/"]');
                for (var j = 0; j < links.length; j++) {
                    var href = links[j].getAttribute('href');
                    if (['/','/reels/','/explore/','/direct/','/accounts/'].indexOf(href) >= 0) continue;
                    if (href.indexOf('/p/') === 0 || href.indexOf('/reel/') === 0 || href.indexOf('/explore/') === 0 || href.indexOf('/stories/') === 0) continue;
                    var lm = href.match(/^\\/([a-zA-Z0-9_.]{2,30})\\/?$/);
                    if (lm) return 'modal-link|' + lm[1].toLowerCase();
                }

                // Method 3: meta tags (work when navigated to a post page)
                var el = document.querySelector('meta[property="og:description"]');
                if (el) {
                    var c = el.getAttribute('content') || '';
                    var m = c.match(/@([a-zA-Z0-9_.]{2,30})/);
                    if (m) return 'og:desc|' + m[1].toLowerCase();
                }
            } catch(e) {}
            return null;
        """)
        if user:
            parts = user.split('|', 1)
            method = parts[0]
            username = parts[1] if len(parts) > 1 else user
            print(f"[extract] OK method={method} user={username}", flush=True)
            if username not in skip:
                return [username]
            else:
                print(f"[extract] {username} in skip set", flush=True)
        else:
            print(f"[extract] FAIL - returned null", flush=True)
        return []
    except Exception as e:
        print(f"[extract] error: {e}", flush=True)
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
    <p style="text-align:center;color:#fcb045;font-size:12px;margin-bottom:8px">La primera vez: inicia sesion en Instagram en el Chrome que se abra. Despues ya no sera necesario.</p>

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

        elif path == '/debug':
            if driver_ref['driver']:
                try:
                    info = driver_ref['driver'].execute_script("""
                        return {
                            url: window.location.href,
                            title: document.title,
                            bodyLen: document.body ? document.body.innerHTML.length : 0,
                            metas: Array.from(document.querySelectorAll('meta[property]')).slice(0,10).map(m => m.getAttribute('property') + '=' + (m.getAttribute('content')||'').substring(0,80)),
                            imgs: Array.from(document.querySelectorAll('img[alt]')).slice(0,10).map(i => i.alt.substring(0,60)),
                            links: Array.from(document.querySelectorAll('a[href^="/"]')).slice(0,15).map(a => a.getAttribute('href')),
                        };
                    """)
                    self._json(info)
                except Exception as e:
                    self._json({'error': str(e)})
            else:
                self._json({'error': 'no driver'})

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
        print(f"IG Niche Scraper corriendo en http://localhost:{PORT}", flush=True)
        webbrowser.open(f'http://localhost:{PORT}')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
