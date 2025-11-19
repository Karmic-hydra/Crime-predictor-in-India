#!/usr/bin/env bash
# Render build script - runs before starting the app

set -o errexit  # Exit on error

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Training ML models (if needed)..."
python train_model.py

echo "Build completed successfully!"
