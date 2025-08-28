# start_robot_from_ctl.py (CtlNode上で実行)
import socket
import sys
import time
import subprocess
import os
import signal
import threading
from flask import Flask, jsonify, send_from_directory

# --- ルーティングデーモンのクラス定義 ---
# node_class.pyの内容をここに統合
# 環境設定
NODE_INFO = {
    0: "192.168.200.10", # CtlNode
    1: "192.168.200.4",  # RelayNode1
    2: "192.168.200.2",  # RelayNode2
    3: "192.168.200.3",  # CamNode
}
IP_NETMASK_PREFIX = "192.168.200"
BROADCAST_PORT = 12345
UNICAST_PORT = 12346
BEACON_INTERVAL = 5 # 秒

MIN_NODE_ID = 0
MAX_NODE_ID = 3 # 4ノード (0, 1, 2, 3)

class Node:
    def __init__(self, node_id, ip_address, node_info):
        self.node_id = node_id
        self.ip_address = ip_address
        self.node_info = node_info
        self.responder_list = []
        self.responder_list_lock = threading.Lock()
        self.min_scope_id = node_id
        self.max_scope_id = node_id

        print(f"[Node Class] Node {self.node_id} ({self.ip_address}) initialized.")

    def _update_ip_route(self, dest_ip, via_ip):
        cmd = f"sudo ip route replace {dest_ip} via {via_ip}"
        try:
            subprocess.run(cmd.split(), check=True)
            print(f"  [Route] Updated: {dest_ip} via {via_ip}")
        except subprocess.CalledProcessError as e:
            print(f"  [ERROR] Failed to update route: {e}")
        except FileNotFoundError:
            print(f"  [ERROR] 'ip' command not found. Ensure iproute2 is installed and in PATH.")

    def _calculate_scope(self):
        with self.responder_list_lock:
            current_responders = sorted([r[0] for r in self.responder_list])
            if not current_responders:
                self.min_scope_id = self.node_id
                self.max_scope_id = self.node_id
                return

            self.min_scope_id = self.node_id
            self.max_scope_id = self.node_id

            for rid in current_responders:
                if rid < self.node_id and rid < self.min_scope_id:
                    self.min_scope_id = rid
                if rid > self.node_id and rid > self.max_scope_id:
                    self.max_scope_id = rid

            if self.node_id == self.min_scope_id and self.node_id > MIN_NODE_ID:
                if (self.node_id - 1) not in current_responders:
                     self.min_scope_id = self.node_id - 1
            if self.node_id == self.max_scope_id and self.node_id < MAX_NODE_ID:
                if (self.node_id + 1) not in current_responders:
                     self.max_scope_id = self.node_id + 1

        print(f"  [Scope] Node {self.node_id}: Scope calculated to be {self.min_scope_id} to {self.max_scope_id}")

    def _update_routing_table(self):
        self._calculate_scope()
        print(f"  [Routing] Updating routes for Node {self.node_id}...")
        for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
            if dst_node_id == self.node_id:
                continue

            dest_ip = self.node_info[dst_node_id]

            if dst_node_id < self.min_scope_id:
                via_node_id = self.min_scope_id
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    {self.node_id} -> {dst_node_id} (via {via_node_id})")
            elif self.min_scope_id <= dst_node_id <= self.max_scope_id:
                self._update_ip_route(dest_ip, dest_ip)
                print(f"    {self.node_id} -> {dst_node_id} (direct)")
            elif dst_node_id > self.max_scope_id:
                via_node_id = self.max_scope_id
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    {self.node_id} -> {dst_node_id} (via {via_node_id})")

        with self.responder_list_lock:
            self.responder_list.clear()

    def _send_beacon(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((self.ip_address, BROADCAST_PORT))

        message = f"BEACON:{self.node_id}".encode('utf-8')
        broadcast_address = f"{IP_NETMASK_PREFIX}.255"
        
        print(f"[Beacon Sender] Node {self.node_id} sending beacon to {broadcast_address}:{BROADCAST_PORT}")
        sock.sendto(message, (broadcast_address, BROADCAST_PORT))
        sock.close()

    def beacon_sender_thread(self):
        print(f"Node {self.node_id} performing initial route setup...")
        for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
            if dst_node_id == self.node_id:
                continue
            dest_ip = self.node_info[dst_node_id]
            
            if abs(dst_node_id - self.node_id) == 1:
                self._update_ip_route(dest_ip, dest_ip)
                print(f"    Initial: {self.node_id} -> {dst_node_id} (direct)")
            else:
                if dst_node_id < self.node_id:
                    via_node_id = self.node_id - 1
                else:
                    via_node_id = self.node_id + 1
                if via_node_id < MIN_NODE_ID: via_node_id = MIN_NODE_ID
                if via_node_id > MAX_NODE_ID: via_node_id = MAX_NODE_ID
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    Initial: {self.node_id} -> {dst_node_id} (via {via_node_id})")
        while True:
            self._send_beacon()
            time.sleep(BEACON_INTERVAL)
            self._update_routing_table()

    def beacon_responder_thread(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', BROADCAST_PORT))
        response_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[Beacon Responder] Node {self.node_id} listening for beacons on port {BROADCAST_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("BEACON:"):
                    sender_id = int(message.split(":")[1])
                    sender_ip = addr[0]
                    if sender_id == self.node_id:
                        continue
                    print(f"  [Responder] Node {self.node_id} received beacon from Node {sender_id} ({sender_ip})")
                    response_message = f"RESPONSE:{self.node_id}".encode('utf-8')
                    try:
                        response_sock.sendto(response_message, (sender_ip, UNICAST_PORT))
                        print(f"  [Responder] Node {self.node_id} sent response to {sender_ip}:{UNICAST_PORT}")
                    except Exception as e:
                        print(f"  [ERROR] Failed to send response to {sender_ip}: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                print(f"  [ERROR] Beacon Responder Error: {e}")

    def unicast_receiver_thread(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', UNICAST_PORT))
        print(f"[Unicast Receiver] Node {self.node_id} listening for responses on port {UNICAST_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("RESPONSE:"):
                    responder_id = int(message.split(":")[1])
                    responder_ip = addr[0]
                    if responder_id == self.node_id:
                        continue
                    print(f"  [Receiver] Node {self.node_id} received response from Node {responder_id} ({responder_ip})")
                    with self.responder_list_lock:
                        if (responder_id, responder_ip) not in self.responder_list:
                            self.responder_list.append((responder_id, responder_ip))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"  [ERROR] Unicast Receiver Error: {e}")

    def start(self):
        beacon_sender_t = threading.Thread(target=self.beacon_sender_thread, daemon=True)
        beacon_sender_t.start()
        beacon_responder_t = threading.Thread(target=self.beacon_responder_thread, daemon=True)
        beacon_responder_t.start()
        unicast_receiver_t = threading.Thread(target=self.unicast_receiver_thread, daemon=True)
        unicast_receiver_t.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"Node {self.node_id} shutting down.")

# --- ここまで node_class.pyの内容を統合 ---


# --- パス設定の修正 ---
# 現在のスクリプトのディレクトリを取得
current_dir = os.path.dirname(os.path.abspath(__file__))
# 他のファイルへのパスを相対的に指定
ROUTING_DAEMON_PATH = os.path.join(current_dir, 'node.py')
RECEIVE_VIDEO_PROGRAM_PATH = os.path.abspath(os.path.join(current_dir, '../../../../robot_video_capture_v1/save_recv.out'))
WEB_CONTROL_DIR = os.path.abspath(os.path.join(current_dir, '../../../../web_control'))


# --- プロセス管理用グローバル変数 ---
routing_daemon_process = None
recv_video_process = None


# --- プロセス起動・停止関数 ---
def start_routing_daemon(node_id):
    global routing_daemon_process
    if not os.path.exists(ROUTING_DAEMON_PATH):
        print(f"エラー: ルーティングデーモンのパスが見つかりません: {ROUTING_DAEMON_PATH}")
        sys.exit(1)
    print(f"Node {node_id}: ルーティングデーモンを起動します...")
    routing_daemon_process = subprocess.Popen(
        ['sudo', 'python3', ROUTING_DAEMON_PATH, str(node_id)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
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
        "60600"
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


# --- ロボットのIPとポートの定義 ---
RECEIVE_VIDEO_IP = "192.168.200.10"
CAMERA_ROBOT_IP = "192.168.200.3"
CAMERA_ROBOT_PORT = 5000
RELAY_NODE1_IP = "192.168.200.4"
RELAY_NODE1_PORT = 5003
RELAY_NODE2_IP = "192.168.200.2"
RELAY_NODE2_PORT = 5002

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

# --- Flaskアプリの定義 ---
app = Flask(__name__, static_folder=WEB_CONTROL_DIR)

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

@app.route('/start_cam_node', methods=['POST'])
def start_cam_node_api():
    success = send_signal(CAMERA_ROBOT_IP, CAMERA_ROBOT_PORT, b"start")
    if success:
        return jsonify({"status": "success", "message": "CamNode起動信号を送信しました。"}), 200
    else:
        return jsonify({"status": "error", "message": "CamNode起動信号の送信に失敗しました。"}), 500

@app.route('/start_relay_node2', methods=['POST'])
def start_relay_node2_api():
    success = send_signal(RELAY_NODE2_IP, RELAY_NODE2_PORT, b"start_move")
    if success:
        return jsonify({"status": "success", "message": "RelayNode2移動開始信号を送信しました。"}), 200
    else:
        return jsonify({"status": "error", "message": "RelayNode2移動開始信号の送信に失敗しました。"}), 500

@app.route('/start_relay_node1', methods=['POST'])
def start_relay_node1_api():
    success = send_signal(RELAY_NODE1_IP, RELAY_NODE1_PORT, b"start_move")
    if success:
        return jsonify({"status": "success", "message": "RelayNode1移動開始信号を送信しました。"}), 200
    else:
        return jsonify({"status": "error", "message": "RelayNode1移動開始信号の送信に失敗しました。"}), 500

def run_server():
    app.run(host='0.0.0.0', port=8000)

# --- メイン処理 ---
if __name__ == "__main__":
    MY_NODE_ID = 0
    MY_IP_ADDRESS = NODE_INFO[MY_NODE_ID]

    # ルーティングデーモンを別プロセスで起動するためのコード
    # Note: Flaskサーバーを動かすプロセスとは別にするため、node.pyの機能を直接実行しない
    start_routing_daemon(MY_NODE_ID)

    if not start_receive_video_program():
        print("映像受信プログラムの起動に失敗しました。終了します。")
        stop_routing_daemon()
        sys.exit(1)
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    try:
        print("\nCtlNodeのメイン制御プログラムが実行中です。")
        print("ウェブサーバーがポート8000で待機しています。")
        print(f"スマートフォンから以下のURLにアクセスして操作できます: http://{RECEIVE_VIDEO_IP}:8000")
        
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nCtlNode制御プログラムを終了します。")
    except Exception as e:
        print(f"予期せぬエラー: {e}")
    finally:
        stop_routing_daemon()
        stop_receive_video_program()


# # start_robot_from_ctl.py (CtlNode上で実行)
# import socket
# import sys
# import time
# import subprocess
# import os
# import signal
# import threading
# from flask import Flask, jsonify, send_from_directory

# # --- ルーティングデーモンのクラス定義 ---
# # node_class.pyの内容をここに統合
# # 環境設定
# NODE_INFO = {
#     0: "192.168.200.10", # CtlNode
#     1: "192.168.200.4",  # RelayNode1
#     2: "192.168.200.2",  # RelayNode2
#     3: "192.168.200.3",  # CamNode
# }
# IP_NETMASK_PREFIX = "192.168.200"
# BROADCAST_PORT = 12345
# UNICAST_PORT = 12346
# BEACON_INTERVAL = 5 # 秒

# MIN_NODE_ID = 0
# MAX_NODE_ID = 3 # 4ノード (0, 1, 2, 3)

# class Node:
#     def __init__(self, node_id, ip_address, node_info):
#         self.node_id = node_id
#         self.ip_address = ip_address
#         self.node_info = node_info
#         self.responder_list = []
#         self.responder_list_lock = threading.Lock()
#         self.min_scope_id = node_id
#         self.max_scope_id = node_id

#         print(f"[Node Class] Node {self.node_id} ({self.ip_address}) initialized.")

#     def _update_ip_route(self, dest_ip, via_ip):
#         cmd = f"sudo ip route replace {dest_ip} via {via_ip}"
#         try:
#             subprocess.run(cmd.split(), check=True)
#             print(f"  [Route] Updated: {dest_ip} via {via_ip}")
#         except subprocess.CalledProcessError as e:
#             print(f"  [ERROR] Failed to update route: {e}")
#         except FileNotFoundError:
#             print(f"  [ERROR] 'ip' command not found. Ensure iproute2 is installed and in PATH.")

#     def _calculate_scope(self):
#         with self.responder_list_lock:
#             current_responders = sorted([r[0] for r in self.responder_list])
#             if not current_responders:
#                 self.min_scope_id = self.node_id
#                 self.max_scope_id = self.node_id
#                 return

#             self.min_scope_id = self.node_id
#             self.max_scope_id = self.node_id

#             for rid in current_responders:
#                 if rid < self.node_id and rid < self.min_scope_id:
#                     self.min_scope_id = rid
#                 if rid > self.node_id and rid > self.max_scope_id:
#                     self.max_scope_id = rid

#             if self.node_id == self.min_scope_id and self.node_id > MIN_NODE_ID:
#                 if (self.node_id - 1) not in current_responders:
#                      self.min_scope_id = self.node_id - 1
#             if self.node_id == self.max_scope_id and self.node_id < MAX_NODE_ID:
#                 if (self.node_id + 1) not in current_responders:
#                      self.max_scope_id = self.node_id + 1

#         print(f"  [Scope] Node {self.node_id}: Scope calculated to be {self.min_scope_id} to {self.max_scope_id}")

#     def _update_routing_table(self):
#         self._calculate_scope()
#         print(f"  [Routing] Updating routes for Node {self.node_id}...")
#         for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
#             if dst_node_id == self.node_id:
#                 continue

#             dest_ip = self.node_info[dst_node_id]

#             if dst_node_id < self.min_scope_id:
#                 via_node_id = self.min_scope_id
#                 via_ip = self.node_info[via_node_id]
#                 self._update_ip_route(dest_ip, via_ip)
#                 print(f"    {self.node_id} -> {dst_node_id} (via {via_node_id})")
#             elif self.min_scope_id <= dst_node_id <= self.max_scope_id:
#                 self._update_ip_route(dest_ip, dest_ip)
#                 print(f"    {self.node_id} -> {dst_node_id} (direct)")
#             elif dst_node_id > self.max_scope_id:
#                 via_node_id = self.max_scope_id
#                 via_ip = self.node_info[via_node_id]
#                 self._update_ip_route(dest_ip, via_ip)
#                 print(f"    {self.node_id} -> {dst_node_id} (via {via_node_id})")

#         with self.responder_list_lock:
#             self.responder_list.clear()

#     def _send_beacon(self):
#         sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
#         sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
#         sock.bind((self.ip_address, BROADCAST_PORT))

#         message = f"BEACON:{self.node_id}".encode('utf-8')
#         broadcast_address = f"{IP_NETMASK_PREFIX}.255"
        
#         print(f"[Beacon Sender] Node {self.node_id} sending beacon to {broadcast_address}:{BROADCAST_PORT}")
#         sock.sendto(message, (broadcast_address, BROADCAST_PORT))
#         sock.close()

#     def beacon_sender_thread(self):
#         print(f"Node {self.node_id} performing initial route setup...")
#         for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
#             if dst_node_id == self.node_id:
#                 continue
#             dest_ip = self.node_info[dst_node_id]
            
#             if abs(dst_node_id - self.node_id) == 1:
#                 self._update_ip_route(dest_ip, dest_ip)
#                 print(f"    Initial: {self.node_id} -> {dst_node_id} (direct)")
#             else:
#                 if dst_node_id < self.node_id:
#                     via_node_id = self.node_id - 1
#                 else:
#                     via_node_id = self.node_id + 1
#                 if via_node_id < MIN_NODE_ID: via_node_id = MIN_NODE_ID
#                 if via_node_id > MAX_NODE_ID: via_node_id = MAX_NODE_ID
#                 via_ip = self.node_info[via_node_id]
#                 self._update_ip_route(dest_ip, via_ip)
#                 print(f"    Initial: {self.node_id} -> {dst_node_id} (via {via_node_id})")
#         while True:
#             self._send_beacon()
#             time.sleep(BEACON_INTERVAL)
#             self._update_routing_table()

#     def beacon_responder_thread(self):
#         sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
#         sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#         sock.bind(('0.0.0.0', BROADCAST_PORT))
#         response_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         print(f"[Beacon Responder] Node {self.node_id} listening for beacons on port {BROADCAST_PORT}")
#         while True:
#             try:
#                 data, addr = sock.recvfrom(1024)
#                 message = data.decode('utf-8')
#                 if message.startswith("BEACON:"):
#                     sender_id = int(message.split(":")[1])
#                     sender_ip = addr[0]
#                     if sender_id == self.node_id:
#                         continue
#                     print(f"  [Responder] Node {self.node_id} received beacon from Node {sender_id} ({sender_ip})")
#                     response_message = f"RESPONSE:{self.node_id}".encode('utf-8')
#                     try:
#                         response_sock.sendto(response_message, (sender_ip, UNICAST_PORT))
#                         print(f"  [Responder] Node {self.node_id} sent response to {sender_ip}:{UNICAST_PORT}")
#                     except Exception as e:
#                         print(f"  [ERROR] Failed to send response to {sender_ip}: {e}")
#             except socket.timeout:
#                 continue
#             except Exception as e:
#                 print(f"  [ERROR] Beacon Responder Error: {e}")

#     def unicast_receiver_thread(self):
#         sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#         sock.bind(('0.0.0.0', UNICAST_PORT))
#         print(f"[Unicast Receiver] Node {self.node_id} listening for responses on port {UNICAST_PORT}")
#         while True:
#             try:
#                 data, addr = sock.recvfrom(1024)
#                 message = data.decode('utf-8')
#                 if message.startswith("RESPONSE:"):
#                     responder_id = int(message.split(":")[1])
#                     responder_ip = addr[0]
#                     if responder_id == self.node_id:
#                         continue
#                     print(f"  [Receiver] Node {self.node_id} received response from Node {responder_id} ({responder_ip})")
#                     with self.responder_list_lock:
#                         if (responder_id, responder_ip) not in self.responder_list:
#                             self.responder_list.append((responder_id, responder_ip))
#             except socket.timeout:
#                 continue
#             except Exception as e:
#                 print(f"  [ERROR] Unicast Receiver Error: {e}")

#     def start(self):
#         beacon_sender_t = threading.Thread(target=self.beacon_sender_thread, daemon=True)
#         beacon_sender_t.start()
#         beacon_responder_t = threading.Thread(target=self.beacon_responder_thread, daemon=True)
#         beacon_responder_t.start()
#         unicast_receiver_t = threading.Thread(target=self.unicast_receiver_thread, daemon=True)
#         unicast_receiver_t.start()
#         try:
#             while True:
#                 time.sleep(1)
#         except KeyboardInterrupt:
#             print(f"Node {self.node_id} shutting down.")

# # --- ここまで node_class.pyの内容を統合 ---


# # --- 未定義だった関数群を統合 ---
# # パスの設定を修正
# # プロジェクトのルートディレクトリを動的に取得
# project_root = os.path.expanduser('~/robot_project/')
# ROUTING_DAEMON_PATH = os.path.join(project_root, 'Motor_Driver_HAT_Code/Motor_Driver_HAT_Code/Raspberry Pi/python/node.py')
# RECEIVE_VIDEO_PROGRAM_PATH = os.path.join(project_root, 'robot_video_capture_v1/save_recv.out')


# # --- プロセス管理用グローバル変数 ---
# routing_daemon_process = None
# recv_video_process = None


# # --- プロセス起動・停止関数 ---
# def start_routing_daemon(node_id):
#     global routing_daemon_process
#     if not os.path.exists(ROUTING_DAEMON_PATH):
#         print(f"エラー: ルーティングデーモンのパスが見つかりません: {ROUTING_DAEMON_PATH}")
#         sys.exit(1)
#     print(f"Node {node_id}: ルーティングデーモンを起動します...")
#     routing_daemon_process = subprocess.Popen(
#         ['sudo', 'python3', ROUTING_DAEMON_PATH, str(node_id)],
#         stdout=subprocess.DEVNULL,
#         stderr=subprocess.DEVNULL,
#         preexec_fn=os.setsid
#     )
#     print(f"Node {node_id}: ルーティングデーモン PID: {routing_daemon_process.pid} で起動しました。")

# def stop_routing_daemon():
#     global routing_daemon_process
#     if routing_daemon_process and routing_daemon_process.poll() is None:
#         print("ルーティングデーモンを終了します...")
#         try:
#             routing_daemon_process.terminate()
#             routing_daemon_process.wait(timeout=5)
#             if routing_daemon_process.poll() is None:
#                 print("ルーティングデーモンを強制終了します。")
#                 routing_daemon_process.kill()
#         except Exception as e:
#             print(f"ルーティングデーモン終了中にエラーが発生しました: {e}")
#     else:
#         print("ルーティングデーモンは実行中ではありません。")

# def ignore_sigpipe():
#     signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# def start_receive_video_program():
#     global recv_video_process
#     if not os.path.exists(RECEIVE_VIDEO_PROGRAM_PATH):
#         print(f"エラー: 映像受信プログラムのパスが見つかりません: {RECEIVE_VIDEO_PROGRAM_PATH}")
#         return False
#     print(f"映像受信プログラム ({RECEIVE_VIDEO_PROGRAM_PATH}) を起動します...")
#     recv_video_process = subprocess.Popen([
#         RECEIVE_VIDEO_PROGRAM_PATH,
#         RECEIVE_VIDEO_IP
#     ], preexec_fn=ignore_sigpipe)
#     print(f"映像受信プログラム PID: {recv_video_process.pid} で起動しました。")
#     return True

# def stop_receive_video_program():
#     global recv_video_process
#     if recv_video_process and recv_video_process.poll() is None:
#         print("映像受信プログラムを終了します...")
#         try:
#             recv_video_process.send_signal(signal.SIGINT)
#             time.sleep(2.0)
#             recv_video_process.wait(timeout=10)
#         except subprocess.TimeoutExpired:
#             print("映像受信プログラムを強制終了します。")
#             recv_video_process.kill()
#             recv_video_process.wait()
#         except Exception as e:
#             print(f"映像受信プログラム終了中にエラーが発生しました: {e}")
#     else:
#         print("映像受信プログラムは実行中ではありません。")


# # --- ロボットのIPとポートの定義 ---
# RECEIVE_VIDEO_IP = "192.168.200.10"
# CAMERA_ROBOT_IP = "192.168.200.3"
# CAMERA_ROBOT_PORT = 5000
# RELAY_NODE1_IP = "192.168.200.4"
# RELAY_NODE1_PORT = 5003
# RELAY_NODE2_IP = "192.168.200.2"
# RELAY_NODE2_PORT = 5002

# def send_signal(ip_address, port, signal_data):
#     try:
#         print(f"ロボット ({ip_address}:{port}) へ信号 '{signal_data.decode()}' を送信します...")
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#             s.connect((ip_address, port))
#             s.sendall(signal_data)
#         print("信号を送信しました。")
#         return True
#     except Exception as e:
#         print(f"ロボット ({ip_address}:{port}) への接続に失敗しました: {e}")
#         return False

# # --- Flaskアプリの定義 ---
# app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'web_control'))

# @app.route('/')
# def serve_index():
#     return send_from_directory(app.static_folder, 'index.html')

# @app.route('/<path:filename>')
# def serve_static(filename):
#     return send_from_directory(app.static_folder, filename)

# @app.route('/start_cam_node', methods=['POST'])
# def start_cam_node_api():
#     success = send_signal(CAMERA_ROBOT_IP, CAMERA_ROBOT_PORT, b"start")
#     if success:
#         return jsonify({"status": "success", "message": "CamNode起動信号を送信しました。"}), 200
#     else:
#         return jsonify({"status": "error", "message": "CamNode起動信号の送信に失敗しました。"}), 500

# @app.route('/start_relay_node2', methods=['POST'])
# def start_relay_node2_api():
#     success = send_signal(RELAY_NODE2_IP, RELAY_NODE2_PORT, b"start_move")
#     if success:
#         return jsonify({"status": "success", "message": "RelayNode2移動開始信号を送信しました。"}), 200
#     else:
#         return jsonify({"status": "error", "message": "RelayNode2移動開始信号の送信に失敗しました。"}), 500

# @app.route('/start_relay_node1', methods=['POST'])
# def start_relay_node1_api():
#     success = send_signal(RELAY_NODE1_IP, RELAY_NODE1_PORT, b"start_move")
#     if success:
#         return jsonify({"status": "success", "message": "RelayNode1移動開始信号を送信しました。"}), 200
#     else:
#         return jsonify({"status": "error", "message": "RelayNode1移動開始信号の送信に失敗しました。"}), 500

# def run_server():
#     app.run(host='0.0.0.0', port=8000)

# # --- メイン処理 ---
# if __name__ == "__main__":
#     MY_NODE_ID = 0
#     MY_IP_ADDRESS = NODE_INFO[MY_NODE_ID]

#     # ルーティングデーモンを別プロセスで起動するためのコード
#     start_routing_daemon(MY_NODE_ID)

#     if not start_receive_video_program():
#         print("映像受信プログラムの起動に失敗しました。終了します。")
#         stop_routing_daemon()
#         sys.exit(1)
    
#     server_thread = threading.Thread(target=run_server, daemon=True)
#     server_thread.start()

#     try:
#         print("\nCtlNodeのメイン制御プログラムが実行中です。")
#         print("ウェブサーバーがポート8000で待機しています。")
#         print(f"スマートフォンから以下のURLにアクセスして操作できます: http://{RECEIVE_VIDEO_IP}:8000")
        
#         while True:
#             time.sleep(5)
#     except KeyboardInterrupt:
#         print("\nCtlNode制御プログラムを終了します。")
#     except Exception as e:
#         print(f"予期せぬエラー: {e}")
#     finally:
#         stop_routing_daemon()
#         stop_receive_video_program()
