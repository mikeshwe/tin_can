import asyncio
import os
from datetime import datetime, timedelta

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
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import deepgram, groq
from livekit.agents.stt import SpeechEventType

load_dotenv()

# Global variables for patient info
PATIENT_NAME = os.getenv("PATIENT_NAME", "John Doe")


def get_patient_availability():
    """Generate 2 upcoming weekday dates as the patient's availability."""
    today = datetime.now()
    dates = []
    i = 1
    while len(dates) < 2:
        future_date = today + timedelta(days=i)
        if future_date.weekday() < 5:  # skip weekends
            dates.append(future_date.strftime('%B %-d'))
        i += 1
    return dates


PATIENT_SYSTEM_PROMPT = f"""You are {PATIENT_NAME} calling a clinic to book an appointment. Be EXTREMELY brief - 1 sentence max.

Rules:
- Your FIRST response after the doctor speaks must ALWAYS be your 2 available dates, no matter what the doctor says. Even if the question sounds like a yes/no, give the dates. Never say "yes" or "they will work" — always say the actual dates.
- When the doctor lists available slots, pick the earliest morning slot (9 AM preferred) on either of your dates. Always include both the date AND time in one sentence, e.g. "March 23rd at 9 AM works for me."
- Only ask for a morning slot if ALL offered times are in the afternoon (after 12 PM).
- If the doctor proposes a date you didn't mention, say that date doesn't work and repeat your 2 dates.
- When the doctor confirms with "Booked" or "See you on", say "Perfect, see you then." and stop.
- NEVER list more than 2 dates. NEVER answer a yes/no question — always give concrete dates or times.

Current date: March 22, 2026.
"""


async def entrypoint(ctx: JobContext):
    """Main entry point for the Patient Agent using lower-level APIs."""
    import sys

    print("Patient Agent: entrypoint called!", flush=True)
    sys.stdout.flush()

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    print("Patient Agent connected to room", flush=True)
    sys.stdout.flush()

    # Create HTTP session for Deepgram
    import aiohttp
    http_session = aiohttp.ClientSession()

    # Create LLM
    llm_instance = groq.LLM(
        model="llama-3.1-8b-instant",
        temperature=0.7,
    )

    # Create STT with HTTP session
    stt = deepgram.STT(model="nova-2", http_session=http_session)

    # Create TTS with HTTP session
    tts = deepgram.TTS(model="aura-athena-en", http_session=http_session)

    # Create initial context for the LLM
    initial_chat_ctx = llm.ChatContext()
    initial_chat_ctx.add_message(role="system", content=PATIENT_SYSTEM_PROMPT)
    # Inject availability at startup so it's always in context
    avail_dates = get_patient_availability()
    initial_chat_ctx.add_message(
        role="system",
        content=f"Your 2 available dates are: {avail_dates[0]} and {avail_dates[1]}. Always mention both when asked for dates."
    )

    print("Patient Agent: Generating initial greeting...", flush=True)
    sys.stdout.flush()

    # Generate initial greeting
    initial_greeting = f"Hello, I'd like to book an appointment for {PATIENT_NAME}."

    # Create audio source for publishing
    audio_source = rtc.AudioSource(24000, 1)
    audio_track = rtc.LocalAudioTrack.create_audio_track("patient-voice", audio_source)

    # Publish the audio track with explicit source
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await ctx.room.local_participant.publish_track(audio_track, options)
    print(f"Patient Agent: Published audio track with source={rtc.TrackSource.SOURCE_MICROPHONE}", flush=True)

    # Subscribe to any agent audio tracks — no presence awareness, just react to audio
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if participant.identity.startswith("web"):
            return  # ignore web observer
        if track.kind == rtc.TrackKind.KIND_AUDIO or int(track.kind) == 1:
            print(f"Patient Agent: Receiving audio from {participant.identity}", flush=True)
            asyncio.create_task(process_audio_track(track, participant, llm_instance, stt, tts, audio_source, initial_chat_ctx))

    for participant in ctx.room.remote_participants.values():
        if participant.identity.startswith("web"):
            continue
        for publication in participant.track_publications.values():
            if publication.track and (publication.track.kind == rtc.TrackKind.KIND_AUDIO or int(publication.track.kind) == 1):
                asyncio.create_task(process_audio_track(publication.track, participant, llm_instance, stt, tts, audio_source, initial_chat_ctx))

    print("Patient Agent: Ready and listening...", flush=True)

    # Brief pause simulating call connecting, then speak — no participant detection needed
    await asyncio.sleep(2)

    print(f"Patient Agent: Speaking - '{initial_greeting}'", flush=True)
    sys.stdout.flush()
    async for audio_chunk in tts.synthesize(initial_greeting):
        await audio_source.capture_frame(audio_chunk.frame)

    print("Patient Agent: Initial greeting sent!", flush=True)
    sys.stdout.flush()

    # Wait indefinitely
    while True:
        await asyncio.sleep(1)


