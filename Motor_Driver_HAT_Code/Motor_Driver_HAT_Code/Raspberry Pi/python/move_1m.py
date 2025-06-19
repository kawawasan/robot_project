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
                pwm.setLevel(self.AIN1, 0)
                pwm.setLevel(self.AIN2, 1)
            else:
                pwm.setLevel(self.AIN1, 1)
                pwm.setLevel(self.AIN2, 0)
        else:
            pwm.setDutycycle(self.PWMB, speed)
            if direction == 'forward':
                pwm.setLevel(self.BIN1, 0)
                pwm.setLevel(self.BIN2, 1)
            else:
                pwm.setLevel(self.BIN1, 1)
                pwm.setLevel(self.BIN2, 0)

    def MotorStop(self, motor):
        if motor == 0:
            pwm.setDutycycle(self.PWMA, 0)
        else:
            pwm.setDutycycle(self.PWMB, 0)

# メイン制御ループ
Motor = MotorDriver()
#実験用に変更
TARGET_DISTANCE = 2.0  # 2m以内に入ったら停止
tolerance_range = 0.05

try:
    while True:
        current_distance = get_distance()  # LIDARから距離を取得
        print(f"Distance: {current_distance:.2f} m")

        if current_distance <= TARGET_DISTANCE-tolerance_range:
            # FORWARD
            Motor.MotorRun(0, 'forward', 50)
            Motor.MotorRun(1, 'forward', 50)
        else:
            print("Target reached. Stopping motors.")
            Motor.MotorStop(0)
            Motor.MotorStop(1)
            #break

        time.sleep(0.4)  # 100ms間隔で距離チェック

except KeyboardInterrupt:
    print("Interrupted by user")
    Motor.MotorStop(0)
    Motor.MotorStop(1)
