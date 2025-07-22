# camera_robot.py (CamNode上で実行)
#!/usr/bin/python
from PCA9685 import PCA9685
import subprocess
import time
from getdist_lidar import get_distance
import signal
import socket
import sys
import os

# --- ルーティングデーモン関連の設定は不要 (wait_start_robot.py が管理) ---

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
        if(direction == 'forward'):
            pwm.setLevel(self.BIN1, 1)
            pwm.setLevel(self.BIN2, 0)
        else:
            pwm.setLevel(self.BIN1, 0)
            pwm.setLevel(self.BIN2, 1)

    def MotorStop(self):
        pwm.setDutycycle(self.PWMB, 0)

def ignore_sigpipe():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# ★★★ 映像送信先のIPアドレスとポートを更新 ★★★
# capture_send2.out は適切なパスに修正
camera_proc = subprocess.Popen([
    "/home/pi/robot_project/robot_video_capture_v1/capture_send2.out",
    "192.168.200.10", # CtlNodeの新しいIPアドレス
    "0", # この引数の意味はcapture_send2.outの仕様に依存
    "60600" # save_recv.cppで定義されているポート番号
], preexec_fn=ignore_sigpipe)


# メイン制御ループ
Motor = MotorDriver()
TARGET_DISTANCE = 2.0
NO_MOVEMENT_TIMEOUT = 30
tolerance_range = 0.1

try:
    no_movement_start = None
    while True:
        current_distance = get_distance()
        print(f"Distance: {current_distance:.2f} m")

        if current_distance <= TARGET_DISTANCE-tolerance_range:
            time.sleep(1.0)
            Motor.MotorRun('forward', 30)
            no_movement_start = None
        else:
            Motor.MotorStop()
            if no_movement_start is None:
                no_movement_start = time.time()
            elif time.time() - no_movement_start >= NO_MOVEMENT_TIMEOUT:
                print("No movement for over 10 seconds. Exiting.")
                break

        time.sleep(0.4)

except KeyboardInterrupt:
    print("Interrupted by user")
    Motor.MotorStop()

finally:
    Motor.MotorStop()
    time.sleep(1.0)
    
    if camera_proc.poll() is None:
        print("python側終了処理")
        try:
            camera_proc.send_signal(signal.SIGINT)
            time.sleep(2.0)
            camera_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("強制終了")
            camera_proc.kill()
            camera_proc.wait()  
        time.sleep(2.0)
    else:
        print("Camera process already exited.")