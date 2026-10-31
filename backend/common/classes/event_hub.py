from fastapi import WebSocket, WebSocketDisconnect


class EventHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        self.clients.add(socket)

    def disconnect(self, socket: WebSocket) -> None:
        self.clients.discard(socket)

    async def broadcast(self, event: dict) -> None:
        stale = []
        for client in tuple(self.clients):
            try:
                await client.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                stale.append(client)
        for client in stale:
            self.disconnect(client)
