#!/usr/bin/env python3
"""
Simple API server to manage A2A agent conversations
"""
import asyncio
import subprocess
import os
import signal
import time
import re
import threading
from flask import Flask, jsonify, request, send_file, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from livekit import api

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

app = Flask(__name__)
CORS(app)  # Enable CORS for web client

# Track current agent processes
current_processes = {
    'orchestrator': None,
    'room_name': None,
    'egress_id': None
}

# Create recordings directory
os.makedirs('recordings', exist_ok=True)


def kill_all_agents():
    """Kill all running agent processes"""
    try:
        # Kill orchestrator if running
        if current_processes['orchestrator']:
            try:
                current_processes['orchestrator'].terminate()
                current_processes['orchestrator'].wait(timeout=2)
            except:
                try:
                    current_processes['orchestrator'].kill()
                    current_processes['orchestrator'].wait(timeout=2)
                except:
                    pass

        # Kill any orphaned agent processes (multiple patterns to catch all)
        kill_commands = [
            "pkill -9 -f 'orchestrator_a2a'",
            "pkill -9 -f 'doctor_agent_a2a'",
            "pkill -9 -f 'patient_agent_a2a'",
            "pkill -9 -f 'appointment-scheduling'",
        ]

        for cmd in kill_commands:
            try:
                subprocess.run(cmd, shell=True, timeout=3)
            except:
                pass

        time.sleep(2)  # Give processes time to die
        print("Killed all agent processes")
    except Exception as e:
        print(f"Error killing agents: {e}")


def generate_access_token(room_name):
    """Generate a LiveKit access token for the room"""
    token = api.AccessToken(
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET")
    )
    token.with_identity("web-observer")
    token.with_name("Web Observer")
    token.with_grants(api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=False,
        can_subscribe=True,
        can_publish_data=False,
    ))

    return token.to_jwt()


async def wait_for_room_to_exist(room_name, max_attempts=20, delay=2):
    """Poll LiveKit API to check if room exists"""
    lk_api = api.LiveKitAPI(
        os.getenv("LIVEKIT_URL"),
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET")
    )

    try:
        for attempt in range(max_attempts):
            try:
                # Try to list rooms and check if our room exists
                rooms = await lk_api.room.list_rooms(api.ListRoomsRequest())
                for room in rooms.rooms:
                    if room.name == room_name:
                        print(f"Room {room_name} found on LiveKit server (attempt {attempt + 1})")
                        return True

                print(f"Room {room_name} not found yet, waiting... (attempt {attempt + 1}/{max_attempts})")
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"Error checking for room (attempt {attempt + 1}): {e}")
                await asyncio.sleep(delay)

        print(f"Room {room_name} not found after {max_attempts} attempts")
        return False
    finally:
        await lk_api.aclose()


