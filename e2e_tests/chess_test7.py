"""T24вЂ“T27: Spectator вЂ” joins active game, sees board from white's perspective, can't act."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't7'
P1  = {'username': f'alice_{SUFFIX}',    'email': f'alice_{SUFFIX}@chesstest.com',    'password': 'pass1234'}
P2  = {'username': f'bob_{SUFFIX}',      'email': f'bob_{SUFFIX}@chesstest.com',      'password': 'pass1234'}
SPT = {'username': f'spectator_{SUFFIX}','email': f'spectator_{SUFFIX}@chesstest.com','password': 'pass1234'}

state = {}


@pytest.fixture(scope='module')
def setup(browser):
    cleanup(SUFFIX)

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    ctx3 = browser.new_context()
    p1   = ctx1.new_page()
    p2   = ctx2.new_page()
    spt  = ctx3.new_page()

    try:
        reg(p1, P1)
        reg(p2, P2)
        reg(spt, SPT)

        # start a game between p1 and p2
        p1.goto(BASE + '/rooms.html')
        p1.wait_for_selector('#create-room-btn', state='visible', timeout=10000)
        p1.click('#create-room-btn')

        p2.goto(BASE + '/rooms.html')
        p2.wait_for_selector('.join-btn', timeout=15000)
        p2.click('.join-btn')

        p1.wait_for_url('**/game.html**', timeout=15000)
        p2.wait_for_url('**/game.html**', timeout=15000)
        p1.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)

        # spectator joins via Spectate button
        spt.goto(BASE + '/rooms.html')
        spt.wait_for_selector('.spectate-btn', timeout=10000)
        spt.click('.spectate-btn')
        spt.wait_for_url('**/game.html**', timeout=10000)
        spt.wait_for_selector('#chessboard .sq', timeout=8000)

        state['p1']  = p1
        state['p2']  = p2
        state['spt'] = spt

        yield
    finally:
        ctx1.close()
        ctx2.close()
        ctx3.close()
        cleanup(SUFFIX)


def test_T24_spectator_reaches_game_page(setup):
    spt = state['spt']
    assert 'game.html' in spt.url
    assert spt.locator('#chessboard .sq').count() == 64


def test_T25_spectator_sees_white_perspective(setup):
    spt = state['spt']
    # From white's perspective the board is not flipped: top-left square in the DOM is a8.
    # If the board were rendered from black's perspective, the first square would be h1.
    first_sq = spt.locator('#chessboard .sq').first
    assert first_sq.get_attribute('data-sq') == 'a8'


def test_T26_spectator_resign_button_hidden(setup):
    spt = state['spt']
    # spectator must never see resign button
    assert not spt.locator('#resign-btn').is_visible()


def test_T27_spectator_sees_board_updates(setup):
    p1  = state['p1']
    spt = state['spt']

    # p1 (white) makes a move e2в†'e4
    p1.click('[data-sq="e2"]')
    p1.wait_for_selector('[data-sq="e4"].legal-target', timeout=5000)
    p1.click('[data-sq="e4"]')

    # spectator must see e4 occupied and e2 empty after the move
    spt.wait_for_selector('[data-sq="e4"].has-piece', timeout=15000)
    assert not spt.locator('[data-sq="e2"]').get_attribute('data-piece')
