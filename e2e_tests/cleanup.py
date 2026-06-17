import json
import os
import subprocess

COMPOSE_DIR = os.environ.get(
    'E2E_COMPOSE_DIR',
    os.path.join(os.path.dirname(__file__), '..'),
)


def _exec(service, code):
    result = subprocess.run(
        ['docker', 'compose', '--env-file', '.env.combined', '-f', 'docker-compose.e2e.yml', 'exec', '-T', service, 'python', '-c', code],
        cwd=COMPOSE_DIR, capture_output=True, text=True
    )
    return result.stdout.strip()


def cleanup(suffix):
    """Delete rooms and games created by test users with the given suffix."""
    output = _exec('chess-room-service', f'''
import json
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
rows = db.execute(text("SELECT game_id FROM rooms WHERE white_player_nickname LIKE \'%{suffix}%\'")).fetchall()
game_ids = [r[0] for r in rows if r[0] is not None]
r = db.execute(text("DELETE FROM rooms WHERE white_player_nickname LIKE \'%{suffix}%\'"))
db.commit()
db.close()
print(json.dumps({{"rooms": r.rowcount, "game_ids": game_ids}}))
''')
    try:
        data = json.loads(output)
        rooms_n = data['rooms']
        game_ids = data['game_ids']
    except Exception:
        rooms_n = 0
        game_ids = []

    games_n = 0
    if game_ids:
        ids = ','.join(str(g) for g in game_ids)
        out2 = _exec('chess-game-service', f'''
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text("DELETE FROM games WHERE id IN ({ids})"))
db.commit()
db.close()
print(r.rowcount)
''')
        try:
            games_n = int(out2.split('\n')[-1])
        except Exception:
            games_n = 0

    users_n = 0
    out3 = _exec('chess-auth-service', f'''
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM refresh_tokens WHERE user_id IN (SELECT id FROM users WHERE username LIKE \'%{suffix}%\')"))
r = db.execute(text("DELETE FROM users WHERE username LIKE \'%{suffix}%\'"))
db.commit()
db.close()
print(r.rowcount)
''')
    try:
        users_n = int(out3.split('\n')[-1])
    except Exception:
        users_n = 0

    print(f'  cleanup: {rooms_n} rooms, {games_n} games, {users_n} users removed')
