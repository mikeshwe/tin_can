"""Monitor a LiveKit room and print participant activity."""
import asyncio
import os
import sys

# Set SSL environment variables BEFORE any other imports
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except ImportError:
    pass

from dotenv import load_dotenv
from livekit import rtc, api

load_dotenv()


async def monitor_room(room_name: str):
    """Connect to a room and monitor activity."""

    # Get LiveKit credentials
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    # Create an access token for monitoring
    from livekit.api import AccessToken, VideoGrants

    token = AccessToken(api_key, api_secret)
    token.with_identity("monitor")
    token.with_name("Room Monitor")
    token.with_grants(VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=False,
        can_subscribe=True,
    ))

    # Connect to the room
    room = rtc.Room()

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        print(f"\n[CONNECTED] {participant.identity}")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        print(f"\n[DISCONNECTED] {participant.identity}")

    @room.on("track_published")
    def on_track_published(publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"\n[TRACK PUBLISHED] {participant.identity}: {publication.kind} track ({publication.sid})")

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"\n[TRACK SUBSCRIBED] {participant.identity}: {track.kind} track")

        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"  -> Audio stream active from {participant.identity}")

    @room.on("active_speakers_changed")
    def on_active_speakers_changed(speakers: list):
        if speakers:
            speaker_ids = [s.identity for s in speakers]
            print(f"\n[SPEAKING] {', '.join(speaker_ids)}")

    print(f"Connecting to room: {room_name}...")
    print(f"URL: {url}\n")

    try:
        await room.connect(url, token.to_jwt())
        print(f"✅ Connected successfully!")
        print(f"Room: {room.name}")
        print(f"Participants: {len(room.remote_participants)}")

        for participant in room.remote_participants.values():
            print(f"  - {participant.identity}")
            for pub in participant.track_publications.values():
                print(f"    * {pub.kind} track ({pub.sid})")

        print("\nMonitoring room activity... (Press Ctrl+C to stop)\n")

        # Keep the connection alive
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        await room.disconnect()
        print("Disconnected from room.")


if __name__ == "__main__":
    room_name = sys.argv[1] if len(sys.argv) > 1 else "appointment-scheduling-1769400142"
    asyncio.run(monitor_room(room_name))
