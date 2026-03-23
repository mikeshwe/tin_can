#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Set SSL certificate path
export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")
export REQUESTS_CA_BUNDLE=$(python -c "import certifi; print(certifi.where())")

# Run the orchestrator
python orchestrator.py
