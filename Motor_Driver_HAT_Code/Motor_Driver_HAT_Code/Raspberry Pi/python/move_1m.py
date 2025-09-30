#!/usr/bin/python

from PCA9685 import PCA9685
import time
from getdist_lidar import get_distance  # LIDAR用関数をインポート

pwm = PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)

class MotorDriver():
    def __init__(self):
        self.PWMA = 0
        self.AIN1 = 1
        self.AIN2 = 2
        self.PWMB = 5
        self.BIN1 = 3
        self.BIN2 = 4

    def MotorRun(self, motor, direction, speed):
        if speed > 100:
            #print("Speed must be between 0 and 100")
            return

        if motor == 0:
            pwm.setDutycycle(self.PWMA, speed)
            if(direction == 'forward'):
                pwm.setLevel(self.AIN1, 1)
                pwm.setLevel(self.AIN2, 0)
            else:
                pwm.setLevel(self.AIN1, 0)
                pwm.setLevel(self.AIN2, 1)
        else:
            pwm.setDutycycle(self.PWMB, speed)
            if direction == 'forward':
                pwm.setLevel(self.BIN1, 1)
                pwm.setLevel(self.BIN2, 0)
            else:
                pwm.setLevel(self.BIN1, 0)
                pwm.setLevel(self.BIN2, 1)

    def MotorStop(self, motor):
        if motor == 0:
            pwm.setDutycycle(self.PWMA, 0)
        else:
            pwm.setDutycycle(self.PWMB, 0)

# メイン制御ループ
Motor = MotorDriver()
TARGET_POSITION_FILE = "/tmp/robot_target_position.txt"

def read_target_position():
    """ファイルから目標位置を読み取る"""
    try:
        with open(TARGET_POSITION_FILE, 'r') as f:
            # cm単位で読み取り、m単位に変換
            return float(f.read().strip()) / 100.0
    except (FileNotFoundError, ValueError):
        # ファイルがない、または内容が不正な場合は現在の位置を維持
        return None

try:
    while True:
        target_distance = read_target_position()
        current_distance = get_distance()  # LIDARから距離を取得

        if target_distance is not None:
            print(f"Current: {current_distance:.2f} m, Target: {target_distance:.2f} m")
            # 目標距離より遠ければ前進、近ければ後退（ここでは単純な前進のみ）
            if current_distance > target_distance:
                print("Moving forward to target...")
                Motor.MotorRun(0, 'forward', 50)
                Motor.MotorRun(1, 'forward', 50)
            else:
                print("Target reached or passed. Stopping.")
                Motor.MotorStop(0)
                Motor.MotorStop(1)
        else:
            print(f"Waiting for target position... Current distance: {current_distance:.2f} m")
            Motor.MotorRun(0, 'forward', 50)
            Motor.MotorRun(1, 'forward', 50)

        time.sleep(0.2)  # 200ms間隔でチェック

except KeyboardInterrupt:
    print("Interrupted by user")
    Motor.MotorStop(0)
    Motor.MotorStop(1)
