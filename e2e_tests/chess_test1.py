"""T1вЂ“T4: Complete resign game вЂ” two players, game starts, p1 resigns, banners checked."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't1'
P1 = {'username': f'alice_{SUFFIX}', 'email': f'alice_{SUFFIX}@chesstest.com', 'password': 'pass1234'}
P2 = {'username': f'bob_{SUFFIX}',   'email': f'bob_{SUFFIX}@chesstest.com',   'password': 'pass1234'}


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

        # p1 creates a room and waits
        p1.goto(BASE + '/rooms.html')
        p1.wait_for_selector('#create-room-btn', state='visible', timeout=10000)
        p1.click('#create-room-btn')

        p2.goto(BASE + '/rooms.html')
        p2.wait_for_selector('.join-btn', timeout=15000)
        p2.click('.join-btn')

        # both land on game.html
        p1.wait_for_url('**/game.html**', timeout=15000)
        p2.wait_for_url('**/game.html**', timeout=15000)

        # wait for WS game_start so status is 'active'
        p1.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)
        p2.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)

        yield p1, p2
    finally:
        ctx1.close()
        ctx2.close()
        cleanup(SUFFIX)


def test_T1_game_active(players):
    p1, p2 = players
    assert p1.locator('#game-status').text_content() == 'active'
    assert p2.locator('#game-status').text_content() == 'active'


def test_T2_board_rendered(players):
    p1, p2 = players
    # 64 squares should be present on both boards
    assert p1.locator('#chessboard .sq').count() == 64
    assert p2.locator('#chessboard .sq').count() == 64
    # white starts so resign button is visible for both players
    assert p1.locator('#resign-btn').is_visible()
    assert p2.locator('#resign-btn').is_visible()


def test_T3_resign_ends_game(players):
    p1, p2 = players
    # p1 (white) resigns вЂ” accept the confirm dialog
    p1.once('dialog', lambda d: d.accept())
    p1.click('#resign-btn')
    # both should see the game-over banner
    p1.wait_for_selector('#game-over-banner.visible', timeout=8000)
    p2.wait_for_selector('#game-over-banner.visible', timeout=8000)


def test_T4_banner_text(players):
    p1, p2 = players
    # resigner (p1 = white) loses; p2 (black) wins
    assert 'lose' in p1.locator('#game-over-title').text_content().lower()
    assert 'win'  in p2.locator('#game-over-title').text_content().lower()
    # resign button must be gone after game over
    assert not p1.locator('#resign-btn').is_visible()
    assert not p2.locator('#resign-btn').is_visible()
