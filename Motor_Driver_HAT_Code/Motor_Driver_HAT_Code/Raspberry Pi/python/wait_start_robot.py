# wait_start_robot.py
#rear_robot.pyからの信号を待機し、camera_robot.pyを動かす(200.3)
import socket
import subprocess

HOST = '0.0.0.0'  # 全インターフェースで待機
PORT = 5000       # 後方ロボットと合わせる

print("前方ロボット：後方からの起動信号を待機中...")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen(1)
    conn, addr = s.accept()
    with conn:
        print(f"{addr} から接続されました")
        data = conn.recv(1024)
        if b'start' in data:
            print("起動信号を受信しました，camera_robot.py を実行します")
            subprocess.run(["python3", "camera_robot.py"])
