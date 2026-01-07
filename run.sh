#!/bin/bash
echo "Starting Uni-Video Automation..."

# Check python
if ! command -v python3 &> /dev/null; then
    echo "Python3 could not be found. Please install Python3."
    exit 1
fi

# Install reqs if needed (basic check)
python3 -m pip install -r requirements.txt

# Run
python3 -m app.main
