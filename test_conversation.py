#!/usr/bin/env python3
"""
Simple test script to demonstrate AI-to-AI conversation.
This connects both agents to the SAME room to ensure they can talk to each other.
"""
import asyncio
import subprocess
import sys
import time
from datetime import datetime

# Room name that BOTH agents will connect to
ROOM_NAME = f"ai-conversation-{int(time.time())}"

def print_banner(text):
    print("\n" + "="*60)
    print(text)
    print("="*60 + "\n")

async def main():
    print_banner("Starting AI-to-AI Conversation Test")
    print(f"Room: {ROOM_NAME}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Launch doctor agent
    print("Launching Doctor Agent...")
    doctor = subprocess.Popen(
        [sys.executable, "doctor_agent.py", "connect", "--room", ROOM_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    print(f"  Doctor PID: {doctor.pid}")

    # Wait for doctor to connect
    await asyncio.sleep(3)

    # Launch patient agent
    print("\nLaunching Patient Agent...")
    patient = subprocess.Popen(
        [sys.executable, "patient_agent.py", "connect", "--room", ROOM_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    print(f"  Patient PID: {patient.pid}")

    print_banner("Both Agents Running!")
    print(f"Room Name: {ROOM_NAME}")
    print(f"LiveKit URL: wss://tincan-mwvmg0g6.livekit.cloud")
    print("\nThe agents should now be talking to each other.")
    print("Press Ctrl+C to stop.\n")

    try:
        # Monitor both processes
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

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
