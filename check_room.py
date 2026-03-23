import asyncio
from livekit import api
import os
from dotenv import load_dotenv

load_dotenv()

async def check_room(room_name):
    livekit_api = api.LiveKitAPI(
        os.getenv("LIVEKIT_URL"),
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET"),
    )

    try:
        # List all rooms
        from livekit.protocol import room as proto_room
        response = await livekit_api.room.list_rooms(proto_room.ListRoomsRequest())
        print(f"\n=== All Active Rooms ===")
        for room in response.rooms:
            print(f"  Room: {room.name}")
            print(f"    - SID: {room.sid}")
            print(f"    - Created: {room.creation_time}")
            print(f"    - Participants: {room.num_participants}")
            print()

        # Check specific room
        print(f"\n=== Checking Room: {room_name} ===")
        try:
            from livekit.protocol import room as proto_room
            response = await livekit_api.room.list_participants(
                proto_room.ListParticipantsRequest(room=room_name)
            )
            participants = response.participants
            print(f"  Found {len(participants)} participants:")
            for p in participants:
                print(f"    - {p.identity} (SID: {p.sid})")
                print(f"      State: {p.state}")
                print(f"      Joined: {p.joined_at}")
        except Exception as e:
            print(f"  Error checking room: {e}")

    except Exception as e:
        print(f"Error listing rooms: {e}")
    finally:
        await livekit_api.aclose()

if __name__ == "__main__":
    import sys
    room_name = sys.argv[1] if len(sys.argv) > 1 else "appointment-scheduling-1769401430"
    asyncio.run(check_room(room_name))
