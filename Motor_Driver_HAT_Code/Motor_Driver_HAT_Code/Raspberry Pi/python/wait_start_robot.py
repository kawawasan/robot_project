# wait_start_robot.py
#rear_robot.pyからの信号を待機し、camera_robot.pyを動かす(200.3)
import socket
import subprocess
import os
import time
import sys

# --- ルーティングデーモン関連の設定 (共通) ---
ROUTING_DAEMON_PATH = os.path.join(os.path.dirname(__file__), 'node.py')
MY_NODE_ID = 2 # カメラロボットのNode ID
CAMERA_ROBOT_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'camera_ex.py')
#　実験用ファイル指定
# CAMERA_ROBOT_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'camera_robot.py')


HOST = '0.0.0.0'  # 全てのネットワークインターフェースで待機
PORT = 5000       # 待機するポート番号 (ctlNodeやrear_robotと合わせる)

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

# ルーティングデーモンをここで起動！
try:
    start_routing_daemon(MY_NODE_ID)
except Exception as e:
    print(f"ルーティングデーモンの起動に失敗しました: {e}")
    sys.exit(1)

print("前方ロボット：起動信号を待機中...")

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
                if not os.path.exists(CAMERA_ROBOT_SCRIPT_PATH):
                    print(f"エラー: camera_robot.py が見つかりません: {CAMERA_ROBOT_SCRIPT_PATH}")
                else:
                    # camera_robot.py を実行。この呼び出しはcamera_robot.pyが終了するまでブロックします。
                    subprocess.run(["python3", CAMERA_ROBOT_SCRIPT_PATH], check=True)

except Exception as e:
    print(f"エラーが発生しました: {e}")

finally:
    stop_routing_daemon() # ルーティングデーモンを終了
    print("wait_start_robot.py 終了。")


#カメラロボットのみ動かす時のやつ、ルーティングなし
# HOST = '0.0.0.0'  # 全インターフェースで待機
# PORT = 5000       # 後方ロボットと合わせる

# # ROUTING_DAMON_PATH = "/home/pi/robot_project/Motor_Driver_HAT_Code/Motor_Driver_HAT_Code/Raspberry Pi/python/node.py"
# # MY_NODE_ID = 1

# print("前方ロボット：後方からの起動信号を待機中...")

# with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#     s.bind((HOST, PORT))
#     s.listen(1)
#     conn, addr = s.accept()
#     with conn:
#         print(f"{addr} から接続されました")
#         data = conn.recv(1024)
#         if b'start' in data:
#             print("起動信号を受信しました，camera_robot.py を実行します")
#             subprocess.run(["python3", "camera_robot.py"])
