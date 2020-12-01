#!/bin/bash

pip3 install virtualenv

echo "Creating a virtual environment.."
python3 -m venv .env


echo "Activating virtual environment.."
source .env/bin/activate

echo "Installing requirements.."
pip3 install -r requirements.txt
