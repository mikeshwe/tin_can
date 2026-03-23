#!/usr/bin/env python3
"""
Refresh the web monitor interface with the current active LiveKit room.
This script:
1. Checks for active LiveKit rooms
2. Generates a new token for the most recent room
3. Updates monitor_current_session.html
4. Opens the interface in your browser
"""
import asyncio
import os
import subprocess
from dotenv import load_dotenv
from livekit import api
from livekit.api import AccessToken, VideoGrants

load_dotenv()


async def get_active_rooms():
    """Get list of all active LiveKit rooms."""
    livekit_api = api.LiveKitAPI(
        os.getenv("LIVEKIT_URL"),
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET"),
    )

    try:
        from livekit.protocol import room as proto_room
        response = await livekit_api.room.list_rooms(proto_room.ListRoomsRequest())
        return response.rooms
    except Exception as e:
        print(f"Error listing rooms: {e}")
        return []
    finally:
        await livekit_api.aclose()


def generate_token(room_name: str):
    """Generate an access token for the web client."""
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    token = AccessToken(api_key, api_secret)
    token.with_identity("web-observer")
    token.with_name("Web Observer")
    token.with_grants(VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    ))

    return token.to_jwt()


def update_monitor_html(room_name: str, token: str):
    """Update the monitor_current_session.html file."""
    html_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>Current Session Monitor</title>
    <script>
        // Get token from URL
        const token = '{token}';
        window.location.href = `web_client.html?room={room_name}&token=${{token}}`;
    </script>
</head>
<body>
    <p>Redirecting to current session...</p>
    <p>Room: {room_name}</p>
</body>
</html>
'''

    with open('monitor_current_session.html', 'w') as f:
        f.write(html_content)

    print(f"Updated monitor_current_session.html")


async def main():
    """Main function."""
    print("\n" + "="*60)
    print("Refreshing Web Monitor Interface")
    print("="*60 + "\n")

    # Get active rooms
    print("Checking for active LiveKit rooms...")
    rooms = await get_active_rooms()

    if not rooms:
        print("\nNo active rooms found in LiveKit dashboard.")
        print("Checking for running agent processes...")

        # Try to find room name from running processes
        import subprocess
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            lines = result.stdout.split('\n')
            for line in lines:
                if '--room' in line and ('doctor_agent' in line or 'patient_agent' in line):
                    parts = line.split('--room')
                    if len(parts) > 1:
                        room_name = parts[1].strip().split()[0]
                        print(f"Found room from running process: {room_name}")
                        break
            else:
                print("\nNo running agents found.")
                print("Start a new session with: python orchestrator.py")
                return
        except Exception as e:
            print(f"Error checking processes: {e}")
            print("\nStart a new session with: python orchestrator.py")
            return
    else:
        # Show available rooms
        print(f"\nFound {len(rooms)} active room(s):")
        for i, room in enumerate(rooms, 1):
            print(f"  {i}. {room.name} ({room.num_participants} participants)")

        # Use the most recent room (last in list)
        room_name = rooms[-1].name
        print(f"\nUsing room: {room_name}")

    # Generate token
    print(f"Generating access token for room: {room_name}")
    token = generate_token(room_name)

    # Update HTML file
    update_monitor_html(room_name, token)

    # Print access info
    print("\n" + "="*60)
    print("Web Monitor Ready!")
    print("="*60)
    print(f"Room: {room_name}")
    print(f"URL: {os.getenv('LIVEKIT_URL')}")
    print("\nTo access the monitor:")
    print("1. Open monitor_current_session.html in your browser")
    print("   or")
    print("2. Run: open monitor_current_session.html")
    print("="*60 + "\n")

    # Optionally open in browser
    try:
        subprocess.run(["open", "monitor_current_session.html"], check=False)
        print("Opening monitor in your default browser...")
    except Exception as e:
        print(f"Could not auto-open browser: {e}")
        print("Please open monitor_current_session.html manually.")


if __name__ == "__main__":
    asyncio.run(main())
