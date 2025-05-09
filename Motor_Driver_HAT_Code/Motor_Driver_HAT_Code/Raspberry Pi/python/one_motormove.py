#!/usr/bin/python

from PCA9685 import PCA9685
import time
from getdist_lidar import get_distance  # LIDAR用関数をインポート

pwm = PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)

class MotorDriver():
    def __init__(self):
        self.PWMB = 5
        self.BIN1 = 3
        self.BIN2 = 4

    def MotorRun(self, motor, direction, speed):
        if speed > 100:
            #print("Speed must be between 0 and 100")
            return

        pwm.setDutycycle(self.PWMB, speed)
        if(direction == 'forward'):
            pwm.setLevel(self.BIN1, 0)
            pwm.setLevel(self.BIN2, 1)
        else:
            pwm.setLevel(self.BIN1, 1)
            pwm.setLevel(self.BIN2, 0)

    def MotorStop(self):
        pwm.setDutycycle(self.PWMB, 0)

# メイン制御ループ
Motor = MotorDriver()
TARGET_DISTANCE = 1.0  # 1m以内に入ったら停止
tolerance_range = 0.05

try:
    no_movement_start = None
    while True:
        current_distance = get_distance()  # LIDARから距離を取得
        print(f"Distance: {current_distance:.2f} m")

        if current_distance <= TARGET_DISTANCE-tolerance_range:
            # FORWARD
            Motor.MotorRun('forward', 70)
            no=movement_start = None
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
