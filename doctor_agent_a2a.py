import asyncio
import os
from datetime import datetime

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
from livekit.agents.stt import SpeechEventType
from livekit.plugins import deepgram, groq
from supabase import create_client, Client

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


@llm.function_tool()
async def query_database(date: str):
    """Query the clinic database for available appointment slots on a specific date."""
    try:
        response = supabase.table('clinic_availability').select('*').eq(
            'is_booked', False
        ).gte(
            'slot_start', f'{date} 00:00:00'
        ).lt(
            'slot_start', f'{date} 23:59:59'
        ).order('slot_start').execute()

        slots = []
        for record in response.data:
            slot_start = datetime.fromisoformat(record['slot_start'])
            slots.append({
                'id': record['id'],
                'time': slot_start.strftime('%I:%M %p'),
            })

        return {
            'success': True,
            'date': date,
            'available_slots': slots,
            'count': len(slots),
            'message': f"Found {len(slots)} available slots on {date}"
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@llm.function_tool()
async def write_booking(date: str, time: str, patient_name: str):
    """Book an appointment slot for a patient."""
    try:
        # Normalise time to 24-hour HH:MM:SS for DB lookup (handles "9:00 AM", "09:00", "9:00")
        from datetime import datetime as _dt
        for fmt in ('%I:%M %p', '%H:%M', '%I %p'):
            try:
                slot_datetime = f'{date} ' + _dt.strptime(time.strip(), fmt).strftime('%H:%M:%S')
                break
            except ValueError:
                continue
        else:
            slot_datetime = f'{date} {time}:00'

        response = supabase.table('clinic_availability').select('*').eq(
            'is_booked', False
        ).eq(
            'slot_start', slot_datetime
        ).execute()

        if not response.data:
            return {
                'success': False,
                'error': 'Slot not found or already booked'
            }

        slot_id = response.data[0]['id']

        supabase.table('clinic_availability').update({
            'is_booked': True,
            'patient_name': patient_name
        }).eq('id', slot_id).execute()

        return {
            'success': True,
            'message': f'Appointment confirmed for {patient_name} on {date} at {time}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


DOCTOR_SYSTEM_PROMPT = """Clinic scheduler. Ultra-brief (1 sentence max). Today is March 22, 2026. All dates are in 2026. Always speak dates naturally, like "March 24th" or "March 24th at 9 AM" — never read out ISO formats like "2026-03-24". Steps: 1) Ask what dates work. 2) Call query_database for each date mentioned (format 2026-MM-DD). 3) Propose slots ONLY from the dates the patient gave you — if the DB query fails or returns no slots, assume 9 AM is available on those dates. NEVER suggest a date the patient did not mention. 4) Call write_booking with the slot the patient picks. 5) Say "Booked! See you on [date] at [time]." then STOP completely."""


async def entrypoint(ctx: JobContext):
    """Main entry point for the Doctor Agent using lower-level APIs."""
    import sys

    print("Doctor Agent: entrypoint called!", flush=True)
    sys.stdout.flush()

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    print("Doctor Agent connected to room", flush=True)
    sys.stdout.flush()

    # Create HTTP session for Deepgram
    import aiohttp
    http_session = aiohttp.ClientSession()

    # Create LLM
    llm_instance = groq.LLM(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
    )

    # Create STT with HTTP session
    stt = deepgram.STT(model="nova-2", http_session=http_session)

    # Create TTS with HTTP session
    tts = deepgram.TTS(model="aura-asteria-en", http_session=http_session)

    # Create initial context for the LLM
    initial_chat_ctx = llm.ChatContext()
    initial_chat_ctx.add_message(role="system", content=DOCTOR_SYSTEM_PROMPT)

    # Create audio source for publishing
    audio_source = rtc.AudioSource(24000, 1)
    audio_track = rtc.LocalAudioTrack.create_audio_track("doctor-voice", audio_source)

    # Publish the audio track with explicit source
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await ctx.room.local_participant.publish_track(audio_track, options)
    print(f"Doctor Agent: Published audio track with source={rtc.TrackSource.SOURCE_MICROPHONE}", flush=True)

    print("Doctor Agent: Ready and listening...", flush=True)
    sys.stdout.flush()

    # Subscribe to any incoming audio — no presence awareness, just react to audio
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if participant.identity.startswith("web"):
            return  # ignore web observer
        if track.kind == rtc.TrackKind.KIND_AUDIO or int(track.kind) == 1:
            print(f"Doctor Agent: Receiving audio from {participant.identity}", flush=True)
            asyncio.create_task(process_audio_track(track, participant, llm_instance, stt, tts, audio_source, initial_chat_ctx))

    # Keep the agent running
    while True:
        await asyncio.sleep(1)


async def process_audio_track(track, participant, llm_instance, stt, tts, audio_source, chat_ctx):
    """Process incoming audio using VAD-driven turn-taking."""
    import sys, json
    from livekit.plugins import silero
    from livekit.agents.vad import VADEventType

    print(f"Doctor Agent: Processing audio from {participant.identity}", flush=True)

    audio_stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
    vad_instance = silero.VAD.load()
    vad_stream = vad_instance.stream()
    stt_stream = stt.stream()

    is_speaking = False      # True while we are playing TTS
    booking_done = False     # True after write_booking succeeds
    accumulated = []         # STT fragments collected during other agent's speech
    respond_task = None      # Pending respond coroutine

    async def run_llm_with_tools(ctx):
        nonlocal booking_done
        response_text = ""
        for _ in range(5):
            stream = llm_instance.chat(chat_ctx=ctx, tools=[query_database, write_booking])
            all_tool_calls = []
            text_this_round = ""
            async for chunk in stream:
                if isinstance(chunk, llm.ChatChunk) and chunk.delta:
                    if chunk.delta.content:
                        text_this_round += chunk.delta.content
                    if chunk.delta.tool_calls:
                        all_tool_calls.extend(chunk.delta.tool_calls)
            if all_tool_calls:
                fnc_calls = []
                for tc in all_tool_calls:
                    print(f"Doctor Agent: Executing {tc.name} with args: {tc.arguments}")
                    fc = llm.FunctionCall(call_id=tc.call_id, name=tc.name, arguments=tc.arguments or "{}")
                    fnc_calls.append(fc)
                    ctx._items.append(fc)
                for fc in fnc_calls:
                    try:
                        args = json.loads(fc.arguments)
                    except Exception:
                        args = {}
                    if fc.name == "query_database":
                        result = await query_database(**args)
                    elif fc.name == "write_booking":
                        result = await write_booking(**args)
                        if result.get("success"):
                            booking_done = True
                    else:
                        result = {"error": "Unknown function"}
                    print(f"Doctor Agent: {fc.name} result: {result}")
                    ctx._items.append(llm.FunctionCallOutput(
                        call_id=fc.call_id, name=fc.name, output=str(result), is_error=False))
                continue
            else:
                response_text = text_this_round
                break
        return response_text

    async def respond(transcript):
        nonlocal is_speaking, booking_done
        if booking_done:
            return
        print(f"Doctor Agent heard: {transcript}")
        chat_ctx.add_message(role="user", content=transcript)
        msgs = chat_ctx.messages()
        if len(msgs) > 6:
            system_msgs = [m for m in msgs if m.role == "system"]
            chat_ctx._items = system_msgs + [m for m in msgs if m.role != "system"][-4:]
        try:
            response_text = await run_llm_with_tools(chat_ctx)
        except Exception as e:
            import traceback
            print(f"Doctor Agent: LLM error: {e}")
            traceback.print_exc()
            return
        if response_text.strip():
            print(f"Doctor Agent says: {response_text}")
            chat_ctx.add_message(role="assistant", content=response_text)
            # If the response is a booking confirmation, stop after speaking it
            response_lower = response_text.lower()
            if any(phrase in response_lower for phrase in ['booked', 'see you on', 'confirmed', 'appointment is set']):
                booking_done = True
            is_speaking = True
            try:
                async for audio_chunk in tts.synthesize(response_text):
                    await audio_source.capture_frame(audio_chunk.frame)
            except Exception as e:
                print(f"Doctor Agent: TTS error: {e}")
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
                    continue  # Other agent started speaking while we're talking — ignore
                # Cancel any pending response — other agent is still speaking
                if respond_task and not respond_task.done():
                    respond_task.cancel()
                    respond_task = None
                accumulated.clear()
                print("Doctor Agent: [VAD] other agent started speaking")

            elif event.type == VADEventType.END_OF_SPEECH:
                if is_speaking:
                    continue
                print("Doctor Agent: [VAD] other agent stopped speaking")
                # Wait briefly for STT to finish, then collect transcript
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
