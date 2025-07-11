# wait_start_robot.py (CamNode上で実行)
import socket
import subprocess
import os
import sys
import time

# --- ルーティングデーモン関連の設定 (共通) ---
ROUTING_DAEMON_PATH = os.path.join(os.path.dirname(__file__), 'node.py')
MY_NODE_ID = 3 # CamNodeのNode ID

routing_daemon_process = None

def start_routing_daemon(node_id):
    global routing_daemon_process
    if not os.path.exists(ROUTING_DAEMON_PATH):
        print(f"エラー: ルーティングデーモンのパスが見つかりません: {ROUTING_DAEMON_PATH}")
        sys.exit(1)
    print(f"Node {node_id}: ルーティングデーモンを起動します...")
    routing_daemon_process = subprocess.Popen(
        ['sudo', 'python3', ROUTING_DAEMON_PATH, str(node_id)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    print(f"Node {node_id}: ルーティングデーモン PID: {routing_daemon_process.pid} で起動しました。")

def stop_routing_daemon():
    global routing_daemon_process
    if routing_daemon_process and routing_daemon_process.poll() is None:
        print("ルーティングデーモンを終了します...")
        try:
            routing_daemon_process.terminate()
            routing_daemon_process.wait(timeout=5)
            if routing_daemon_process.poll() is None:
                print("ルーティングデーモンを強制終了します。")
                routing_daemon_process.kill()
        except Exception as e:
            print(f"ルーティングデーモン終了中にエラーが発生しました: {e}")
    else:
        print("ルーティングデーモンは実行中ではありません。")
# --- ルーティングデーモン関連の設定ここまで ---

HOST = '0.0.0.0'
PORT = 5000 # カメラロボットの起動信号待ち受けポートは変更なし

start_routing_daemon(MY_NODE_ID)

print("CamNode：起動信号を待機中...")

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(1)
        conn, addr = s.accept()
        with conn:
            print(f"{addr} から接続されました")
            data = conn.recv(1024)
            if b'start' in data:
                print("起動信号を受信しました，camera_robot.py を実行します")
                # camera_robot.py のパスが異なる場合は修正
                subprocess.run(["python3", "camera_robot.py"]) 

except Exception as e:
    print(f"エラーが発生しました: {e}")

finally:
    stop_routing_daemon()
    print("wait_start_robot.py 終了。")