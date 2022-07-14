import json
import logging

import backoff
import chess
import httpx

from typing import Callable, AsyncGenerator
from config import CONFIG


class Lichess:
    def __init__(self):
        self.token = CONFIG["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
        }

        self.client = httpx.AsyncClient(
            base_url="https://lichess.org", headers=self.headers
        )

        self.user: dict | None = None

    @classmethod
    async def create(cls):
        li = cls()
        li.user = await li.get_account()
        return li

    @property
    def username(self):
        return self.user["username"]

    @property
    def title(self):
        return self.user.get("title")

    @backoff.on_exception(backoff.expo, httpx.HTTPStatusError)
    async def get(self, endpoint: str, **kwargs) -> httpx.Response:
        response = await self.client.get(endpoint, **kwargs)
        if response.status_code < 500:
            return response
        else:
            response.raise_for_status()

    @backoff.on_exception(backoff.expo, httpx.HTTPStatusError, max_time=300)
    async def post(self, endpoint: str, **kwargs) -> httpx.Response:
        response = await self.client.post(endpoint, **kwargs)
        if response.status_code < 500:
            return response
        else:
            response.raise_for_status()

    async def watch_control_stream(self) -> AsyncGenerator[dict, dict]:
        while True:
            try:
                async with self.client.stream(
                    "GET", "/api/stream/event", timeout=None
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            event = json.loads(line)
                        else:
                            event = {"type": "ping"}
                        yield event
                return
            except httpx.HTTPStatusError:
                pass

    async def watch_game_stream(self, game_id) -> AsyncGenerator[dict, dict]:
        while True:
            try:
                async with self.client.stream(
                    "GET",
                    f"/api/bot/game/stream/{game_id}",
                    timeout=None,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            event = json.loads(line)
                        else:
                            event = {"type": "ping"}
                        yield event
                return
            except httpx.HTTPStatusError:
                if game_id not in await self.get_ongoing_games():
                    return

    async def get_online_bots(self) -> AsyncGenerator[dict, dict]:
        try:
            async with self.client.stream("GET", "/api/bot/online") as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    bot = json.loads(line)
                    yield bot
        except httpx.HTTPStatusError as e:
            return

    async def get_account(self) -> dict:
        response = await self.get("/api/account")
        if response.status_code == 200:
            return response.json()
        else:
            return {}

    async def accept_challenge(self, challenge_id: str) -> bool:
        response = await self.post(f"/api/challenge/{challenge_id}/accept")
        if response.status_code == 200:
            return True
        else:
            return False

    async def decline_challenge(self, challenge_id: str) -> bool:
        response = await self.post(f"/api/challenge/{challenge_id}/decline")
        if response.status_code == 200:
            return True
        else:
            return False

    async def create_challenge(
        self, opponent: str, initial_time: int, increment: int = 0
    ) -> str:

        response = await self.post(
            f"/api/challenge/{opponent}",
            data={
                "rated": str(CONFIG["matchmaking"]["rated"]).lower(),
                "clock.limit": initial_time,
                "clock.increment": increment,
                "variant": CONFIG["matchmaking"]["variant"],
                "color": "random",
            },
        )
        if response.status_code == 200:
            return response.json()["challenge"]["id"]
        else:
            return ""

    async def cancel_challenge(self, challenge_id: str) -> bool:
        response = await self.post(f"/api/challenge/{challenge_id}/cancel")
        if response.status_code == 200:
            return True
        else:
            return False

    async def abort_game(self, game_id: str) -> bool:
        response = await self.post(f"/api/bot/game/{game_id}/abort")
        if response.status_code == 200:
            return True
        else:
            return False

    async def get_open_challenges(self) -> dict:
        response = await self.get("/api/challenge")
        if response.status_code == 200:
            return response.json()
        else:
            return {}

    async def get_ongoing_games(self) -> list[str]:
        response = await self.get("/api/account/playing")
        if response.status_code == 200:
            return [game_info["gameId"] for game_info in response.json()["nowPlaying"]]
        else:
            return []

    async def make_move(self, game_id: str, move: chess.Move) -> bool:
        response = await self.post(
            f"/api/bot/game/{game_id}/move/{move.uci()}",
        )
        if response.status_code == 200:
            return True
        else:
            return False

    async def upgrade_account(self) -> bool:
        response = await self.post("/api/bot/account/upgrade")
        if response.status_code == 200:
            return True
        else:
            return False
