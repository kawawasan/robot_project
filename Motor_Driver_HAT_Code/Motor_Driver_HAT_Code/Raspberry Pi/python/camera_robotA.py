#!/usr/bin/python
from PCA9685 import PCA9685
import subprocess
import time
from getdist_lidar import get_distance  # LIDAR用関数をインポート
import signal
import socket
import sys
import os



pwm = PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)

class MotorDriver():
    def __init__(self):
        self.PWMB = 5
        self.BIN1 = 3
        self.BIN2 = 4

    def MotorRun(self, direction, speed):
        if speed > 100:
            #print("Speed must be between 0 and 100")
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
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # または SIG_
    
camera_proc = subprocess.Popen([
    "/home/pi/robot_project/robot_video_capture_v1/capture_send2.out",
    # "/home/pi/robot_project/robot_video_capture_v1/capture_send.out",
    "192.168.200.4", #とりあえずctlNodeに直接送るように変更
    "0",
    "1000"
], preexec_fn=ignore_sigpipe)##.outに対してsigpipeを無視させる


# メイン制御ループ
Motor = MotorDriver()
# TARGET_DISTANCE = 1.0  # 1m以内に入ったら停止
TARGET_DISTANCE = 2.0  # 2m以内に入ったら停止
NO_MOVEMENT_TIMEOUT = 10  # 秒
tolerance_range = 0.05 # 10cm以内の誤差を認める
# tolerance_range = 0.1 # 10cm以内の誤差を認める

try:
    no_movement_start = None
    while True:
        current_distance = get_distance()  # LIDARから距離を取得
        print(f"Distance: {current_distance:.2f} m")

        if current_distance <= TARGET_DISTANCE-tolerance_range:
            # FORWARD
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

        time.sleep(0.4)  # 400ms間隔で距離チェック

except KeyboardInterrupt:
    print("Interrupted by user")
    Motor.MotorStop()

finally:
    Motor.MotorStop()
    time.sleep(1.0)
    
    if camera_proc.poll() is None:
        print("python側終了処理")
        # camera_proc.send_signal(signal.SIGINT)
        try:
            camera_proc.send_signal(signal.SIGINT)
            
            time.sleep(2.0)
            
            camera_proc.wait(timeout=5)
            
        except subprocess.TimeoutExpired:
            print("強制終了")
            camera_proc.kill()
            camera_proc.wait()  
        # camera_proc.terminate()
        # camera_proc.wait()
        time.sleep(2.0)
    else:
        print("Camera process already exited.")
