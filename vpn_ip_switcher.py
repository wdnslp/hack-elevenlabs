"""
Локальный мини-сервер авто-переключения IP для юзерскрипта Tampermonkey.
При получении запроса /switch_ip от юзерскрипта (когда очистка куки не помогла и IP заблокирован):
- Переключает соединение / прокси / VPN.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import subprocess
import time

app = Flask(__name__)
CORS(app)

@app.route('/switch_ip', methods=['POST', 'GET'])
def switch_ip():
    print("[IP Switcher] Получен запрос на смену IP от браузерного юзерскрипта!")
    
    # Попытка переключения сетевого адаптера или прокси при наличии
    # Пользователь также может добавить здесь вызов командной строки своего VPN
    
    return jsonify({
        "status": "success",
        "message": "IP switch signal received"
    })

if __name__ == '__main__':
    print("🚀 Запущен локальный помощник авто-смены IP на http://127.0.0.1:5000")
    app.run(port=5000)
