# start_robot_from_ctl.py (CtlNode上で実行)
import socket
import sys
import time
import subprocess
import os
import signal

# --- ルーティングデーモン関連の設定 (共通) ---
# PATHはご自身の環境に合わせてください
ROUTING_DAEMON_PATH = os.path.join(os.path.dirname(__file__), 'node.py')
MY_NODE_ID = 0 # CtlNodeのNode ID

routing_daemon_process = None

def start_routing_daemon(node_id):
    global routing_daemon_process
    if not os.path.exists(ROUTING_DAEMON_PATH):
        print(f"エラー: ルーティングデーモンのパスが見つかりません: {ROUTING_DAEMON_PATH}")
        sys.exit(1)
    print(f"Node {node_id}: ルーティングデーモンを起動します...")
    routing_daemon_process = subprocess.Popen(
        ['sudo', 'python3', ROUTING_DAEMON_PATH, str(node_id)],
        stdout=subprocess.DEVNULL, # デバッグ中は stdout=None に変更してログを確認
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid # Ctrl+Cで親プロセス終了時に子プロセスも終了させない
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

# ★★★ IPアドレスとポートの定義を更新 ★★★
RECEIVE_VIDEO_PROGRAM_PATH = "/home/pi/robot_project/robot_video_capture_v1/save_recv.out" # 適切なパスに修正
RECEIVE_VIDEO_IP = "192.168.200.10" # CtlNode自身の新しいIP

CAMERA_ROBOT_IP = "192.168.200.3" # CamNodeのIP
CAMERA_ROBOT_PORT = 5000

RELAY_NODE2_IP = "192.168.200.2" # RelayNode2のIP
RELAY_NODE2_PORT = 5002 # RelayNode2用のポート

RELAY_NODE1_IP = "192.168.200.4" # RelayNode1のIP
RELAY_NODE1_PORT = 5003 # ★RelayNode1用の新しいポート

recv_video_process = None

def ignore_sigpipe():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

def start_receive_video_program():
    global recv_video_process
    if not os.path.exists(RECEIVE_VIDEO_PROGRAM_PATH):
        print(f"エラー: 映像受信プログラムのパスが見つかりません: {RECEIVE_VIDEO_PROGRAM_PATH}")
        return False
    
    print(f"映像受信プログラム ({RECEIVE_VIDEO_PROGRAM_PATH}) を起動します...")
    recv_video_process = subprocess.Popen([
        RECEIVE_VIDEO_PROGRAM_PATH,
        RECEIVE_VIDEO_IP,
        "60600" # save_recv.cppで定義されているポート番号
    ], preexec_fn=ignore_sigpipe)
    print(f"映像受信プログラム PID: {recv_video_process.pid} で起動しました。")
    return True

def stop_receive_video_program():
    global recv_video_process
    if recv_video_process and recv_video_process.poll() is None:
        print("映像受信プログラムを終了します...")
        try:
            recv_video_process.send_signal(signal.SIGINT)
            time.sleep(2.0)
            recv_video_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("映像受信プログラムを強制終了します。")
            recv_video_process.kill()
            recv_video_process.wait()
        except Exception as e:
            print(f"映像受信プログラム終了中にエラーが発生しました: {e}")
    else:
        print("映像受信プログラムは実行中ではありません。")


def send_signal(ip_address, port, signal_data):
    try:
        print(f"ロボット ({ip_address}:{port}) へ信号 '{signal_data.decode()}' を送信します...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((ip_address, port))
            s.sendall(signal_data)
        print("信号を送信しました。")
        return True
    except Exception as e:
        print(f"ロボット ({ip_address}:{port}) への接続に失敗しました: {e}")
        return False

if __name__ == "__main__":
    start_routing_daemon(MY_NODE_ID)

    if not start_receive_video_program():
        print("映像受信プログラムの起動に失敗しました。終了します。")
        stop_routing_daemon()
        sys.exit(1)
    
    try:
        # input("Enterキーを押すと、カメラロボットと後方ロボットへ起動/移動開始信号を送信します...")
        input("1回目のEnterでCamNodeを起動します...")
    
        # 1. CamNodeへ起動信号を送信 (Node ID 3)
        if send_signal(CAMERA_ROBOT_IP, CAMERA_ROBOT_PORT, b"start"):
            print("カメラロボット起動信号の送信に成功しました。")
        else:
            print("カメラロボット起動信号の送信に失敗しました。")
            
        # 2. RelayNode2へ移動開始信号を送信 (Node ID 2)
        input("2回目のEnterでRelayNode2を起動します...")
        time.sleep(1) # 必要に応じて調整
        if send_signal(RELAY_NODE2_IP, RELAY_NODE2_PORT, b"start_move"):
            print("中継ロボット2（RelayNode2）移動開始信号の送信に成功しました。")
        else:
            print("中継ロボット2（RelayNode2）移動開始信号の送信に失敗しました。")

        # 3. RelayNode1へ移動開始信号を送信 (Node ID 1)
        input("3回目のEnterでRelayNode1を起動します...")
        time.sleep(1) # 必要に応じて調整
        if send_signal(RELAY_NODE1_IP, RELAY_NODE1_PORT, b"start_move"):
            print("中継ロボット1（RelayNode1）移動開始信号の送信に成功しました。")
        else:
            print("中継ロボット1（RelayNode1）移動開始信号の送信に失敗しました。")


        print("\nCtlNodeのメイン制御プログラムが実行中です。")
        while True:
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nCtlNode制御プログラムを終了します。")
    except Exception as e:
        print(f"予期せぬエラー: {e}")
    finally:
        stop_routing_daemon()
        stop_receive_video_program()