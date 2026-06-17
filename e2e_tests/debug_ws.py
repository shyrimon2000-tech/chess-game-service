import asyncio, random, string
from playwright.async_api import async_playwright

BASE = "http://localhost:8080"
suffix = "ws_" + "".join(random.choices(string.ascii_lowercase, k=4))
U1 = {"email": f"w_{suffix}@t.com", "password": "pass123", "username": f"w_{suffix}"}
U2 = {"email": f"b_{suffix}@t.com", "password": "pass123", "username": f"b_{suffix}"}

p1_ws_msgs = []
p2_ws_msgs = []
p1_console = []
p2_console = []

async def reg(page, user):
    await page.goto(BASE)
    await page.click('button[data-tab="register"]')
    await page.wait_for_selector("#tab-register.active", timeout=3000)
    await page.fill("#reg-username", user["username"])
    await page.fill("#reg-email", user["email"])
    await page.fill("#reg-password", user["password"])
    await page.click('#register-form button[type="submit"]')
    await page.wait_for_url("**/rooms.html", timeout=8000)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx1 = await browser.new_context()
        ctx2 = await browser.new_context()
        p1 = await ctx1.new_page()
        p2 = await ctx2.new_page()

        # capture console
        p1.on("console", lambda m: p1_console.append(f"{m.type}: {m.text}"))
        p2.on("console", lambda m: p2_console.append(f"{m.type}: {m.text}"))

        # capture WS frames
        def capture_ws(page_name, ws_msgs):
            def on_ws(ws):
                print(f"  [{page_name}] WS CREATED url={ws.url[:80]}")
                ws_msgs.append(f"CREATED {ws.url[:80]}")
                ws.on("framereceived", lambda f: ws_msgs.append(f"RECV {(f if isinstance(f, str) else f.payload)[:200]}"))
                ws.on("framesent",    lambda f: ws_msgs.append(f"SENT {f.payload[:100]}"))
                ws.on("close",       lambda: ws_msgs.append("CLOSED"))
            return on_ws
        p1.on("websocket", capture_ws("p1", p1_ws_msgs))
        p2.on("websocket", capture_ws("p2", p2_ws_msgs))

        print("Registering...")
        await reg(p1, U1)
        await reg(p2, U2)

        print("p1 creates room...")
        import time
        t0 = time.time()
        async with p1.expect_response(lambda r: "/api/rooms" in r.url and r.request.method == "POST") as ri:
            await p1.click("#create-room-btn")
        resp = await ri.value
        room_data = await resp.json()
        room_id = room_data["id"]
        await p1.wait_for_url("**/game.html**", timeout=15000)
        print(f"  p1 on game.html in {time.time()-t0:.2f}s  game_id={p1.url.split('game_id=')[1]}")
        await asyncio.sleep(0.5)
        print(f"  p1 WS msgs so far: {p1_ws_msgs}")

        print("p2 joins...")
        t1 = time.time()
        await p2.goto(f"{BASE}/rooms.html")
        await p2.wait_for_selector(f'.join-btn[data-room-id="{room_id}"]', timeout=6000)
        await p2.click(f'.join-btn[data-room-id="{room_id}"]')
        await p2.wait_for_url("**/game.html**", timeout=10000)
        print(f"  p2 on game.html in {time.time()-t1:.2f}s")

        # poll every 200ms for up to 5 seconds
        for i in range(25):
            await asyncio.sleep(0.2)
            gs_p1 = await p1.evaluate("window.gameStatus")
            gs_p2 = await p2.evaluate("window.gameStatus")
            mc_p2 = await p2.evaluate("window.myColor")
            if gs_p1 == "active":
                print(f"  p1 got active at {i*0.2:.1f}s")
                break
            if i % 5 == 4:
                print(f"  t={i*0.2:.1f}s  p1.gameStatus={gs_p1!r}  p2.gameStatus={gs_p2!r}  p2.myColor={mc_p2!r}")
                print(f"    p1 WS msgs: {p1_ws_msgs[-3:] if p1_ws_msgs else []}")
        else:
            print(f"  TIMEOUT: p1 never got active")

        print("\n--- p1 WS frames ---")
        for m in p1_ws_msgs: print(" ", m)
        print("\n--- p2 WS frames ---")
        for m in p2_ws_msgs: print(" ", m)
        print("\n--- p1 console ---")
        for m in p1_console: print(" ", m)

        await browser.close()

        # cleanup
        import subprocess, os
        subprocess.run(
            ["docker", "compose", "exec", "-T", "chess-auth-service", "python", "-c",
             f"from app.database import SessionLocal; from sqlalchemy import text; db=SessionLocal(); db.execute(text(\"DELETE FROM users WHERE username LIKE '%{suffix}%'\")); db.commit()"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True,
        )

asyncio.run(main())
