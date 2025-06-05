import sys
import socket
import threading
import time
import subprocess
# import json # ノードIDとIPアドレスのマッピングのために使用

# 環境設定
# 実際には、NodeIDとIPの対応は設定ファイルやDiscoveryで得る
NODE_INFO = {
    0: "192.168.200.4", # ctlNode
    1: "192.168.200.2", # 後方ロボット
    2: "192.168.200.3", # カメラロボット
    # ... 他のノードがあれば追加
}
# 各端末が自身のIPアドレスを持つので、0, 1, 2は最後のオクテットとする
IP_NETMASK_PREFIX = "192.168.200"
BROADCAST_PORT = 12345
UNICAST_PORT = 12346
BEACON_INTERVAL = 5 # 秒

MIN_NODE_ID = 0
MAX_NODE_ID = 2 # 3端末なので0, 1, 2

# 自ノードのID (コマンドライン引数で受け取る)
# MY_NODE_ID = int(sys.argv[1])
# MY_IP_ADDRESS = f"{IP_NETMASK_PREFIX}.{MY_NODE_ID}"

# ルーティング設定用のIPアドレス（各ノードが持つ仮想IPを想定）
# 例: 192.168.200.4 for ctlNode, 192.168.200.2 for 後方ロボット, 192.168.200.3 for カメラロボット

# 応答が来たノードのリスト (グローバル変数またはクラス変数)
# [NodeID, Source_IP_Address] のタプルを格納
# RESPONDER_LIST = []
# RESPONDER_LIST_LOCK = threading.Lock() # リストへのアクセスを保護

try:
    # 自ノードのID (コマンドライン引数で受け取る)
    MY_NODE_ID = int(sys.argv[1])
    if not (MIN_NODE_ID <= MY_NODE_ID <= MAX_NODE_ID):
        print(f"エラー: ノードID {MY_NODE_ID} は範囲外です [{MIN_NODE_ID}-{MAX_NODE_ID}]。")
        sys.exit(1)
    if MY_NODE_ID not in NODE_INFO:
        print(f"エラー: ノードID {MY_NODE_ID} は NODE_INFO に定義されていません。")
        sys.exit(1)
    MY_IP_ADDRESS = NODE_INFO[MY_NODE_ID] # NODE_INFOからIPアドレスを取得
except IndexError:
    print(f"エラー: ノードIDがコマンドライン引数として提供されていません。")
    print(f"使用法: python <スクリプト名>.py <my_node_id>") # スクリプト名は node.py になります
    sys.exit(1)
except ValueError:
    print(f"エラー: ノードID '{sys.argv[1]}' は有効な整数ではありません。")
    sys.exit(1)


