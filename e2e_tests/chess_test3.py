"""T9вЂ“T12: Disconnect timeout вЂ” opponent banner shown, game abandoned, room deleted."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't3'
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

    _setup_done = False
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

        state['p2'] = p2
        state['ctx1'] = ctx1

        _setup_done = True
        yield
    finally:
        if not _setup_done:
            ctx1.close()
        ctx2.close()
        cleanup(SUFFIX)


def test_T9_disconnect_banner_appears(players):
    ctx1 = state['ctx1']
    p2 = state['p2']

    # disconnect p1 by closing the page вЂ” do NOT reconnect this time
    p1_page = ctx1.pages[0]
    p1_page.close()
    ctx1.close()   # close context too so reconnect can't happen

    p2.wait_for_selector('#disconnect-banner.visible', timeout=10000)
    text = p2.locator('#disconnect-countdown').text_content()
    assert 'abandoned' in text.lower()


def test_T10_game_abandoned_after_timeout(players):
    p2 = state['p2']
    # wait up to 35 s for the 30 s timer to fire and game_abandoned to arrive
    p2.wait_for_selector('#game-over-banner.visible', timeout=40000)


def test_T11_winner_banner_shown_for_remaining_player(players):
    p2 = state['p2']
    # active-game disconnect timeout fires game_over → remaining player wins
    title = p2.locator('#game-over-title').text_content().lower()
    assert 'win' in title


def test_T12_room_deleted_from_list(players):
    p2 = state['p2']
    # navigate to rooms вЂ” room should be gone
    p2.goto(BASE + '/rooms.html')
    p2.wait_for_selector('#rooms-tbody', timeout=5000)
    tbody = p2.locator('#rooms-tbody').text_content()
    # room for alice_t3 must not appear (it was deleted when game ended)
    assert f'alice_{SUFFIX}' not in tbody
