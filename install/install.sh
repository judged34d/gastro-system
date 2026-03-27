#!/bin/bash

echo "=== GASTRO SYSTEM INSTALL ==="

# ============================================================
# SYSTEM UPDATE
# ============================================================
sudo apt update && sudo apt upgrade -y

# ============================================================
# INSTALL PYTHON + VENV
# ============================================================
sudo apt install -y python3 python3-venv python3-pip git

# ============================================================
# PROJECT SETUP
# ============================================================
mkdir -p /opt/gastro-system
cd /opt/gastro-system

# ============================================================
# CLONE REPO (PLACEHOLDER)
# ============================================================
if [ ! -d ".git" ]; then
    git clone REPO_URL .
fi

# ============================================================
# VENV
# ============================================================
python3 -m venv venv
source venv/bin/activate

pip install flask flask-cors

# ============================================================
# START BACKEND
# ============================================================
echo "Starte Backend..."

nohup venv/bin/python backend/main.py > backend.log 2>&1 &

# ============================================================
# START FRONTEND
# ============================================================
echo "Starte Frontend..."

nohup python3 -m http.server 8080 --directory frontend > frontend.log 2>&1 &

echo "=== INSTALL DONE ==="
echo "Frontend: http://IP:8080"
echo "Backend: http://IP:8000"
