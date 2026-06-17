"""T32вЂ“T34: Return-to-game panel вЂ” intentional navigation away shows panel, not auto-redirect."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't9'
P1 = {'username': f'alice_{SUFFIX}', 'email': f'alice_{SUFFIX}@chesstest.com', 'password': 'pass1234'}
P2 = {'username': f'bob_{SUFFIX}',   'email': f'bob_{SUFFIX}@chesstest.com',   'password': 'pass1234'}

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

        state['p1'] = p1
        state['p2'] = p2

        yield
    finally:
        ctx1.close()
        ctx2.close()
        cleanup(SUFFIX)


def test_T32_clicking_rooms_link_shows_return_panel(players):
    p1 = state['p1']
    # game is active вЂ” clicking "в†ђ Rooms" sets left_game in sessionStorage
    p1.click('a[href="rooms.html"]')
    p1.wait_for_url('**/rooms.html', timeout=8000)
    # rooms.js reads left_game and shows the "Your active game" panel instead of auto-redirect
    p1.wait_for_selector('#my-game-panel:not(.hidden)', timeout=8000)
    assert p1.locator('#my-game-panel').is_visible()


def test_T33_return_to_game_button_goes_back(players):
    p1 = state['p1']
    # click "Return to game" inside the panel
    p1.click('#my-game-return-btn')
    p1.wait_for_url('**/game.html**', timeout=8000)
    p1.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=10000)
    assert p1.locator('#game-status').text_content() == 'active'
    state['p1_back_at_game'] = True


def test_T34_direct_navigation_auto_redirects_to_game(players):
    p2 = state['p2']
    # p2 navigates to rooms.html directly (no left_game flag) while game is active
    # rooms.js should auto-redirect to game.html without showing the panel
    p2.goto(BASE + '/rooms.html')
    # expect immediate redirect to game.html (rooms.js redirects on init)
    p2.wait_for_url('**/game.html**', timeout=10000)
    assert 'game.html' in p2.url
    # panel must NOT be visible (auto-redirect happened, panel not shown)
    # (we're back on game.html, not rooms.html, so this is confirmed by URL)
