-- Supabase Database Schema for Clinic Availability
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS clinic_availability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slot_start TIMESTAMP NOT NULL,
    slot_end TIMESTAMP NOT NULL,
    is_booked BOOLEAN DEFAULT false,
    patient_name TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create an index for faster queries
CREATE INDEX IF NOT EXISTS idx_slot_start ON clinic_availability(slot_start);
CREATE INDEX IF NOT EXISTS idx_is_booked ON clinic_availability(is_booked);

-- Clear existing data and reseed with current dates
DELETE FROM clinic_availability;

-- Sample data: March–April 2026 weekday morning slots (9 AM, 9:30 AM, 10 AM, 10:30 AM)
INSERT INTO clinic_availability (slot_start, slot_end, is_booked) VALUES
    ('2026-03-23 09:00:00', '2026-03-23 09:30:00', false),
    ('2026-03-23 09:30:00', '2026-03-23 10:00:00', false),
    ('2026-03-23 10:00:00', '2026-03-23 10:30:00', false),
    ('2026-03-23 10:30:00', '2026-03-23 11:00:00', false),
    ('2026-03-24 09:00:00', '2026-03-24 09:30:00', false),
    ('2026-03-24 09:30:00', '2026-03-24 10:00:00', false),
    ('2026-03-24 10:00:00', '2026-03-24 10:30:00', false),
    ('2026-03-24 10:30:00', '2026-03-24 11:00:00', false),
    ('2026-03-25 09:00:00', '2026-03-25 09:30:00', false),
    ('2026-03-25 09:30:00', '2026-03-25 10:00:00', false),
    ('2026-03-26 09:00:00', '2026-03-26 09:30:00', false),
    ('2026-03-26 09:30:00', '2026-03-26 10:00:00', false),
    ('2026-03-27 09:00:00', '2026-03-27 09:30:00', false),
    ('2026-03-27 09:30:00', '2026-03-27 10:00:00', false),
    ('2026-03-30 09:00:00', '2026-03-30 09:30:00', false),
    ('2026-03-30 09:30:00', '2026-03-30 10:00:00', false),
    ('2026-03-31 09:00:00', '2026-03-31 09:30:00', false),
    ('2026-03-31 09:30:00', '2026-03-31 10:00:00', false),
    ('2026-04-01 09:00:00', '2026-04-01 09:30:00', false),
    ('2026-04-01 09:30:00', '2026-04-01 10:00:00', false),
    ('2026-04-02 09:00:00', '2026-04-02 09:30:00', false),
    ('2026-04-02 09:30:00', '2026-04-02 10:00:00', false),
    ('2026-04-03 09:00:00', '2026-04-03 09:30:00', false),
    ('2026-04-03 09:30:00', '2026-04-03 10:00:00', false);