class Node:
    def __init__(self, node_id, ip_address, node_info):
        self.node_id = node_id
        self.ip_address = ip_address
        self.node_info = node_info # 全ノードのIDとIPのマッピング
        self.responder_list = [] # 応答が来たノードIDを保存
        self.min_scope_id = node_id
        self.max_scope_id = node_id
        self.responder_list_lock = threading.Lock()
        

        print(f"Node {self.node_id} ({self.ip_address}) initialized.")

    def _update_ip_route(self, dest_ip, via_ip):
        """
        Linuxのip routeコマンドを使ってルーティングテーブルを更新する
        sudo権限が必要
        """
        # cmd = f"sudo ip route replace {dest_ip} via {via_ip}"
        cmd_list = ["sudo", "ip", "route", "replace", dest_ip, "via", via_ip]
        try:
            # subprocess.run(cmd.split(), check=True)
            subprocess.run(cmd_list, check=True)    
            # print(f"  [Route] Updated: {dest_ip} via {via_ip}")
        except subprocess.CalledProcessError as e:
            print(f"  [ERROR] Failed to update route: {e}")
        except FileNotFoundError:
            print(f"  [ERROR] 'ip' command not found. Ensure iproute2 is installed and in PATH.")

    def _calculate_scope(self):
        """
        responder_listに基づいて通信範囲 (scope) を計算する
        """
        # with RESPONDER_LIST_LOCK:
        with self.responder_list_lock:
            current_responders = sorted([r[0] for r in self.responder_list])
            if not current_responders:
                # 応答が一つもない場合は、自身のIDのみをスコープとする
                self.min_scope_id = self.node_id
                self.max_scope_id = self.node_id
                return

            self.min_scope_id = self.node_id
            self.max_scope_id = self.node_id

            for rid in current_responders:
                # if rid < self.node_id and rid < self.min_scope_id:
                #     self.min_scope_id = rid
                # if rid > self.node_id and rid > self.max_scope_id:
                #     self.max_scope_id = rid
                    
                if rid < self.node_id: # 自分より小さいIDの応答ノード
                    self.min_scope_id = min(self.min_scope_id, rid)
                if rid > self.node_id: # 自分より大きいIDの応答ノード
                    self.max_scope_id = max(self.max_scope_id, rid)
            
            # ビーコンロスの補正（隣接ノードを超える端末へのルーティングを考慮）
            # 初期設定の「i-2とi+2へパケットを送信する際にはi-1, i+1へそれぞれパケットを送信するようにルーティングを設定しておく」
            # これに準拠させるために、最小範囲を自身のID-1、最大範囲を自身のID+1とする
            # ただし、ネットワークの端（MIN_NODE_ID, MAX_NODE_ID）の場合は調整
            
            # 自身のIDがスコープの最小値であり、かつ最小ノードIDではない場合、隣接ノードをスコープに含める
            # if self.node_id == self.min_scope_id and self.node_id > MIN_NODE_ID:
            #     if (self.node_id - 1) not in current_responders: # 隣が応答していない場合でも、ルーティングでは考慮する
            #         self.min_scope_id = self.node_id - 1
            if self.min_scope_id == self.node_id and self.node_id > MIN_NODE_ID:
                self.min_scope_id = self.node_id - 1 # 隣接ノード (ID-1) をスコープに含める
            
            
            # 自身のIDがスコープの最大値であり、かつ最大ノードIDではない場合、隣接ノードをスコープに含める
            # if self.node_id == self.max_scope_id and self.node_id < MAX_NODE_ID:
            #     if (self.node_id + 1) not in current_responders: # 隣が応答していない場合でも、ルーティングでは考慮する
            #         self.max_scope_id = self.node_id + 1
            if self.max_scope_id == self.node_id and self.node_id < MAX_NODE_ID:
                self.max_scope_id = self.node_id + 1 # 隣接ノード (ID+1) をスコープに含める

        print(f"  [Scope] Node {self.node_id}: Scope calculated to be {self.min_scope_id} to {self.max_scope_id}")


    def _update_routing_table(self):
        """
        計算されたscopeに基づいてルーティングテーブルを更新する
        """
        self._calculate_scope() # 最新のresponder_listでscopeを再計算

        print(f"  [Routing] Updating routes for Node {self.node_id}...")
        for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
            if dst_node_id == self.node_id:
                continue # 自分自身へのルーティングは不要

            dest_ip = self.node_info[dst_node_id]

            if dst_node_id < self.min_scope_id:
                # a 未満のノードに対しては a を経由
                via_node_id = self.min_scope_id
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    {self.node_id} -> {dst_node_id} (via {via_node_id})")

            elif self.min_scope_id <= dst_node_id <= self.max_scope_id:
                # a 以上 b 以下のノードに対しては直接ルーティング
                self._update_ip_route(dest_ip, dest_ip)
                print(f"    {self.node_id} -> {dst_node_id} (direct)")

            elif dst_node_id > self.max_scope_id:
                # b より大きいノードに対しては b を経由
                via_node_id = self.max_scope_id
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    {self.node_id} -> {dst_node_id} (via {via_node_id})")
        
        # responder_listをクリア（次のブロードキャストに備える）
        # with RESPONDER_LIST_LOCK:
        with self.responder_list_lock:    
            self.responder_list.clear()


    def _send_beacon(self):
        """
        自身のNodeIDを含んだビーコンパケットをブロードキャストする
        """
        # sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # sock.bind((self.ip_address, BROADCAST_PORT)) # ブロードキャストを送信するインターフェースにバインド

        # message = f"BEACON:{self.node_id}".encode('utf-8')
        # broadcast_address = f"{IP_NETMASK_PREFIX}.255" # 例: 192.168.201.255
        
        # print(f"[Beacon Sender] Node {self.node_id} sending beacon to {broadcast_address}:{BROADCAST_PORT}")
        # sock.sendto(message, (broadcast_address, BROADCAST_PORT))
        # sock.close()
        
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # 送信元IPアドレスを固定し、送信元ポートはOSに任せる (0を指定)
            sock.bind((self.ip_address, 0))

            message = f"BEACON:{self.node_id}".encode('utf-8')
            broadcast_address = f"{IP_NETMASK_PREFIX}.255" # 例: 192.168.200.255
            print(f"[Beacon Sender] Node {self.node_id} sending beacon to {broadcast_address}:{BROADCAST_PORT}")
            sock.sendto(message, (broadcast_address, BROADCAST_PORT))

    def beacon_sender_thread(self):
        """
        ビーコンを定期的に送信し、ルーティングを更新するスレッド
        """
        # 初期ルーティング設定: 各端末iは隣接するノードを超える端末に対して(i-2とi+2)へパケットを送信する際には
        # i-1, i+1へそれぞれパケットを送信するようにルーティングを設定しておく
        print(f"Node {self.node_id} performing initial route setup...")
        for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
            if dst_node_id == self.node_id:
                continue
            
            dest_ip = self.node_info[dst_node_id]
            
            if dst_node_id < self.node_id - 1: # i-2以下
                via_node_id = self.node_id - 1 if self.node_id - 1 >= MIN_NODE_ID else MIN_NODE_ID
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    Initial: {self.node_id} -> {dst_node_id} (via {via_node_id})")

            elif dst_node_id > self.node_id + 1: # i+2以上
                via_node_id = self.node_id + 1 if self.node_id + 1 <= MAX_NODE_ID else MAX_NODE_ID
                via_ip = self.node_info[via_node_id]
                self._update_ip_route(dest_ip, via_ip)
                print(f"    Initial: {self.node_id} -> {dst_node_id} (via {via_node_id})")
            else: # 隣接ノード (i-1, i+1) または直接接続想定
                self._update_ip_route(dest_ip, dest_ip)
                print(f"    Initial: {self.node_id} -> {dst_node_id} (direct)")


        while True:
            self._send_beacon()
            time.sleep(BEACON_INTERVAL) # ビーコン送信間隔
            self._update_routing_table() # ビーコンを送信した後にルーティングを更新


    def beacon_responder_thread(self):
        """
        ビーコンパケットを受信し、応答をユニキャストするスレッド
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', BROADCAST_PORT)) # 全てのインターフェースからのブロードキャストを受信

        response_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # 応答用ソケット

        print(f"[Beacon Responder] Node {self.node_id} listening for beacons on port {BROADCAST_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                
                if message.startswith("BEACON:"):
                    sender_id = int(message.split(":")[1])
                    sender_ip = addr[0] # ブロードキャストの送信元IP

                    if sender_id == self.node_id:
                        continue # 自身からのブロードキャストは無視

                    print(f"  [Responder] Node {self.node_id} received beacon from Node {sender_id} ({sender_ip})")
                    
                    # 応答（自身のNodeID）をユニキャストで返す
                    response_message = f"RESPONSE:{self.node_id}".encode('utf-8')
                    try:
                        # ビーコンの送信元IPへユニキャストで応答
                        response_sock.sendto(response_message, (sender_ip, UNICAST_PORT))
                        print(f"  [Responder] Node {self.node_id} sent response to {sender_ip}:{UNICAST_PORT}")
                    except Exception as e:
                        print(f"  [ERROR] Failed to send response to {sender_ip}: {e}")

            except socket.timeout:
                continue # タイムアウトは無視
            except Exception as e:
                print(f"  [ERROR] Beacon Responder Error: {e}")

    def unicast_receiver_thread(self):
        """
        ユニキャストの応答パケットを受信するスレッド
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', UNICAST_PORT)) # 全てのインターフェースからのユニキャストを受信

        print(f"[Unicast Receiver] Node {self.node_id} listening for responses on port {UNICAST_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')

                if message.startswith("RESPONSE:"):
                    responder_id = int(message.split(":")[1])
                    responder_ip = addr[0]

                    if responder_id == self.node_id:
                        continue # 自身からの応答は無視

                    print(f"  [Receiver] Node {self.node_id} received response from Node {responder_id} ({responder_ip})")
                    
                    # with RESPONDER_LIST_LOCK:
                    with self.responder_list_lock:  
                        # 既にリストに存在するか確認し、なければ追加
                        if (responder_id, responder_ip) not in self.responder_list:
                            self.responder_list.append((responder_id, responder_ip))
                            # print(f"  [Receiver] Updated responder_list: {self.responder_list}")

            except socket.timeout:
                continue
            except Exception as e:
                print(f"  [ERROR] Unicast Receiver Error: {e}")

    def start(self):
        """
        ノードの全スレッドを開始する
        """
        # ビーコン送信＆ルーティング設定スレッド
        beacon_sender_t = threading.Thread(target=self.beacon_sender_thread, daemon=True)
        beacon_sender_t.start()

        # ビーコン応答スレッド
        beacon_responder_t = threading.Thread(target=self.beacon_responder_thread, daemon=True)
        beacon_responder_t.start()

        # ユニキャスト受信スレッド (応答パケットを受け取る側)
        unicast_receiver_t = threading.Thread(target=self.unicast_receiver_thread, daemon=True)
        unicast_receiver_t.start()

        # メインスレッドはそのまま待機、または他の処理を実行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"Node {self.node_id} shutting down.")