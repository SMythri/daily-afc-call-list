#!/bin/bash

cd "$(dirname "$0")"

echo "Daily AFC CallList - AFC Import Setup"
echo ""

if [ ! -f "data/afc_homes.csv" ]; then
    echo "Missing AFC file."
    echo ""
    echo "Please place the AFC master file here:"
    echo "data/afc_homes.csv"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

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

echo "Importing AFC master list..."
python import_afc.py

echo ""
echo "AFC import complete."
echo "You can now start the app using run_app.command."
echo ""

read -p "Press Enter to close..."