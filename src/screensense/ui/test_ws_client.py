import asyncio
import websockets
import json

async def receive_state():
    uri = "ws://localhost:8765"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Waiting for state updates...")
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"State Update: {data['status']} | Text: {data.get('text', '')}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(receive_state())
