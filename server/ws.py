"""
WebSocket module for real-time notifications in the Distributed AI Network.

Supports:
- Room-based subscriptions (tasks, workers, jobs)
- Broadcasting to all clients
- Targeted messages to specific workers
- Event filtering and subscription management
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="", tags=["WebSocket"])


# =============================================================================
# EVENT TYPES
# =============================================================================

class EventType(str, Enum):
    # Task events
    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    TASK_SUBMITTED = "task.submitted"
    TASK_VALIDATED = "task.validated"
    TASK_COMPLETED = "task.completed"
    TASK_REJECTED = "task.rejected"

    # Worker events
    WORKER_REGISTERED = "worker.registered"
    WORKER_ONLINE = "worker.online"
    WORKER_OFFLINE = "worker.offline"
    WORKER_BANNED = "worker.banned"
    WORKER_REPUTATION = "worker.reputation"

    # Job events
    JOB_CREATED = "job.created"
    JOB_PROGRESS = "job.progress"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"

    # System events
    SYSTEM_ALERT = "system.alert"
    SYSTEM_STATS = "system.stats"


# =============================================================================
# CONNECTION MANAGER
# =============================================================================

@dataclass
class ClientConnection:
    """Represents a WebSocket client connection."""
    websocket: WebSocket
    client_id: str
    subscriptions: Set[str] = field(default_factory=set)
    worker_id: Optional[int] = None
    connected_at: datetime = field(default_factory=datetime.utcnow)

    async def send(self, message: dict) -> bool:
        """Send message to this client."""
        try:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_json(message)
                return True
        except Exception as e:
            logger.debug(f"Failed to send to {self.client_id}: {e}")
        return False


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self):
        self.connections: Dict[str, ClientConnection] = {}
        self.rooms: Dict[str, Set[str]] = {
            "tasks": set(),
            "workers": set(),
            "jobs": set(),
            "system": set(),
            "all": set(),
        }
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        worker_id: Optional[int] = None,
    ) -> ClientConnection:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        client = ClientConnection(
            websocket=websocket,
            client_id=client_id,
            worker_id=worker_id,
        )

        async with self._lock:
            self.connections[client_id] = client
            self.rooms["all"].add(client_id)

        logger.info(f"WebSocket connected: {client_id}")
        return client

    async def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if client_id in self.connections:
                client = self.connections[client_id]

                # Remove from all rooms
                for room in self.rooms.values():
                    room.discard(client_id)

                del self.connections[client_id]

        logger.info(f"WebSocket disconnected: {client_id}")

    async def subscribe(self, client_id: str, room: str) -> bool:
        """Subscribe a client to a room."""
        async with self._lock:
            if client_id not in self.connections:
                return False

            if room not in self.rooms:
                self.rooms[room] = set()

            self.rooms[room].add(client_id)
            self.connections[client_id].subscriptions.add(room)

        logger.debug(f"Client {client_id} subscribed to {room}")
        return True

    async def unsubscribe(self, client_id: str, room: str) -> bool:
        """Unsubscribe a client from a room."""
        async with self._lock:
            if room in self.rooms:
                self.rooms[room].discard(client_id)

            if client_id in self.connections:
                self.connections[client_id].subscriptions.discard(room)

        return True

    async def broadcast(self, message: dict, room: str = "all") -> int:
        """Broadcast a message to all clients in a room."""
        sent_count = 0
        dead_clients = []

        async with self._lock:
            clients = list(self.rooms.get(room, set()))

        for client_id in clients:
            client = self.connections.get(client_id)
            if client:
                if await client.send(message):
                    sent_count += 1
                else:
                    dead_clients.append(client_id)

        # Clean up dead connections
        for client_id in dead_clients:
            await self.disconnect(client_id)

        return sent_count

    async def send_to_worker(self, worker_id: int, message: dict) -> bool:
        """Send a message to a specific worker."""
        async with self._lock:
            for client in self.connections.values():
                if client.worker_id == worker_id:
                    return await client.send(message)
        return False

    async def send_event(
        self,
        event_type: EventType,
        data: dict,
        room: Optional[str] = None,
    ) -> int:
        """Send a typed event to subscribers."""
        message = {
            "type": event_type.value,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Determine room from event type if not specified
        if room is None:
            if event_type.value.startswith("task."):
                room = "tasks"
            elif event_type.value.startswith("worker."):
                room = "workers"
            elif event_type.value.startswith("job."):
                room = "jobs"
            elif event_type.value.startswith("system."):
                room = "system"
            else:
                room = "all"

        return await self.broadcast(message, room)

    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self.connections),
            "rooms": {room: len(clients) for room, clients in self.rooms.items()},
        }


# Global connection manager
manager = ConnectionManager()


# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================

@ws_router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(default=None),
    worker_id: Optional[int] = Query(default=None),
):
    """
    Main WebSocket endpoint.

    Query parameters:
        - client_id: Unique client identifier (auto-generated if not provided)
        - worker_id: Worker ID for worker-specific notifications

    Message format:
        {"action": "subscribe", "room": "tasks"}
        {"action": "unsubscribe", "room": "tasks"}
        {"action": "ping"}
    """
    import uuid

    if not client_id:
        client_id = str(uuid.uuid4())

    client = await manager.connect(websocket, client_id, worker_id)

    # Send welcome message
    await client.send({
        "type": "connected",
        "client_id": client_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    try:
        while True:
            # Receive and process messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    room = message.get("room", "all")
                    await manager.subscribe(client_id, room)
                    await client.send({
                        "type": "subscribed",
                        "room": room,
                    })

                elif action == "unsubscribe":
                    room = message.get("room")
                    if room:
                        await manager.unsubscribe(client_id, room)
                        await client.send({
                            "type": "unsubscribed",
                            "room": room,
                        })

                elif action == "ping":
                    await client.send({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                elif action == "stats":
                    await client.send({
                        "type": "stats",
                        "data": manager.get_stats(),
                    })

            except json.JSONDecodeError:
                await client.send({
                    "type": "error",
                    "message": "Invalid JSON",
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        await manager.disconnect(client_id)


@ws_router.websocket("/ws/worker/{worker_id}")
async def worker_websocket(
    websocket: WebSocket,
    worker_id: int,
):
    """
    Dedicated WebSocket endpoint for workers.
    Automatically subscribes to worker-specific events.
    """
    client_id = f"worker-{worker_id}"

    client = await manager.connect(websocket, client_id, worker_id)

    # Auto-subscribe to relevant rooms
    await manager.subscribe(client_id, "tasks")
    await manager.subscribe(client_id, "workers")
    await manager.subscribe(client_id, f"worker:{worker_id}")

    await client.send({
        "type": "connected",
        "worker_id": worker_id,
        "subscriptions": ["tasks", "workers", f"worker:{worker_id}"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "ping":
                    await client.send({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(client_id)


# =============================================================================
# HELPER FUNCTIONS FOR BROADCASTING
# =============================================================================

async def broadcast(message: dict) -> int:
    """Broadcast to all connected clients (backwards compatible)."""
    return await manager.broadcast(message, "all")


async def notify_task_created(task_id: int, task_type: str, prompt: str) -> None:
    """Notify about task creation."""
    await manager.send_event(
        EventType.TASK_CREATED,
        {
            "task_id": task_id,
            "task_type": task_type,
            "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
        },
    )


async def notify_task_assigned(task_id: int, worker_id: int, mode: str) -> None:
    """Notify about task assignment."""
    await manager.send_event(
        EventType.TASK_ASSIGNED,
        {
            "task_id": task_id,
            "worker_id": worker_id,
            "mode": mode,
        },
    )

    # Also send to specific worker
    await manager.send_to_worker(worker_id, {
        "type": "task.assigned",
        "data": {"task_id": task_id, "mode": mode},
    })


async def notify_task_completed(
    task_id: int,
    worker_a_id: int,
    worker_b_id: int,
    reward_a: float,
    reward_b: float,
) -> None:
    """Notify about task completion."""
    await manager.send_event(
        EventType.TASK_COMPLETED,
        {
            "task_id": task_id,
            "worker_a_id": worker_a_id,
            "worker_b_id": worker_b_id,
            "reward_a": reward_a,
            "reward_b": reward_b,
        },
    )


async def notify_task_rejected(task_id: int, reason: str) -> None:
    """Notify about task rejection."""
    await manager.send_event(
        EventType.TASK_REJECTED,
        {
            "task_id": task_id,
            "reason": reason,
        },
    )


async def notify_worker_online(worker_id: int, worker_name: str) -> None:
    """Notify about worker coming online."""
    await manager.send_event(
        EventType.WORKER_ONLINE,
        {
            "worker_id": worker_id,
            "worker_name": worker_name,
        },
    )


async def notify_worker_offline(worker_id: int) -> None:
    """Notify about worker going offline."""
    await manager.send_event(
        EventType.WORKER_OFFLINE,
        {
            "worker_id": worker_id,
        },
    )


async def notify_worker_reputation(
    worker_id: int,
    old_reputation: float,
    new_reputation: float,
    reason: str,
) -> None:
    """Notify about worker reputation change."""
    await manager.send_event(
        EventType.WORKER_REPUTATION,
        {
            "worker_id": worker_id,
            "old_reputation": old_reputation,
            "new_reputation": new_reputation,
            "change": new_reputation - old_reputation,
            "reason": reason,
        },
    )


async def notify_job_progress(
    job_id: str,
    completed_chunks: int,
    total_chunks: int,
    status: str,
) -> None:
    """Notify about job progress."""
    await manager.send_event(
        EventType.JOB_PROGRESS,
        {
            "job_id": job_id,
            "completed_chunks": completed_chunks,
            "total_chunks": total_chunks,
            "progress_percent": round(completed_chunks / total_chunks * 100, 1) if total_chunks > 0 else 0,
            "status": status,
        },
        room=f"job:{job_id}",
    )


async def notify_system_alert(alert_type: str, message: str, severity: str = "info") -> None:
    """Send system alert to all clients."""
    await manager.send_event(
        EventType.SYSTEM_ALERT,
        {
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
        },
    )


# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@ws_router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection status."""
    return manager.get_stats()
