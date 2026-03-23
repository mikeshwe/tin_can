"""Generate a LiveKit access token for the web client."""
import os
import sys
from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants

load_dotenv()


def generate_token(room_name: str, identity: str = "web-observer"):
    """Generate an access token for joining a LiveKit room."""
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        print("Error: LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in .env")
        sys.exit(1)

    token = AccessToken(api_key, api_secret)
    token.with_identity(identity)
    token.with_name("Web Observer")
    token.with_grants(VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,  # Allow user to speak
        can_subscribe=True,
        can_publish_data=True,
    ))

    jwt_token = token.to_jwt()

    print(f"\n{'='*60}")
    print(f"Access Token Generated")
    print(f"{'='*60}")
    print(f"Room: {room_name}")
    print(f"Identity: {identity}")
    print(f"\nToken:")
    print(jwt_token)
    print(f"\n{'='*60}")
    print(f"\nTo use this token:")
    print(f"1. Open web_client.html in your browser")
    print(f"2. Enter room name: {room_name}")
    print(f"3. Enter WebSocket URL: {os.getenv('LIVEKIT_URL')}")
    print(f"4. Paste the token above")
    print(f"5. Click 'Connect to Room'")
    print(f"{'='*60}\n")

    return jwt_token


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_token.py <room_name>")
        print("\nExample:")
        print("  python generate_token.py appointment-scheduling-1769400142")
        sys.exit(1)

    room_name = sys.argv[1]
    generate_token(room_name)
