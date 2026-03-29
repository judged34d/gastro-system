#!/bin/bash

echo "=== GASTRO SYSTEM INSTALL ==="

# ============================================================
# SYSTEM UPDATE
# ============================================================
sudo apt update && sudo apt upgrade -y

# ============================================================
# INSTALL BASICS
# ============================================================
sudo apt install -y python3 python3-venv python3-pip git

# ============================================================
# PROJECT CLONE
# ============================================================
if [ ! -d "/opt/gastro-system" ]; then
    git clone https://github.com/judged34d/gastro-system.git /opt/gastro-system
fi

cd /opt/gastro-system

# ============================================================
# VENV
# ============================================================
python3 -m venv venv
source venv/bin/activate

pip install flask flask-cors

# ============================================================
# START BACKEND
# ============================================================
nohup venv/bin/python backend/main.py > backend.log 2>&1 &

# ============================================================
# START FRONTEND
# ============================================================
nohup python3 -m http.server 8080 --directory frontend > frontend.log 2>&1 &

# ============================================================
# SHOW IP
# ============================================================
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=== INSTALL DONE ==="
echo "Frontend: http://$IP:8080"
echo "Backend: http://$IP:8000"
