import os
import signal
import subprocess
import time
from datetime import datetime
from PCA9685 import PCA9685
from getdist_lidar import get_distance

pwm = PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)

#モータ一台のみ制御する設定に変更済
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

Motor = MotorDriver()
TARGET_DISTANCE = 1.0
TOLERANCE = 0.05
NO_MOVEMENT_TIMEOUT = 10  # 秒
CHECK_INTERVAL = 0.4

#実行時刻のファイル名
record_dir = "/home/pi/recordings"
timestamp = datetime.now().strftime("%Y%m%d_%H%M")
filename = os.path.join(record_dir, f"record_{timestamp}.mp4")

# カメラ録画コマンド
camera_cmd = (
    f"libcamera-vid -t 0 --width 1280 --height 720 "
    f"--framerate 30 --codec h264 --inline -vflip -o - | "
    f"ffmpeg -fflags +genpts -i - -c:v copy {filename}"
)

try:
    # カメラ起動
    camera_proc = subprocess.Popen(camera_cmd, shell=True, preexec_fn=os.setsid)
    print("Camera recording started.")

    no_movement_start = None

    while True:
        dist = get_distance()
        print(f"Distance: {dist:.2f} m")

        if dist <= TARGET_DISTANCE - TOLERANCE:
            Motor.MotorRun('forward', 50)
            no_movement_start = None  # 動いたのでリセット
        else:
            Motor.MotorStop()
            if no_movement_start is None:
                no_movement_start = time.time()
            elif time.time() - no_movement_start >= NO_MOVEMENT_TIMEOUT:
                print("No movement for over 10 seconds. Exiting.")
                break

        time.sleep(CHECK_INTERVAL)

except KeyboardInterrupt:
    print("Interrupted by user.")

finally:
    Motor.MotorStop()
    if camera_proc.poll() is None:
        os.killpg(os.getpgid(camera_proc.pid), signal.SIGTERM)
	#camera_proc.terminate()
        print("Camera recording stopped.")


