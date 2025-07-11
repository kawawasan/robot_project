# start_robot_from_ctl.py (ctlNode上で実行)
import socket
import sys
import time
import subprocess
import os
import signal


# --- ルーティングデーモン関連の設定 (共通) ---
ROUTING_DAEMON_PATH = os.path.join(os.path.dirname(__file__), 'node.py')
MY_NODE_ID = 0 # ctlNodeのNode ID

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

TARGET_ROBOT_IP = "192.168.200.3" # カメラロボットのIPアドレス
TARGET_PORT = 5000

#6/12追記　映像プログラム組み込み
# --- 映像受信プログラム関連の設定 ---
# save_recv.out のパスと、受信待機するIPアドレス
# 自身のIPアドレスで受信待機させる
RECEIVE_VIDEO_PROGRAM_PATH = "/home/pi/robot_project/robot_video_capture_v1/save_recv.out"
RECEIVE_VIDEO_IP = "192.168.200.10" # ctlNode自身のIP

recv_video_process = None # 映像受信プロセスを保持する変数

def ignore_sigpipe(): # SIGPIPEを無視する関数 (Popenで必要になることがある)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

def start_receive_video_program():
    global recv_video_process
    if not os.path.exists(RECEIVE_VIDEO_PROGRAM_PATH):
        print(f"エラー: 映像受信プログラムのパスが見つかりません: {RECEIVE_VIDEO_PROGRAM_PATH}")
        # プログラムを終了するか、エラー処理を記述
        return False
    
    print(f"映像受信プログラム ({RECEIVE_VIDEO_PROGRAM_PATH}) を起動します...")
    recv_video_process = subprocess.Popen([
        RECEIVE_VIDEO_PROGRAM_PATH,
        RECEIVE_VIDEO_IP # 自身のIPアドレスで受信待機
    ], preexec_fn=ignore_sigpipe)
    print(f"映像受信プログラム PID: {recv_video_process.pid} で起動しました。")
    return True

def stop_receive_video_program():
    global recv_video_process
    if recv_video_process and recv_video_process.poll() is None:
        print("映像受信プログラムを終了します...")
        try:
            recv_video_process.send_signal(signal.SIGINT) # SIGINT を送信
            time.sleep(2.0) # 終了を待つ
            recv_video_process.wait(timeout=10) # タイムアウト付きで終了を待機
        except subprocess.TimeoutExpired:
            print("映像受信プログラムを強制終了します。")
            recv_video_process.kill() # 強制終了
            recv_video_process.wait()
        except Exception as e:
            print(f"映像受信プログラム終了中にエラーが発生しました: {e}")
    else:
        print("映像受信プログラムは実行中ではありません。")
# --- 映像受信プログラム関連の設定ここまで ---


def send_start_signal(ip_address, port):
    try:
        print(f"カメラロボット ({ip_address}) へ起動信号を送信します...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((ip_address, port))
            s.sendall(b"start")
        print("起動信号を送信しました。")
        return True
    except Exception as e:
        print(f"カメラロボットへの接続に失敗しました: {e}")
        return False

if __name__ == "__main__":
    start_routing_daemon(MY_NODE_ID) # ctlNodeのルーティングデーモンを起動

    # 映像受信プログラムをここで起動！
    if not start_receive_video_program():
        print("映像受信プログラムの起動に失敗しました。終了します。")
        stop_routing_daemon()
        sys.exit(1)
    
    
    try:
        input("Enterキーを押すと、カメラロボットに起動信号を送信します...")
        
        if send_start_signal(TARGET_ROBOT_IP, TARGET_PORT):
            print("起動信号の送信に成功しました。")
        else:
            print("起動信号の送信に失敗しました。ルーティングデーモンのログと ip route show を確認してください。")

        # ここにctlNodeのメイン制御ループを追加
        print("\nctlNodeのメイン制御プログラムが実行中です。")
        while True:
            # 例: ロボットのステータス監視、コマンド送信など
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nctlNode制御プログラムを終了します。")
    except Exception as e:
        print(f"予期せぬエラー: {e}")
    finally:
        stop_routing_daemon() # ルーティングデーモンを終了