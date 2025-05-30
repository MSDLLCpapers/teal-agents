from __future__ import annotations
import json, asyncio, redis.asyncio as redis
from ska_utils import AppConfig
from enum import Enum
from collab_orchestrator.configs import (
    TA_REDIS_HOST, TA_REDIS_PORT, TA_REDIS_DB, TA_REDIS_TTL
)


class PendingPlanStore:
    """Async hash + pub/sub helper for pending plans."""

    def __init__(self) -> None:
        cfg = AppConfig()  # <- NOW after add_configs()
        host = cfg.get(TA_REDIS_HOST.env_name)
        if host is None:
            raise RuntimeError("HITL requested but TA_REDIS_HOST not set")

        self._ttl = int(cfg.get(TA_REDIS_TTL.env_name) or 3600)
        self._r: redis.Redis = redis.Redis(
            host=host,
            port=int(cfg.get(TA_REDIS_PORT.env_name) or 6379),
            db=int(cfg.get(TA_REDIS_DB.env_name) or 0),
            decode_responses=True,
        )

    def key(self, sid: str) -> str:
        return f"pending-plan:{sid}"

    # -------- CRUD ----------
    async def save(self, sid: str, plan_dict: dict) -> None:
        await self._r.hset(
            self.key(sid),
            mapping={
                "plan": json.dumps(plan_dict, default=lambda o: o.value if isinstance(o, Enum) else str(o)),
                "status": "pending",
                "edited_plan": "",
            },
        )
        await self._r.expire(self.key(sid), self._ttl)

    async def set_decision(
            self, sid: str, status: str, edited_plan: dict | None = None
    ) -> None:
        m: dict[str, str] = {"status": status}
        if edited_plan is not None:
            m["edited_plan"] = json.dumps(edited_plan, default=lambda o: o.value if isinstance(o, Enum) else str(o))
        await self._r.hset(self.key(sid), mapping=m)
        await self._r.publish(self.key(sid), "go")

    async def get(self, sid: str) -> dict | None:
        h = await self._r.hgetall(self.key(sid))
        if not h:
            return None
        if "plan" in h:
            h["plan"] = json.loads(h["plan"])
        if h.get("edited_plan"):
            try:
                h["edited_plan"] = json.loads(h["edited_plan"])
            except json.JSONDecodeError:
                h["edited_plan"] = None
        return h

    async def delete(self, sid: str) -> None:
        await self._r.delete(self.key(sid))

    # -------- waiter ----------
    async def wait_for_decision(self, sid: str, timeout: int | None):
        """
        Suspend until status != pending OR key expires OR timeout.
        Returns full hash dict, or None on timeout/expiry.
        """
        # quick pre-check
        snap = await self.get(sid)
        if snap and snap["status"] != "pending":
            return snap

        pubsub = self._r.pubsub()
        await pubsub.subscribe(self.key(sid))
        try:
            async def _listen():
                async for message in pubsub.listen():
                    # Only respond for actual published messages, not subscription confirmations
                    if message.get("type") == "message":
                        return

            waiter = asyncio.create_task(_listen())
            try:
                if timeout and timeout > 0:
                    await asyncio.wait_for(waiter, timeout)
                else:
                    await waiter
            except asyncio.TimeoutError:
                return None
            return await self.get(sid)
        finally:
            await pubsub.unsubscribe(self.key(sid))
            await pubsub.close()
