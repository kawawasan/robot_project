import sys
import glob
import os
import re
import matplotlib.pyplot as plt
from collections import defaultdict

nodes = {
    'CtlN': 0,
    'RN1': 1,
    'RN2': 2,
    'CamN': 3
}

def resolve_log_files(file_pattern):
    expanded_pattern = os.path.expanduser(file_pattern)
    matched_files = glob.glob(expanded_pattern)
    
    log_files = {}
    for filepath in matched_files:
        basename = os.path.basename(filepath)
        if 'CtlN' in basename or 'cn'in basename or 'CN'in basename:
            log_files['CtlN'] = filepath
        elif 'RN1' in basename:
            log_files['RN1'] = filepath
        elif 'RN2' in basename:
            log_files['RN2'] = filepath
        elif 'CamN' in basename:
            log_files['CamN'] = filepath
    return log_files

def parse_logs(log_files):
    events = []
    pattern = re.compile(r'T=\s*([0-9.]+)\s+Ev=\s*(Send|Recv)\s+Type=\s*([A-Z]+).*?Seq=\s*(\d+)')
    
    for node, filepath in log_files.items():
        time_offset = 0.0
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    # ヘッダから絶対時刻のオフセットを取得して時刻ズレを補正
                    if 'time_pref_counter=' in line:
                        m = re.search(r'time_pref_counter=\s*(\d+)', line)
                        if m:
                            time_offset = int(m.group(1)) / 1e9
                            
                    match = pattern.search(line)
                    if match:
                        t = float(match.group(1))
                        ev = match.group(2)
                        p_type = match.group(3)
                        seq = int(match.group(4))
                        events.append({
                            'node': node,
                            'global_time': t + time_offset, # 絶対時刻
                            'event': ev,
                            'type': p_type,
                            'seq': seq
                        })
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            
    # 全ノードの中で一番早い時間を0秒にリセット（引数のstart_timeと感覚を合わせるため）
    if events:
        min_global_time = min(e['global_time'] for e in events)
        for e in events:
            e['time'] = e['global_time'] - min_global_time
            
    events.sort(key=lambda x: x['time'])
    return events

def extract_links(events):
    links = []
    send_history = defaultdict(list)
    
    for ev in events:
        if ev['type'] not in ['CONTROL', 'VIDEO', 'DUMMY']:
            continue
            
        key = (ev['type'], ev['seq'])
        
        if ev['event'] == 'Send':
            send_history[key].append(ev)
        elif ev['event'] == 'Recv':
            best_send = None
            min_diff = float('inf')
            
            # このRecvの直前に送信された、同じパケットを探す
            for s in send_history[key]:
                diff = ev['time'] - s['time']
                # 時間が逆行しておらず、0.5秒以内の遅延のもの
                if 0 <= diff < 0.5:
                    if diff < min_diff:
                        min_diff = diff
                        best_send = s
            
            if best_send and best_send['node'] != ev['node']:
                # 各ノードのインデックス（位置）を取得
                sender_idx = nodes[best_send['node']]
                recv_idx = nodes[ev['node']]
                
                # 【追加】パケットの種類によって、流れる方向を強制的に制約する
                if ev['type'] == 'CONTROL' and sender_idx >= recv_idx:
                    continue  # CONTROLは必ず CtlN(0) -> CamN(3) の方向（右向き）
                if ev['type'] == 'VIDEO' and sender_idx <= recv_idx:
                    continue  # VIDEOは必ず CamN(3) -> CtlN(0) の方向（左向き）
                # DUMMYも主にCamN->CtlNに流れる場合は以下を有効化しても良いです
                # if ev['type'] == 'DUMMY' and sender_idx <= recv_idx:
                #     continue

                links.append({
                    'type': ev['type'],
                    'seq': ev['seq'],
                    'sender_node': best_send['node'],
                    'sender_time': best_send['time'],
                    'receiver_node': ev['node'],
                    'receiver_time': ev['time']
                })
    return links

def plot_sequence(links, start_time, duration):
    end_time = start_time + duration
    fig, ax = plt.subplots(figsize=(10, 8))
    
    for node, x in nodes.items():
        ax.axvline(x=x, color='black', linestyle='-', alpha=0.3)
        ax.text(x, start_time - duration * 0.02, node, 
                ha='center', va='bottom', fontsize=12, fontweight='bold')

    for link in links:
        if not ((start_time <= link['sender_time'] <= end_time) or 
                (start_time <= link['receiver_time'] <= end_time)):
            continue
            
        x_values = [nodes[link['sender_node']], nodes[link['receiver_node']]]
        y_values = [link['sender_time'], link['receiver_time']]
        
        if link['type'] == 'CONTROL':
            color = 'blue'
            alpha = 0.5
            zorder = 3
        elif link['type'] == 'VIDEO':
            color = 'orange'
            alpha = 0.5
            zorder = 2
        elif link['type'] == 'DUMMY':
            color = 'gray'
            alpha = 0.3
            zorder = 1
        
        # 矢印（ax.annotate）を削除し、ax.plotに marker='o', markersize=3 を追加
        ax.plot(x_values, y_values, color=color, linewidth=1.5, 
                alpha=alpha, zorder=zorder, marker='o', markersize=3)

    ax.set_xlim(-0.5, 3.5)
    ax.set_ylim(end_time, start_time) 
    ax.set_xticks(list(nodes.values()))
    ax.set_xticklabels(list(nodes.keys()))
    ax.set_ylabel('Time (s)')
    ax.set_title(f'Packet Flow Sequence ({start_time}s - {end_time}s)')
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.show()
if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("【使い方】 python plot_packets.py <log_file_pattern> <start_time> <duration>")
        sys.exit(1)

    file_pattern = sys.argv[1]
    start_time = float(sys.argv[2])
    duration = float(sys.argv[3])

    log_files = resolve_log_files(file_pattern)
    events = parse_logs(log_files)
    links = extract_links(events)
    plot_sequence(links, start_time, duration)