#!/bin/bash
echo "Starting ATL01 Data Center Model..."
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt
echo ""
echo "Launching application..."
streamlit run app/Data_Center_Model.py