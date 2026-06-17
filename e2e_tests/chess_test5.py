"""T17вЂ“T20: Quick join and explicit join вЂ” room creation, matchmaking, game start."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't5'
P1 = {'username': f'alice_{SUFFIX}', 'email': f'alice_{SUFFIX}@chesstest.com', 'password': 'pass1234'}
P2 = {'username': f'bob_{SUFFIX}',   'email': f'bob_{SUFFIX}@chesstest.com',   'password': 'pass1234'}
P3 = {'username': f'carol_{SUFFIX}', 'email': f'carol_{SUFFIX}@chesstest.com', 'password': 'pass1234'}

state = {}


@pytest.fixture(scope='module')
def pages(browser):
    cleanup(SUFFIX)

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    ctx3 = browser.new_context()
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()
    p3 = ctx3.new_page()

    try:
        reg(p1, P1)
        reg(p2, P2)
        reg(p3, P3)

        state['p1'] = p1
        state['p2'] = p2
        state['p3'] = p3

        yield
    finally:
        ctx1.close()
        ctx2.close()
        ctx3.close()
        cleanup(SUFFIX)


def test_T17_quick_join_creates_room_when_none_available(pages):
    p1 = state['p1']
    p1.goto(BASE + '/rooms.html')
    p1.wait_for_selector('#quick-join-btn', state='visible', timeout=10000)
    p1.click('#quick-join-btn')
    # quick-join creates a room and navigates p1 directly to game.html in waiting status
    p1.wait_for_url('**/game.html**', timeout=30000)
    p1.wait_for_function("document.getElementById('game-status')?.textContent === 'waiting'", timeout=10000)
    assert p1.locator('#game-status').text_content() == 'waiting'


def test_T18_quick_join_joins_existing_room(pages):
    p2 = state['p2']
    # p1 has a waiting room вЂ” p2 quick joins it
    p2.click('#quick-join-btn')
    # p2 is sent directly to game.html (game activated)
    p2.wait_for_url('**/game.html**', timeout=15000)
    state['p2_game_url'] = p2.url


def test_T19_both_players_reach_game_page(pages):
    p1 = state['p1']
    p2 = state['p2']
    # p1 should also be redirected to game.html via room poll
    p1.wait_for_url('**/game.html**', timeout=20000)
    # both must see active game
    p1.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)
    p2.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)
    assert p1.locator('#game-status').text_content() == 'active'
    assert p2.locator('#game-status').text_content() == 'active'


def test_T20_explicit_join_by_id_is_spectator_on_active_game(pages):
    p1 = state['p1']
    p3 = state['p3']
    # the active game room should appear in rooms list with a Spectate button
    p3.goto(BASE + '/rooms.html')
    # reload until spectate btn appears (room-service may have not listed active room yet)
    p3.wait_for_selector('.spectate-btn', timeout=10000)
    p3.click('.spectate-btn')
    p3.wait_for_url('**/game.html**', timeout=10000)
    # spectator: resign button must be hidden
    assert not p3.locator('#resign-btn').is_visible()
