#映像伝送とルーティング制御を実験するためのプログラム

#!/usr/bin/python3
import subprocess
import socket
import time
import signal
import sys
import os

from PCA9685 import PCA9685
# from getdist_lidar import get_distance # LIDAR用関数をインポート: コメントアウト

# --- ルーティングデーモン関連の設定 (共通) ---
ROUTING_DAEMON_PATH = os.path.join(os.path.dirname(__file__), 'node.py')
MY_NODE_ID = 1 # 後方ロボットのNode ID

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

# ---------- モーター制御 ----------
pwm = PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)

class MotorDriver():
    def __init__(self):
        self.PWMB = 5
        self.BIN1 = 3
        self.BIN2 = 4

    def MotorRun(self, direction, speed):
        # モーター起動を無効化
        # if speed > 100:
        #     return
        # pwm.setDutycycle(self.PWMB, speed)
        # if direction == 'forward':
        #     pwm.setLevel(self.BIN1, 0)
        #     pwm.setLevel(self.BIN2, 1)
        # else:
        #     pwm.setLevel(self.BIN1, 1)
        #     pwm.setLevel(self.BIN2, 0)
        pass # 何もしない

    def MotorStop(self):
        # モーター停止を無効化
        # pwm.setDutycycle(self.PWMB, 0)
        pass # 何もしない

# ---------- save_recv 実行 ----------
def ignore_sigpipe():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

print("映像受信プログラム (save_recv) を起動します...")
recv_proc = subprocess.Popen([
    "/home/pi/robot_project/robot_video_capture_v1/save_recv.out",
    "192.168.200.2"
], preexec_fn=ignore_sigpipe)

# ルーティングデーモンをここで起動！
start_routing_daemon(MY_NODE_ID)

# ---------- Enterキー待機 (デバッグ用) ----------
# input("Enterキーが押されるまで待機します...") # 不要であればコメントアウト

# ---------- 前進開始 ----------
Motor = MotorDriver()
# TARGET_DISTANCE = 2.0  # 2m以内で停止: コメントアウト
# NO_MOVEMENT_TIMEOUT = 10: コメントアウト
# tolerance_range = 0.1: コメントアウト

try:
    # no_movement_start = None: コメントアウト
    while True:
        # current_distance = get_distance(): コメントアウト
        # print(f"Distance: {current_distance:.2f} m"): コメントアウト

        # if current_distance <= TARGET_DISTANCE - tolerance_range:: コメントアウト
        #     Motor.MotorRun('forward', 30): コメントアウト
        #     no_movement_start = None: コメントアウト
        # else:: コメントアウト
        #     Motor.MotorStop(): コメントアウト
        #     if no_movement_start is None:: コメントアウト
        #         no_movement_start = time.time(): コメントアウト
        #     elif time.time() - no_movement_start >= NO_MOVEMENT_TIMEOUT:: コメントアウト
        #         print("10秒以上前進していないため停止します。"): コメントアウト
        #         break: コメントアウト
        
        # モーター制御とLIDAR関連のロジックを削除し、単に待機する
        time.sleep(1.0) # 映像伝送のためにループを維持

except KeyboardInterrupt:
    print("ユーザーによる中断")

finally:
    print("終了処理を行います。")
    Motor.MotorStop() # 無効化されているので影響なし
    time.sleep(1.0)
    if recv_proc.poll() is None:
        try:
            recv_proc.send_signal(signal.SIGINT)
            time.sleep(2.0)
            recv_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("受信プログラムを強制終了します。")
            recv_proc.kill()
            recv_proc.wait()
    else:
        print("受信プログラムはすでに終了しています。")
        
    #ルーティングデーモンを終了
    stop_routing_daemon()