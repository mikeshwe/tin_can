# System Architecture Document: AI-to-AI Voice Scheduling Prototype

## 1. Executive Summary
This document outlines the architecture for a technical prototype demonstrating two autonomous AI voice agents negotiating an appointment. The Patient Agent retrieves availability from a Calendly account, while the Doctor Agent manages a clinic's schedule via a Supabase database. Both agents interact in real-time over WebRTC.

---

## 2. Core Tech Stack
* **Voice Framework:** Pipecat (Python)
* **Real-Time Communication:** LiveKit (WebRTC)
* **Orchestration:** LiveKit Agents
* **Language Model (LLM):** Groq (Llama 3.3 70B) for low-latency reasoning
* **Speech-to-Text (STT):** Deepgram Nova-2
* **Text-to-Speech (TTS):** Deepgram Aura
* **Calendly Integration:** Calendly V2 API
* **Clinic Backend:** Supabase (PostgreSQL)

Note that one of the constraints for this tech stack is that each of the components had to be available freely or on a sufficiently generous free-tier basis to accommodate prototyping trials.

---

## 3. System Architecture
The system utilizes a central WebRTC room where both agents participate as distinct peers. This bypasses traditional telephony costs and reduces latency.

### 3.1. Component Breakdown

#### A. Patient Agent (The Outbound Agent)
* **Role:** Represents the human patient.
* **Logic:** * Authenticates via Calendly API.
    * Extracts "User Availability" and "Scheduled Events" to determine free blocks.
    * Initiates the conversation once a second participant (Doctor Agent) joins the room.
* **System Prompt:** Instructs the AI to be polite, clear about its owner's constraints, and to confirm the appointment once agreed upon.

#### B. Doctor Agent (The Inbound Agent)
* **Role:** Represents the clinic receptionist.
* **Logic:**
    * Connects to Supabase to query the `clinic_availability` table.
    * Uses function calling (Tool Use) to search for open slots or insert a new booking.
* **System Prompt:** Instructs the AI to act as a professional medical receptionist, verify patient details, and handle scheduling conflicts.

#### C. LiveKit Control Plane
* Handles the audio routing between agents.
* Provides a developer playground for monitoring the interaction.
* Generates the JSON Web Tokens (JWT) required for agents to join the room.

---

## 4. Technical Data Flow

### 4.1. The Handshake Protocol
1. **Initialization:** A Python script spins up two concurrent Pipecat processes.
2. **Room Entry:** Both agents connect to a shared LiveKit room.
3. **Discovery:** The Patient Agent detects the `participant_joined` event for the Doctor Agent.
4. **Opening Move:** The Patient Agent generates a TTS greeting: "Hello, I am the assistant for [Name]. I'd like to book an appointment."
5. **Information Exchange:** * Doctor Agent calls `get_available_slots()`.
    * Patient Agent calls `check_calendly_free_time()`.
6. **Resolution:** Once a mutual slot is found, the Doctor Agent calls `confirm_booking()` in Supabase.

### 4.2. Tool Definitions

**Patient Agent Tools:**
* `get_my_availability()`: Calls `https://api.calendly.com/user_availability_schedules`.
* `notify_owner_success()`: Simulates a notification that the booking is complete.

**Doctor Agent Tools:**
* `query_database(date)`: Performs a SELECT query on Supabase for the specified date.
* `write_booking(date, time, patient_name)`: Performs an INSERT query on Supabase to lock the slot.

---

## 5. Database Schema (Supabase)
```sql
CREATE TABLE clinic_availability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slot_start TIMESTAMP NOT NULL,
    slot_end TIMESTAMP NOT NULL,
    is_booked BOOLEAN DEFAULT false,
    patient_name TEXT DEFAULT NULL
);
```
---

#  Update for A2A architecture

# Architectural Specification: Multi-Agent Voice Handshake (A2A)

## 1. Goal
To simulate an autonomous voice interaction between two distinct organizations (Patient Assistant and Medical Clinic) using the LiveKit Agents Framework. This architecture bypasses the default "ignore agents" filter to allow two AI sessions to communicate in a shared WebRTC room.

---

## 2. Infrastructure & Logic
Each organization runs its own independent worker process. This ensures true "Black Box" interaction where neither AI has access to the other's internal database or context.

### 2.1. The Patient Agent (Outbound Simulator)
* **Organization:** Personal Assistant AI
* **Primary Tool:** Calendly API (v2)
* **Start Condition:** Initiates conversation upon detecting the Doctor Agent.
* **Key Config:** `allow_interruptions=False` (to ensure the initial pitch is heard fully).

### 2.2. The Doctor Agent (Inbound Simulator)
* **Organization:** Clinic Reception AI
* **Primary Tool:** Supabase (PostgreSQL)
* **Start Condition:** Waits for the Patient Agent's greeting.
* **Key Config:** `participant_kinds=[PARTICIPANT_KIND_STANDARD, PARTICIPANT_KIND_AGENT]`.

---

## 3. Implementation Details

### 3.1. Bypassing the AI-to-AI Filter
The core "snag" is resolved by updating the `RoomOptions` during session startup. By default, LiveKit agents only listen to humans. You must explicitly include `PARTICIPANT_KIND_AGENT`.

```python
# Implementation for both Agent entrypoints
from livekit import rtc
from livekit.agents import room_io

async def entrypoint(ctx: JobContext):
    # Initialize your pipeline (STT, LLM, TTS)
    # ...
    
    await session.start(
        agent=your_agent_instance,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            # This allows the agent to hear the other agent
            participant_kinds=[
                rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD,
                rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
            ]
        )
    )