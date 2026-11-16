#!/bin/zsh
cd "$(dirname "$0")"
echo "Đang khởi động Hưng Phát AI Agent trên localhost..."
python3 app.py --host 127.0.0.1 --port 8000 --open || python3 app.py --host 127.0.0.1 --port 8001 --open
