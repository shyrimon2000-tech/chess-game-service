import json
import os
import time

BASE = 'http://localhost:8080'

_TIMES_FILE = os.path.join(os.path.dirname(__file__), '.reg_times.json')
_LIMIT = 5
_WINDOW = 60


def _load():
    try:
        with open(_TIMES_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return []


def _save(times):
    with open(_TIMES_FILE, 'w') as f:
        json.dump(times, f)


def reg(page, user):
    now = time.time()
    times = [t for t in _load() if now - t < _WINDOW]
    if len(times) >= _LIMIT:
        wait = _WINDOW - (now - times[0]) + 1
        print(f'  waiting {wait:.0f}s to clear rate limit window...')
        time.sleep(wait)
    page.goto(BASE)
    page.click("button[data-tab='register']")
    page.wait_for_selector('#tab-register.active', timeout=3000)
    page.fill('#reg-username', user['username'])
    page.fill('#reg-email', user['email'])
    page.fill('#reg-password', user['password'])
    page.click("#register-form button[type='submit']")
    try:
        page.wait_for_url('**/rooms.html', timeout=15000)
    except Exception:
        # user likely already exists — fall back to login
        page.goto(BASE)
        page.fill('#login-email', user['email'])
        page.fill('#login-password', user['password'])
        page.click("#login-form button[type='submit']")
        page.wait_for_url('**/rooms.html', timeout=15000)
    times.append(time.time())
    _save(times)
