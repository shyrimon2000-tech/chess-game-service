"""T13вЂ“T16: Resign button visibility, resign flow, redirect, room cleanup."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't4'
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


def test_T13_resign_btn_visible_for_active_players(players):
    p1 = state['p1']
    p2 = state['p2']
    assert p1.locator('#resign-btn').is_visible()
    assert p2.locator('#resign-btn').is_visible()


def test_T14_resign_btn_hidden_after_game_over(players):
    p1 = state['p1']
    p2 = state['p2']

    p1.once('dialog', lambda d: d.accept())
    p1.click('#resign-btn')

    p1.wait_for_selector('#game-over-banner.visible', timeout=8000)
    p2.wait_for_selector('#game-over-banner.visible', timeout=8000)

    assert not p1.locator('#resign-btn').is_visible()
    assert not p2.locator('#resign-btn').is_visible()


def test_T15_back_to_rooms_after_resign(players):
    p1 = state['p1']
    # click "Back to Rooms" button inside game-over banner
    p1.click('#game-over-banner button')
    p1.wait_for_url('**/rooms.html', timeout=8000)
    assert 'rooms.html' in p1.url


def test_T16_room_absent_from_list(players):
    p1 = state['p1']
    # give room-service a moment to process game_over and delete the room row
    p1.wait_for_selector('#rooms-tbody', timeout=5000)
    p1.wait_for_timeout(1500)
    tbody = p1.locator('#rooms-tbody').text_content()
    assert f'alice_{SUFFIX}' not in tbody
