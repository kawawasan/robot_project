#!/usr/bin/python3
import subprocess
import socket
import time
import signal
from PCA9685 import PCA9685
from getdist_lidar import get_distance

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
        else:
            pwm.setLevel(self.BIN1, 1)
            pwm.setLevel(self.BIN2, 0)

    def MotorStop(self):
        pwm.setDutycycle(self.PWMB, 0)

# ---------- save_recv 実行 ----------
def ignore_sigpipe():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

print("映像受信プログラム (save_recv) を起動します...")
recv_proc = subprocess.Popen([
    "/home/pi/robot_project/robot_video_capture_v1/save_recv.out",
    "192.168.200.2"
], preexec_fn=ignore_sigpipe)

# ---------- 前方ロボットに起動信号を送信 ----------
FRONT_ROBOT_IP = "192.168.200.3"  # 前方ロボットIP
PORT = 5000

try:
    print("前方ロボットへ起動信号を送信します...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((FRONT_ROBOT_IP, PORT))
        s.sendall(b"start")
    print("起動信号を送信しました。")

except Exception as e:
    print(f"前方ロボットへの接続に失敗しました: {e}")

# ---------- Enterキー待機 ----------
input("Enterキーが押されるまで待機します...")

# ---------- 前進開始 ----------
Motor = MotorDriver()
TARGET_DISTANCE = 2.0  # 1m以内で停止
NO_MOVEMENT_TIMEOUT = 10
tolerance_range = 0.1

try:
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