async def process_audio_track(track, participant, llm_instance, stt, tts, audio_source, chat_ctx):
    """Process incoming audio using VAD-driven turn-taking."""
    from livekit.plugins import silero
    from livekit.agents.vad import VADEventType

    print(f"Patient Agent: Processing audio from {participant.identity}")

    audio_stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
    vad_instance = silero.VAD.load()
    vad_stream = vad_instance.stream()
    stt_stream = stt.stream()

    is_speaking = False       # True while we are playing TTS
    conversation_done = False # True after booking confirmed
    accumulated = []          # STT fragments during other agent's speech
    respond_task = None

    async def respond(transcript):
        nonlocal is_speaking, conversation_done
        if conversation_done:
            return
        print(f"Patient Agent heard: {transcript}")
        chat_ctx.add_message(role="user", content=transcript)
        msgs = chat_ctx.messages()
        if len(msgs) > 8:
            system_msgs = [m for m in msgs if m.role == "system"]
            chat_ctx._items = system_msgs + [m for m in msgs if m.role != "system"][-6:]

        try:
            llm_stream = llm_instance.chat(chat_ctx=chat_ctx)
            response_text = ""
            async for chunk in llm_stream:
                if isinstance(chunk, llm.ChatChunk) and chunk.delta and chunk.delta.content:
                    response_text += chunk.delta.content
        except Exception as e:
            print(f"Patient Agent: LLM error: {e}")
            return

        if response_text.strip():
            done_phrases = ["see you then", "see you soon", "goodbye", "that's all"]
            if any(p in response_text.lower() for p in done_phrases):
                conversation_done = True
            print(f"Patient Agent says: {response_text}")
            chat_ctx.add_message(role="assistant", content=response_text)
            is_speaking = True
            try:
                async for audio_chunk in tts.synthesize(response_text):
                    await audio_source.capture_frame(audio_chunk.frame)
            except Exception as e:
                print(f"Patient Agent: TTS error: {e}")
            finally:
                is_speaking = False

    async def forward_audio():
        async for event in audio_stream:
            vad_stream.push_frame(event.frame)
            if not is_speaking:
                stt_stream.push_frame(event.frame)

    async def process_vad():
        nonlocal accumulated, respond_task
        async for event in vad_stream:
            if event.type == VADEventType.START_OF_SPEECH:
                if is_speaking:
                    continue
                if respond_task and not respond_task.done():
                    respond_task.cancel()
                    respond_task = None
                accumulated.clear()
                print("Patient Agent: [VAD] other agent started speaking")

            elif event.type == VADEventType.END_OF_SPEECH:
                if is_speaking:
                    continue
                print("Patient Agent: [VAD] other agent stopped speaking")
                await asyncio.sleep(0.3)
                if accumulated:
                    full_transcript = " ".join(accumulated)
                    accumulated.clear()
                    respond_task = asyncio.create_task(respond(full_transcript))

    async def process_stt():
        nonlocal accumulated
        async for event in stt_stream:
            if event.type == SpeechEventType.FINAL_TRANSCRIPT:
                if is_speaking:
                    continue
                text = event.alternatives[0].text.strip()
                if text:
                    accumulated.append(text)

    await asyncio.gather(forward_audio(), process_vad(), process_stt())


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        ),
    )
