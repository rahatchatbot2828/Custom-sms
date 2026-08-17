#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, jsonify, render_template_string
import subprocess
import sys
import os
import threading
import time

app = Flask(__name__)

# Bot process management
bot_process = None
bot_status = {
    'running': False,
    'start_time': None,
    'restart_count': 0,
    'last_error': None
}

def install_dependencies():
    """Install required packages for bot"""
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-telegram-bot aiohttp requests'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def start_bot():
    """Start bot.py in background"""
    global bot_process
    
    if bot_process and bot_process.poll() is None:
        return True
    
    try:
        bot_process = subprocess.Popen(
            [sys.executable, 'bot.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        bot_status['running'] = True
        bot_status['start_time'] = time.time()
        bot_status['restart_count'] += 1
        return True
    except Exception as e:
        bot_status['last_error'] = str(e)
        bot_status['running'] = False
        return False

def monitor_bot():
    """Monitor bot process and restart if crashed"""
    global bot_process
    
    while True:
        if bot_process and bot_process.poll() is not None:
            # Bot crashed, restart
            print("Bot crashed! Restarting...")
            bot_status['running'] = False
            start_bot()
        time.sleep(30)

@app.route('/')
def home():
    """Home page"""
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Telegram Bot - Running</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                    width: 100%;
                }
                .status-icon {
                    font-size: 60px;
                    margin-bottom: 20px;
                    animation: pulse 2s infinite;
                }
                @keyframes pulse {
                    0% { transform: scale(1); }
                    50% { transform: scale(1.1); }
                    100% { transform: scale(1); }
                }
                h1 {
                    color: #333;
                    margin-bottom: 10px;
                    font-size: 28px;
                }
                .status {
                    display: inline-block;
                    background: #4CAF50;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 25px;
                    font-weight: bold;
                    margin: 10px 0;
                }
                .info {
                    color: #666;
                    margin: 15px 0;
                    line-height: 1.6;
                }
                .uptime {
                    background: #f0f0f0;
                    padding: 15px;
                    border-radius: 10px;
                    margin: 20px 0;
                    font-family: monospace;
                    font-size: 14px;
                }
                .footer {
                    color: #999;
                    font-size: 12px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="status-icon">🤖</div>
                <h1>Telegram Bot</h1>
                <div class="status">🟢 Bot Running</div>
                <div class="info">
                    Your bot is active and working 24/7<br>
                    Force Join: @CODE_X_RAHAT
                </div>
                <div class="uptime">
                    Status: Active<br>
                    Uptime: <span id="uptime">Calculating...</span>
                </div>
                <div class="footer">
                    Powered by Render • Auto-restart enabled
                </div>
            </div>
            <script>
                function updateUptime() {
                    fetch('/health')
                        .then(response => response.json())
                        .then(data => {
                            if (data.uptime_seconds) {
                                const hours = Math.floor(data.uptime_seconds / 3600);
                                const minutes = Math.floor((data.uptime_seconds % 3600) / 60);
                                const seconds = Math.floor(data.uptime_seconds % 60);
                                document.getElementById('uptime').textContent = 
                                    `${hours}h ${minutes}m ${seconds}s`;
                            }
                        });
                }
                updateUptime();
                setInterval(updateUptime, 1000);
            </script>
        </body>
        </html>
    ''')

@app.route('/health')
def health():
    """Health check endpoint for UptimeRobot"""
    uptime_seconds = int(time.time() - bot_status['start_time']) if bot_status['start_time'] else 0
    
    return jsonify({
        'status': 'ok',
        'bot_running': bot_status['running'],
        'uptime_seconds': uptime_seconds,
        'restart_count': bot_status['restart_count']
    })

@app.route('/status')
def status():
    """Detailed status page"""
    uptime_seconds = int(time.time() - bot_status['start_time']) if bot_status['start_time'] else 0
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    
    return jsonify({
        'bot_running': bot_status['running'],
        'uptime': f"{hours}h {minutes}m {seconds}s",
        'restart_count': bot_status['restart_count'],
        'last_error': bot_status['last_error']
    })

@app.route('/restart')
def restart():
    """Manual restart endpoint"""
    global bot_process
    
    if bot_process:
        bot_process.terminate()
        bot_process = None
    
    success = start_bot()
    return jsonify({'restarted': success})

if __name__ == '__main__':
    print("=" * 50)
    print("     TELEGRAM BOT - WEB SERVER")
    print("=" * 50)
    print()
    print("🚀 Starting web server...")
    print(f"📱 Port: {PORT}")
    print("🤖 Bot monitor: Active")
    print()
    
    # Install dependencies
    print("📦 Checking dependencies...")
    install_dependencies()
    print("✅ Dependencies ready")
    
    # Start bot
    print("🤖 Starting bot...")
    if start_bot():
        print("✅ Bot started successfully")
    else:
        print("❌ Failed to start bot")
    
    # Start monitor thread
    monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
    monitor_thread.start()
    print("🔍 Monitor started")
    
    # Start Flask app
    print(f"🌐 Web server running on port {PORT}")
    print()
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
