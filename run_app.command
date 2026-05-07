#!/bin/bash

cd "$(dirname "$0")"

echo "Starting Daily AFC CallList Engine..."
echo ""

if ! command -v python3 &> /dev/null
then
    echo "Python 3 is not installed."
    echo "Please install Python 3 and try again."
    read -p "Press Enter to close..."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating local Python environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing required packages..."
pip install -r requirements.txt

echo "Setting up local database..."
python setup_db.py

echo "Opening app at http://127.0.0.1:8501"
echo ""

python -m streamlit run app.py --server.address 127.0.0.1