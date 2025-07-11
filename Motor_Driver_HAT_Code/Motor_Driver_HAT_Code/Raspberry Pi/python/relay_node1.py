# relay_node1.py (RelayNode1上で実行)
#!/usr/bin/python3
import subprocess
import socket
import time
import signal
import sys
import os
import threading

# PCA9685とgetdist_lidarは適切なパスに配置されている前提
from PCA9685 import PCA9685
from getdist_lidar import get_distance

# --- ルーティングデーモン関連の設定 (共通) ---
ROUTING_DAEMON_PATH = os.path.join(os.path.dirname(__file__), 'node.py')
MY_NODE_ID = 1 # RelayNode1のNode ID

routing_daemon_process = None

def start_routing_daemon(node_id):
    global routing_daemon_process
    if not os.path.exists(ROUTING_DAEMON_PATH):
        print(f"エラー: ルーティングデーモンのパスが見つかりません: {ROUTING_DAEMON_PATH}")
        sys.exit(1)
    print(f"Node {node_id}: ルーティングデーモンを起動します...")
    routing_daemon_process = subprocess.Popen(
        ['sudo', 'python3', ROUTING_DAEMON_PATH, str(node_id)],
        stdout=subprocess.DEVNULL, # デバッグ中は stdout=None に変更
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


# ---------- モーター制御 ----------
pwm = PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)

class MotorDriver():
    def __init__(self):
        self.PWMB = 5
        self.BIN1 = 3
        self.BIN2 = 4

    def MotorRun(self, direction, speed):
        if speed > 100:
            return
        pwm.setDutycycle(self.PWMB, speed)
        if direction == 'forward':
            pwm.setLevel(self.BIN1, 0)
            pwm.setLevel(self.BIN2, 1)
        else: # 'backward'
            pwm.setLevel(self.BIN1, 1)
            pwm.setLevel(self.BIN2, 0)

    def MotorStop(self):
        pwm.setDutycycle(self.PWMB, 0)

# ---------- save_recv 実行 (RelayNode1で映像受信が不要であれば削除) ----------
# RelayNode1が映像受信をする場合は、以下のコメントを外し、パスとIP/ポートを設定
# print("映像受信プログラム (save_recv) を起動します...")
# recv_proc = subprocess.Popen([
#     "/home/pi/robot_project/robot_video_capture_v1/save_recv.out", # 適切なパスに修正
#     "192.168.200.4", # RelayNode1自身のIP
#     "60600" # save_recv.cppで定義されているポート番号
# ], preexec_fn=ignore_sigpipe)


# ★★★ CtlNodeからの移動開始信号を待ち受ける ★★★
RELAY_NODE1_LISTEN_PORT = 5003 # RelayNode1用の新しいポート

robot_movement_started = threading.Event()

def start_signal_listener():
    HOST = '0.0.0.0'
    print(f"RelayNode1：CtlNodeからの移動開始信号をポート {RELAY_NODE1_LISTEN_PORT} で待機中...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, RELAY_NODE1_LISTEN_PORT))
        s.listen(1)
        conn, addr = s.accept()
        with conn:
            print(f"{addr} から接続されました (移動開始信号)")
            data = conn.recv(1024)
            if b'start_move' in data:
                print("移動開始信号を受信しました。")
                robot_movement_started.set()
            else:
                print("不明な信号を受信しました。")

# TCPサーバーを別スレッドで起動
listener_thread = threading.Thread(target=start_signal_listener, daemon=True)
listener_thread.start()


# ルーティングデーモンをここで起動！
start_routing_daemon(MY_NODE_ID)


# ---------- 前進開始 ----------
Motor = MotorDriver()
TARGET_DISTANCE = 2.0
NO_MOVEMENT_TIMEOUT = 10
tolerance_range = 0.1

try:
    print("RelayNode1：CtlNodeからの移動開始信号を待っています...")
    robot_movement_started.wait()
    print("RelayNode1：移動を開始します。")

    no_movement_start = None
    while True:
        current_distance = get_distance()
        print(f"Distance: {current_distance:.2f} m")

        if current_distance <= TARGET_DISTANCE - tolerance_range:
            Motor.MotorRun('forward', 30)
            no_movement_start = None
        else:
            Motor.MotorStop()
            if no_movement_start is None:
                no_movement_start = time.time()
            elif time.time() - no_movement_start >= NO_MOVEMENT_TIMEOUT:
                print("10秒以上前進していないため停止します。")
                break

        time.sleep(0.4)

except KeyboardInterrupt:
    print("ユーザーによる中断")

finally:
    print("終了処理を行います。")
    Motor.MotorStop()
    time.sleep(1.0)
    # もしrecv_procを起動しているなら、終了処理もここに追加
    # if 'recv_proc' in locals() and recv_proc.poll() is None:
    #     try:
    #         recv_proc.send_signal(signal.SIGINT)
    #         time.sleep(2.0)
    #         recv_proc.wait(timeout=10)
    #     except subprocess.TimeoutExpired:
    #         print("受信プログラムを強制終了します。")
    #         recv_proc.kill()
    #         recv_proc.wait()
    # else:
    #     print("受信プログラムはすでに終了しています。")
    
    stop_routing_daemon()