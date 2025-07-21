# rear_robot.py (RelayNode2上で実行)
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
MY_NODE_ID = 2 # RelayNode2のNode ID

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
pwm = PCA9685(0x40, debug=False) # 0x40はPCA9685のデフォルトアドレス
pwm.setPWMFreq(50) # 50Hz

class MotorDriver():
    def __init__(self):
        # PWMチャネルやGPIOピンの定義
        self.PWMB = 5 # モーターBのPWM出力チャネル
        self.BIN1 = 3 # モーターBの方向制御ピン1
        self.BIN2 = 4 # モーターBの方向制御ピン2

    def MotorRun(self, direction, speed):
        if speed > 100:
            return
        pwm.setDutycycle(self.PWMB, speed) # PWMデューティサイクルを設定 (0-100)
        if direction == 'forward':
            pwm.setLevel(self.BIN1, 1) # 方向制御ピンを設定
            pwm.setLevel(self.BIN2, 0)
        else: # 'backward'
            pwm.setLevel(self.BIN1, 0)
            pwm.setLevel(self.BIN2, 1)

    def MotorStop(self):
        pwm.setDutycycle(self.PWMB, 0) # デューティサイクルを0にしてモーター停止

# ---------- save_recv 実行 ----------
def ignore_sigpipe():
    # SIGPIPEシグナルを無視する設定 (subprocessでパイプが閉じられたときにクラッシュしないため)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

print("映像受信プログラム (save_recv) を起動します...")
recv_proc = subprocess.Popen([
    "/home/pi/robot_project/robot_video_capture_v1/save_recv.out", # 適切なパスに修正
    "192.168.200.2", # RelayNode2自身のIPアドレス
    "60600" # save_recv.cppで定義されているポート番号
], preexec_fn=ignore_sigpipe)


# ★★★ CtlNodeからの移動開始信号を待ち受ける ★★★
REAR_ROBOT_LISTEN_PORT = 5002 # RelayNode2用の新しいポート

robot_movement_started = threading.Event() # 移動開始イベント

def start_signal_listener():
    HOST = '0.0.0.0' # 全てのインターフェースで待機
    print(f"RelayNode2：CtlNodeからの移動開始信号をポート {REAR_ROBOT_LISTEN_PORT} で待機中...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, REAR_ROBOT_LISTEN_PORT))
        s.listen(1) # 1つの接続を待機
        conn, addr = s.accept() # 接続を受け付ける
        with conn: # 接続ソケットを閉じるためのwithブロック
            print(f"{addr} から接続されました (移動開始信号)")
            data = conn.recv(1024) # データを受信
            if b'start_move' in data: # 信号 'start_move' を検出
                print("移動開始信号を受信しました。")
                robot_movement_started.set() # イベントを設定してメインスレッドに通知
            else:
                print("不明な信号を受信しました。")

# TCPサーバーを別スレッドで起動
listener_thread = threading.Thread(target=start_signal_listener, daemon=True)
listener_thread.start()


# ルーティングデーモンをここで起動！
start_routing_daemon(MY_NODE_ID)


# ---------- 前進開始 ----------
Motor = MotorDriver()
TARGET_DISTANCE = 2.0 # LIDARでこの距離以下になったら停止
NO_MOVEMENT_TIMEOUT = 10 # 10秒以上動かなければ停止
tolerance_range = 0.1 # 距離判定の許容誤差

try:
    print("RelayNode2：CtlNodeからの移動開始信号を待っています...")
    robot_movement_started.wait() # イベントが設定されるまでここでブロック
    print("RelayNode2：移動を開始します。")

    no_movement_start = None
    while True:
        current_distance = get_distance() # LIDARから距離を取得
        print(f"Distance: {current_distance:.2f} m")

        # ターゲット距離に達したら停止、そうでなければ前進
        if current_distance <= TARGET_DISTANCE - tolerance_range:
            Motor.MotorRun('forward', 30) # 前進
            no_movement_start = None
        else:
            Motor.MotorStop() # 停止
            if no_movement_start is None:
                no_movement_start = time.time()
            elif time.time() - no_movement_start >= NO_MOVEMENT_TIMEOUT:
                print("10秒以上前進していないため停止します。")
                break

        time.sleep(0.4) # 処理間隔

except KeyboardInterrupt:
    print("ユーザーによる中断")

finally:
    print("終了処理を行います。")
    Motor.MotorStop() # モーター停止
    time.sleep(1.0)
    # 映像受信プログラムの終了処理
    if recv_proc.poll() is None:
        try:
            recv_proc.send_signal(signal.SIGINT) # SIGINTを送信
            time.sleep(2.0)
            recv_proc.wait(timeout=10) # 終了を待機
        except subprocess.TimeoutExpired:
            print("受信プログラムを強制終了します。")
            recv_proc.kill() # 強制終了
            recv_proc.wait()
    else:
        print("受信プログラムはすでに終了しています。")
    
    stop_routing_daemon() # ルーティングデーモンを終了