async def start_room_egress_async(room_name):
    """Start LiveKit egress to record the room audio (async version)"""
    # First, wait for the room to exist on LiveKit server
    print(f"Waiting for room {room_name} to be established on LiveKit server...")
    room_exists = await wait_for_room_to_exist(room_name)

    if not room_exists:
        print(f"Room {room_name} never appeared on LiveKit server, cannot start recording")
        return None

    # Create API client within async context
    lk_api = api.LiveKitAPI(
        os.getenv("LIVEKIT_URL"),
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET")
    )

    try:
        # Output file configuration
        file_output = api.EncodedFileOutput(
            file_type=api.EncodedFileType.MP4,
            filepath=f"recordings/{room_name}.mp4"
        )

        # Room composite egress request (captures entire room audio)
        request = api.RoomCompositeEgressRequest(
            room_name=room_name,
            audio_only=True,  # Audio only
            file_outputs=[file_output]
        )

        # Start egress
        egress_info = await lk_api.egress.start_room_composite_egress(request)
        print(f"Started egress: {egress_info.egress_id} for room {room_name}")
        return egress_info.egress_id

    except Exception as e:
        print(f"Error starting egress: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await lk_api.aclose()


def start_room_egress_sync(room_name):
    """Synchronous wrapper for start_room_egress_async"""
    try:
        return asyncio.run(start_room_egress_async(room_name))
    except Exception as e:
        print(f"Error in sync wrapper: {e}")
        import traceback
        traceback.print_exc()
        return None


async def stop_room_egress_async(egress_id):
    """Stop LiveKit egress recording (async version)"""
    if not egress_id:
        return

    lk_api = api.LiveKitAPI(
        os.getenv("LIVEKIT_URL"),
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET")
    )

    try:
        await lk_api.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
        print(f"Stopped egress: {egress_id}")
    except Exception as e:
        print(f"Error stopping egress: {e}")
    finally:
        await lk_api.aclose()


def stop_room_egress_sync(egress_id):
    """Synchronous wrapper for stop_room_egress_async"""
    try:
        asyncio.run(stop_room_egress_async(egress_id))
    except Exception as e:
        print(f"Error in stop sync wrapper: {e}")


@app.route('/')
def index():
    """Serve the web client"""
    return send_file('web_client.html')


@app.route('/web_client.html')
def web_client():
    """Serve the web client"""
    response = send_file('web_client.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/api/start-conversation', methods=['POST'])
def start_conversation():
    """Start a new A2A conversation"""
    try:
        # Kill existing agents
        kill_all_agents()

        # Clear log files so transcript stream shows only new session
        for log_file in ['logs/patient_agent_a2a_live.log', 'logs/doctor_agent_a2a_live.log']:
            try:
                open(log_file, 'w').close()
            except Exception:
                pass

        # Start orchestrator in background
        process = subprocess.Popen(
            ['python3', 'orchestrator_a2a.py'],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}
        )

        current_processes['orchestrator'] = process

        # Poll for room name in orchestrator stdout (appears within ~2s)
        room_name = None
        for _ in range(30):  # up to 6 seconds
            time.sleep(0.2)
            try:
                result = subprocess.run(
                    "ps aux | grep 'patient_agent_a2a.py' | grep -v grep | grep -o -- '--room [^ ]*' | awk '{print $2}'",
                    shell=True, capture_output=True, text=True
                )
                room_name = result.stdout.strip() or None
            except Exception:
                pass
            if not room_name:
                try:
                    with open('logs/patient_agent_a2a_live.log', 'r') as f:
                        m = re.search(r'appointment-scheduling-\d+', f.read())
                        if m:
                            room_name = m.group(0)
                except Exception:
                    pass
            if room_name:
                break

        if not room_name:
            room_name = f"a2a-conversation-{int(time.time())}"

        current_processes['room_name'] = room_name

        # Start egress in background so we don't block returning the token
        def start_egress_bg(rn):
            egress_id = start_room_egress_sync(rn)
            current_processes['egress_id'] = egress_id
            if egress_id:
                print(f"Egress started successfully: {egress_id}")
            else:
                print("Warning: Egress failed to start (non-blocking)")
        threading.Thread(target=start_egress_bg, args=(room_name,), daemon=True).start()

        # Generate token for web client immediately
        token = generate_access_token(room_name)

        return jsonify({
            'success': True,
            'room_name': room_name,
            'token': token,
            'ws_url': os.getenv('LIVEKIT_URL'),
            'recording': False
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stop-conversation', methods=['POST'])
def stop_conversation():
    """Stop the current conversation"""
    try:
        # Stop egress if running
        if current_processes.get('egress_id'):
            print(f"Stopping egress: {current_processes['egress_id']}")
            stop_room_egress_sync(current_processes['egress_id'])
            current_processes['egress_id'] = None

        kill_all_agents()
        current_processes['room_name'] = None
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/restart', methods=['POST'])
def restart_demo():
    """Full reset: stop agents, clear logs, then start fresh conversation"""
    try:
        # Stop egress if running
        if current_processes.get('egress_id'):
            stop_room_egress_sync(current_processes['egress_id'])
            current_processes['egress_id'] = None

        kill_all_agents()
        current_processes['room_name'] = None

        # Clear log files
        for log_file in ['logs/patient_agent_a2a_live.log', 'logs/doctor_agent_a2a_live.log']:
            try:
                open(log_file, 'w').close()
            except Exception:
                pass

        # Start fresh orchestrator
        process = subprocess.Popen(
            ['python3', 'orchestrator_a2a.py'],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}
        )
        current_processes['orchestrator'] = process

        # Poll for room name (appears within ~2s, no need to sleep 12s)
        room_name = None
        for _ in range(30):  # up to 6 seconds
            time.sleep(0.2)
            try:
                result = subprocess.run(
                    "ps aux | grep 'patient_agent_a2a.py' | grep -v grep | grep -o -- '--room [^ ]*' | awk '{print $2}'",
                    shell=True, capture_output=True, text=True
                )
                room_name = result.stdout.strip() or None
            except Exception:
                pass
            if not room_name:
                try:
                    with open('logs/patient_agent_a2a_live.log', 'r') as f:
                        m = re.search(r'appointment-scheduling-\d+', f.read())
                        if m:
                            room_name = m.group(0)
                except Exception:
                    pass
            if room_name:
                break

        if not room_name:
            room_name = f"a2a-conversation-{int(time.time())}"

        current_processes['room_name'] = room_name

        # Start egress in background so we don't block returning the token
        def start_egress_bg(rn):
            egress_id = start_room_egress_sync(rn)
            current_processes['egress_id'] = egress_id
            if egress_id:
                print(f"Egress started successfully: {egress_id}")
            else:
                print("Warning: Egress failed to start (non-blocking)")
        threading.Thread(target=start_egress_bg, args=(room_name,), daemon=True).start()

        token = generate_access_token(room_name)

        return jsonify({
            'success': True,
            'room_name': room_name,
            'token': token,
            'ws_url': os.getenv('LIVEKIT_URL'),
            'recording': False
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/recording/<room_name>')
def get_recording(room_name):
    """Get the recorded audio file for a room"""
    try:
        recording_path = f"recordings/{room_name}.mp4"
        if os.path.exists(recording_path):
            return send_file(recording_path, mimetype='audio/mp4')
        else:
            return jsonify({'error': 'Recording not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Get current conversation status"""
    is_running = current_processes['orchestrator'] and current_processes['orchestrator'].poll() is None
    return jsonify({
        'running': is_running,
        'room_name': current_processes['room_name']
    })


def parse_log_line(line):
    """Parse a log line and return structured transcript data"""
    if 'Patient Agent: Speaking' in line:
        match = re.search(r"Speaking - '(.*)'", line)
        if match:
            return {'speaker': 'patient', 'text': match.group(1), 'type': 'says'}
    elif 'Patient Agent says:' in line:
        text = line.split('Patient Agent says:', 1)[1].strip()
        return {'speaker': 'patient', 'text': text, 'type': 'says'}
    elif 'Patient Agent heard:' in line:
        text = line.split('Patient Agent heard:', 1)[1].strip()
        return {'speaker': 'patient', 'text': text, 'type': 'heard'}
    elif 'Doctor Agent says:' in line:
        text = line.split('Doctor Agent says:', 1)[1].strip()
        return {'speaker': 'doctor', 'text': text, 'type': 'says'}
    elif 'Doctor Agent heard:' in line:
        text = line.split('Doctor Agent heard:', 1)[1].strip()
        return {'speaker': 'doctor', 'text': text, 'type': 'heard'}
    return None


@app.route('/api/transcript-stream')
def transcript_stream():
    """Stream transcript updates via Server-Sent Events"""
    def generate():
        import subprocess
        import time
        import json
        import select

        log_files = [
            'logs/patient_agent_a2a_live.log',
            'logs/doctor_agent_a2a_live.log'
        ]

        # Use separate tail processes for each file to avoid filename headers
        processes = []
        for f in log_files:
            p = subprocess.Popen(
                ['tail', '-f', '-n', '+1', f],  # show all lines from beginning
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            processes.append(p)

        # Send keepalive comment first
        yield ': keepalive\n\n'

        try:
            while True:
                # Use select to check which processes have data
                readable, _, _ = select.select(
                    [p.stdout for p in processes], [], [], 1.0
                )
                for stream in readable:
                    line = stream.readline()
                    if line:
                        parsed = parse_log_line(line.strip())
                        if parsed:
                            parsed['ts'] = time.time()
                            yield f"data: {json.dumps(parsed)}\n\n"
                # Send keepalive every second even if no data
                yield ': keepalive\n\n'
        finally:
            for p in processes:
                p.kill()

    return Response(stream_with_context(generate()),
                   mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'X-Accel-Buffering': 'no',
                       'Access-Control-Allow-Origin': '*'
                   })


if __name__ == '__main__':
    print("Starting A2A API Server...")
    print("Access the web client at: http://localhost:5001/web_client.html")
    app.run(host='0.0.0.0', port=5001, debug=False)
