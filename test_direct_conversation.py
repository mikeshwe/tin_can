#!/usr/bin/env python3
"""
Test script for direct connection AI-to-AI conversation.
Launches both agents with direct room connection, bypassing the worker framework.
"""
import asyncio
import subprocess
import sys
import time
import os
from datetime import datetime
from livekit import api

# Room name that BOTH agents will connect to
ROOM_NAME = f"direct-conversation-{int(time.time())}"

def print_banner(text):
    print("\n" + "="*60)
    print(text)
    print("="*60 + "\n")

def generate_web_token(room_name):
    """Generate a token for web client to observe the conversation."""
    from dotenv import load_dotenv
    load_dotenv()

    token = api.AccessToken(
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET")
    )
    token.with_identity("web-observer")
    token.with_name("Web Observer")
    token.with_grants(
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_subscribe=True,
        )
    )
    return token.to_jwt()

async def main():
    print_banner("Direct Connection AI-to-AI Conversation Test")
    print(f"Room: {ROOM_NAME}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Launch doctor agent with direct connection
    print("Launching Doctor Agent (direct connection)...")
    doctor = subprocess.Popen(
        [sys.executable, "direct_doctor_agent.py", ROOM_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    print(f"  Doctor PID: {doctor.pid}")

    # Wait for doctor to connect
    await asyncio.sleep(3)

    # Launch patient agent with direct connection
    print("\nLaunching Patient Agent (direct connection)...")
    patient = subprocess.Popen(
        [sys.executable, "direct_patient_agent.py", ROOM_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    print(f"  Patient PID: {patient.pid}")

    print_banner("Both Agents Running!")

    # Generate web client token
    web_token = generate_web_token(ROOM_NAME)
    livekit_url = os.getenv("LIVEKIT_URL", "wss://tincan-mwvmg0g6.livekit.cloud")

    print(f"Room Name: {ROOM_NAME}")
    print(f"LiveKit URL: {livekit_url}")
    print(f"\nWeb Client URL:")
    print(f"file://{os.getcwd()}/web_client.html?room={ROOM_NAME}&token={web_token}")
    print("\nThe agents should now be talking to each other.")
    print("Press Ctrl+C to stop.\n")

    # Monitor agent output
    async def monitor_output(proc, name):
        """Monitor and print agent output."""
        while True:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                await asyncio.sleep(0.1)
                continue
            print(f"[{name}] {line.rstrip()}")

    # Create monitoring tasks
    doctor_monitor = asyncio.create_task(monitor_output(doctor, "DOCTOR"))
    patient_monitor = asyncio.create_task(monitor_output(patient, "PATIENT"))

    try:
        # Wait for both processes
        while True:
            doc_status = doctor.poll()
            pat_status = patient.poll()

            if doc_status is not None:
                print(f"\nDoctor agent exited with code: {doc_status}")
            if pat_status is not None:
                print(f"\nPatient agent exited with code: {pat_status}")

            if doc_status is not None and pat_status is not None:
                break

            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping agents...")
        doctor.terminate()
        patient.terminate()
        await asyncio.sleep(2)
        if doctor.poll() is None:
            doctor.kill()
        if patient.poll() is None:
            patient.kill()
        print("Agents stopped.")
    finally:
        # Cancel monitoring tasks
        doctor_monitor.cancel()
        patient_monitor.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
