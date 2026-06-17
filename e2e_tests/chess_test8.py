"""T28вЂ“T31: Board interaction вЂ” legal move highlights, turn guard, move execution."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't8'
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
        p2.wait_for_function("document.getElementById('game-status')?.textContent === 'active'", timeout=30000)

        state['p1'] = p1
        state['p2'] = p2

        yield
    finally:
        ctx1.close()
        ctx2.close()
        cleanup(SUFFIX)


def test_T28_click_own_pawn_shows_legal_moves(players):
    p1 = state['p1']
    # p1 is white, e2 has a white pawn in starting position
    p1.click('[data-sq="e2"]')
    p1.wait_for_selector('.sq.legal-target', timeout=5000)
    targets = p1.locator('.sq.legal-target').count()
    assert targets >= 2   # e3 and e4 are always legal on first move


def test_T29_click_opponent_piece_shows_no_selection(players):
    p1 = state['p1']
    # click somewhere else first to deselect
    p1.keyboard.press('Escape')
    # click e7 вЂ” that's a black pawn, not p1's piece в†’ no selection/legal moves
    p1.click('[data-sq="e7"]')
    p1.wait_for_timeout(500)
    selected = p1.locator('.sq.selected').count()
    legal    = p1.locator('.sq.legal-target').count()
    assert selected == 0
    assert legal == 0


def test_T30_cannot_move_on_opponents_turn(players):
    p2 = state['p2']
    # p2 is black, white moves first вЂ” p2 clicks their pawn but it's not their turn
    p2.click('[data-sq="e7"]')
    p2.wait_for_timeout(500)
    assert p2.locator('.sq.selected').count() == 0
    assert p2.locator('.sq.legal-target').count() == 0


def test_T31_valid_move_updates_board(players):
    p1 = state['p1']
    p2 = state['p2']

    # select e2 and click e4 to make the move e2e4
    p1.click('[data-sq="e2"]')
    p1.wait_for_selector('[data-sq="e4"].legal-target', timeout=5000)
    p1.click('[data-sq="e4"]')

    # board must update on both sides: e4 occupied, e2 empty
    p1.wait_for_selector('[data-sq="e4"].has-piece', timeout=8000)
    p2.wait_for_selector('[data-sq="e4"].has-piece', timeout=8000)

    assert not p1.locator('[data-sq="e2"]').get_attribute('data-piece')
    assert not p2.locator('[data-sq="e2"]').get_attribute('data-piece')

    # turn should switch to black
    assert p1.locator('#game-status').text_content() == 'active'
