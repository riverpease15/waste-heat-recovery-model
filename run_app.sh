#!/bin/bash
echo "Starting ATL01 Thermal Model..."
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt
echo ""
echo "Launching application..."
streamlit run thermal_model_streamlit.py