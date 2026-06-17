"""T21вЂ“T23: Auth flows вЂ” unauth redirect, bad credentials, logout."""
import pytest
from helpers import reg, BASE
from cleanup import cleanup

SUFFIX = 't6'
P1 = {'username': f'alice_{SUFFIX}', 'email': f'alice_{SUFFIX}@chesstest.com', 'password': 'pass1234'}


@pytest.fixture(scope='module')
def browser_ctx(browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    yield page
    ctx.close()


def test_T21_unauthenticated_redirect_to_login(browser_ctx):
    page = browser_ctx
    # clear any leftover tokens and navigate to a protected page
    page.goto(BASE)
    page.evaluate("localStorage.clear()")
    page.goto(BASE + '/rooms.html')
    # rooms.js guard must redirect to /index.html
    page.wait_for_url('**/index.html', timeout=5000)


def test_T22_login_with_wrong_password_shows_error(browser_ctx):
    page = browser_ctx
    # register then try to login with wrong password
    reg(page, P1)

    # clear token and navigate atomically — prevents race with rooms.js polling guard
    page.evaluate("localStorage.clear(); window.location.href = '/index.html';")
    page.wait_for_url('**/index.html', timeout=10000)

    page.fill('#login-email', P1['email'])
    page.fill('#login-password', 'wrongpassword')
    page.click("#login-form button[type='submit']")
    page.wait_for_selector('#login-msg.visible', timeout=5000)
    msg = page.locator('#login-msg').text_content().lower()
    assert 'invalid' in msg


def test_T23_logout_clears_session(browser_ctx):
    page = browser_ctx
    # login properly
    page.goto(BASE)
    page.fill('#login-email', P1['email'])
    page.fill('#login-password', P1['password'])
    page.click("#login-form button[type='submit']")
    page.wait_for_url('**/rooms.html', timeout=8000)

    # logout
    page.click('#logout-btn')
    page.wait_for_url('**/index.html', timeout=5000)

    # navigate to rooms вЂ” should redirect back to login
    page.goto(BASE + '/rooms.html')
    page.wait_for_url('**/index.html', timeout=5000)
