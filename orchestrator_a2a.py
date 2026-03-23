import asyncio
import os
import subprocess
import time
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

from dotenv import load_dotenv, dotenv_values
from livekit import api

# Load with explicit path and override so subprocesses get all keys
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)


class A2AOrchestrator:
    """Orchestrates the LiveKit room and launches both A2A agents."""

    def __init__(self):
        self.livekit_url = os.getenv("LIVEKIT_URL")
        self.livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        self.livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        self.room_name = f"appointment-scheduling-{int(time.time())}"

    async def create_room(self):
        """Create a LiveKit room for the agents."""
        print(f"\n{'='*60}")
        print(f"Creating LiveKit room: {self.room_name}")
        print(f"{'='*60}\n")

        lk_api = api.LiveKitAPI(
            self.livekit_url,
            self.livekit_api_key,
            self.livekit_api_secret,
        )

        try:
            room = await lk_api.room.create_room(
                api.CreateRoomRequest(name=self.room_name)
            )
            print(f"Room created successfully: {room.name}")
            return room
        except Exception as e:
            print(f"Error creating room: {e}")
            raise

    def launch_agent(self, agent_name: str, script_name: str):
        """Launch an agent as a subprocess."""
        print(f"\nLaunching {agent_name}...")

        # Start from all env vars loaded from .env file directly
        env = os.environ.copy()
        env["LIVEKIT_URL"] = self.livekit_url
        env["LIVEKIT_API_KEY"] = self.livekit_api_key
        env["LIVEKIT_API_SECRET"] = self.livekit_api_secret

        # Ensure all .env keys are explicitly forwarded to agent subprocesses
        for key, val in dotenv_values(_env_path).items():
            if val is not None:
                env[key] = val

        # Set SSL certificate path for agents
        try:
            import certifi
            env["SSL_CERT_FILE"] = certifi.where()
            env["REQUESTS_CA_BUNDLE"] = certifi.where()
        except ImportError:
            pass

        # Create log file for this agent
        log_filename = f"logs/{script_name.replace('.py', '')}_live.log"
        log_file = open(log_filename, 'w')

        # Launch the agent with connection to the specific room
        process = subprocess.Popen(
            ["python3", script_name, "connect", "--room", self.room_name],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

        print(f"{agent_name} launched with PID: {process.pid}")
        print(f"  Logs: {log_filename}")
        return process

    async def run(self):
        """Main orchestration flow."""
        print("\n" + "="*60)
        print("AI-to-AI Voice Scheduling (A2A Mode)")
        print("="*60)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")

        # Step 1: Create the room
        try:
            await self.create_room()
        except Exception as e:
            print(f"Failed to create room: {e}")
            return

        # Step 2: Launch both agents
        print("\nLaunching agents...")
        print("-" * 60)

        doctor_process = self.launch_agent("Doctor Agent (A2A)", "doctor_agent_a2a.py")
        await asyncio.sleep(2)  # Give doctor agent time to join first

        patient_process = self.launch_agent("Patient Agent (A2A)", "patient_agent_a2a.py")

        print("\n" + "="*60)
        print("Both A2A agents are now running!")
        print("="*60)
        print(f"\nRoom Name: {self.room_name}")
        print(f"LiveKit URL: {self.livekit_url}")
        print("\nThe patient agent will speak first automatically.")
        print("The agents will converse to schedule an appointment.")
        print("\nPress Ctrl+C to stop all agents and end the session.")
        print("="*60 + "\n")

        # Monitor the processes
        try:
            while True:
                # Check if processes are still running
                doctor_status = doctor_process.poll()
                patient_status = patient_process.poll()

                if doctor_status is not None:
                    print(f"\nDoctor Agent exited with code: {doctor_status}")
                if patient_status is not None:
                    print(f"\nPatient Agent exited with code: {patient_status}")

                if doctor_status is not None and patient_status is not None:
                    print("\nBoth agents have finished. Ending session.")
                    break

                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\n\nShutting down agents...")
            doctor_process.terminate()
            patient_process.terminate()

            # Wait for graceful shutdown
            await asyncio.sleep(2)

            # Force kill if still running
            if doctor_process.poll() is None:
                doctor_process.kill()
            if patient_process.poll() is None:
                patient_process.kill()

            print("All agents stopped.")

        print("\n" + "="*60)
        print("Session ended")
        print("="*60 + "\n")


async def main():
    """Main entry point."""
    orchestrator = A2AOrchestrator()
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
