from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import wait_for_db
from app.events.publisher import wait_for_redis
from app.events.subscriber import start_subscriber
from app.events.ws_relay import start_ws_relay
from app.routers import games, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    wait_for_redis()
    start_subscriber()
    await start_ws_relay()
    yield


app = FastAPI(
    title="Chess Game Service",
    description="Game session and move management microservice for the chess application",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "service": "chess-game-service",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(games.router)
app.include_router(ws.router)
