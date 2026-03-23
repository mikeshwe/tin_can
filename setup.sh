#!/bin/bash

# Setup script for AI-to-AI Voice Scheduling Prototype

echo "=========================================="
echo "AI-to-AI Voice Scheduling Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

if [ $? -ne 0 ]; then
    echo "Error: Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "=========================================="
    echo "IMPORTANT: Configure your .env file"
    echo "=========================================="
    echo "Please edit the .env file and add your API keys:"
    echo "  - LiveKit credentials"
    echo "  - Groq API key"
    echo "  - Deepgram API key"
    echo "  - Calendly API key"
    echo "  - Supabase credentials"
    echo ""
else
    echo ""
    echo ".env file already exists. Skipping creation."
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API credentials"
echo "2. Run the database_setup.sql in your Supabase SQL editor"
echo "3. Activate the virtual environment: source venv/bin/activate"
echo "4. Run the prototype: python orchestrator.py"
echo ""
