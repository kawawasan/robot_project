# node_class.py
import sys
import socket
import threading
import time
import subprocess
import json
import os

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
        self.responder_list = [] # インスタンス固有のリスト
        self.responder_list_lock = threading.Lock() # インスタンス固有のロック
        self.min_scope_id = node_id
        self.max_scope_id = node_id

        print(f"Node {self.node_id} ({self.ip_address}) initialized.")

    def _update_ip_route(self, dest_ip, via_ip):
        cmd = f"sudo ip route replace {dest_ip} via {via_ip}"
        try:
            subprocess.run(cmd.split(), check=True)
            # print(f"  [Route] Updated: {dest_ip} via {via_ip}") # デバッグ用
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

            # ビーコンロスの補正（隣接ノードをスコープに含めるロジック）
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
        # 初期ルーティング設定
        print(f"Node {self.node_id} performing initial route setup...")
        for dst_node_id in range(MIN_NODE_ID, MAX_NODE_ID + 1):
            if dst_node_id == self.node_id:
                continue
            
            dest_ip = self.node_info[dst_node_id]
            
            # 初期設定は、隣接ノード(i-1, i+1)はdirect、それ以外は隣接ノード経由
            if abs(dst_node_id - self.node_id) == 1: # 隣接ノードの場合
                self._update_ip_route(dest_ip, dest_ip)
                print(f"    Initial: {self.node_id} -> {dst_node_id} (direct)")
            else: # 隣接しないノードの場合
                if dst_node_id < self.node_id: # 上流方向
                    via_node_id = self.node_id - 1
                else: # 下流方向
                    via_node_id = self.node_id + 1
                
                # ネットワークの端の場合の補正
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