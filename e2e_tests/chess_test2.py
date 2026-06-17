"""T5вЂ“T8: Disconnect and reconnect within 30 s вЂ” banner shown, then hidden, game resumes."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't2'
P1 = {'username': f'alice_{SUFFIX}', 'email': f'alice_{SUFFIX}@chesstest.com', 'password': 'pass1234'}
P2 = {'username': f'bob_{SUFFIX}',   'email': f'bob_{SUFFIX}@chesstest.com',   'password': 'pass1234'}

# mutable dict shared across tests in this module
state = {}


@pytest.fixture(scope='module')
def players(browser):
    cleanup(SUFFIX)

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()

    try:
        reg(p1, P1)
        reg(p2, P2)

        p1.goto(BASE + '/rooms.html')
        p1.wait_for_selector('#create-room-btn', state='visible', timeout=10000)
        p1.click('#create-room-btn')

        p2.goto(BASE + '/rooms.html')
        p2.wait_for_selector('.join-btn', timeout=15000)
        p2.click('.join-btn')

        p1.wait_for_url('**/game.html**', timeout=15000)
        p2.wait_for_url('**/game.html**', timeout=15000)
        p1.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)

        state['game_url'] = p1.url
        state['ctx1'] = ctx1
        state['p2'] = p2

        yield
    finally:
        ctx1.close()
        ctx2.close()
        cleanup(SUFFIX)


def test_T5_disconnect_banner_shown(players):
    p2 = state['p2']
    ctx1 = state['ctx1']

    # close p1's page to simulate disconnect (keeps session in ctx1)
    p1_page = ctx1.pages[0]
    p1_page.close()

    p2.wait_for_selector('#disconnect-banner.visible', timeout=10000)
    countdown = p2.locator('#disconnect-countdown').text_content()
    assert 'abandoned' in countdown.lower()


def test_T6_reconnect_hides_banner(players):
    p2 = state['p2']
    ctx1 = state['ctx1']

    # reconnect p1 in the same context вЂ” tokens survive
    new_p1 = ctx1.new_page()
    new_p1.goto(state['game_url'])
    new_p1.wait_for_url('**/game.html**', timeout=10000)
    state['p1_reconnected'] = new_p1

    p2.wait_for_selector('#disconnect-banner.visible', state='hidden', timeout=10000)


def test_T7_game_continues_after_reconnect(players):
    new_p1 = state.get('p1_reconnected')
    if not new_p1:
        pytest.skip('reconnect did not complete in T6')
    assert new_p1.locator('#game-status').text_content() == 'active'
    assert new_p1.locator('#chessboard .sq').count() == 64


def test_T8_reconnected_player_sees_board_state(players):
    new_p1 = state.get('p1_reconnected')
    if not new_p1:
        pytest.skip('reconnect did not complete in T6')
    # server sends game_state personally on reconnect вЂ” pieces must be on board
    pieces = new_p1.locator('#chessboard .sq.has-piece').count()
    assert pieces >= 16
