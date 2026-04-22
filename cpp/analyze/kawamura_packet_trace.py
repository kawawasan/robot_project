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
        if any(x in basename for x in ['CtlN', 'cn', 'CN']):
            log_files['CtlN'] = filepath
        elif 'RN1' in basename: log_files['RN1'] = filepath
        elif 'RN2' in basename: log_files['RN2'] = filepath
        elif 'CamN' in basename: log_files['CamN'] = filepath
    return log_files

def parse_logs(log_files):
    events = []
    pattern = re.compile(r'T=\s*([\d\.]+)\s+Ev=\s*(Send|Recv|Send_outside_num_\d+)\s+Type=\s*([A-Z]+).*?Seq=\s*(\d+)')
    
    # 大まかな時刻合わせ（time_pref_counter）
    time_prefs = {}
    for node, filepath in log_files.items():
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    if 'time_pref_counter=' in line:
                        m = re.search(r'time_pref_counter=\s*(\d+)', line)
                        if m:
                            time_prefs[node] = int(m.group(1))
                        break
        except Exception as e:
            print(f"Header Error: {filepath}: {e}")
            
    if not time_prefs:
        return []
        
    min_pref = min(time_prefs.values())
    
    for node, filepath in log_files.items():
        node_pref = time_prefs.get(node, min_pref)
        t_offset = (node_pref - min_pref) / 1e9 
        
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    match = pattern.search(line)
                    if match:
                        t_sec = float(match.group(1))
                        ev_type = match.group(2)
                        
                        if 'Send' in ev_type:
                            ev_type = 'Send'
                            
                        p_type = match.group(3)
                        seq = int(match.group(4))
                        
                        events.append({
                            'node': node,
                            'time': t_sec + t_offset,
                            'event': ev_type,
                            'type': p_type,
                            'seq': seq
                        })
        except Exception as e:
            print(f"Read Error: {filepath}: {e}")
            
    events.sort(key=lambda x: x['time'])
    return events

def apply_initial_packet_sync(events, base_delay=0.001):
    """最初のパケットを基準にして、全ノードの時間軸を固定オフセットで補正する"""
    packet_events = defaultdict(lambda: {'sends': {}, 'recvs': {}})
    for e in events:
        key = (e['type'], e['seq'])
        if e['event'] == 'Send' and e['node'] not in packet_events[key]['sends']:
            packet_events[key]['sends'][e['node']] = e
        elif e['event'] == 'Recv' and e['node'] not in packet_events[key]['recvs']:
            packet_events[key]['recvs'][e['node']] = e

    target_nodes = ['RN1', 'RN2', 'CamN']
    ref_seq, ref_type = None, None
    
    # CtlNからの最初のCONTROLパケットを探す
    ctln_sends = [e for e in events if e['node'] == 'CtlN' and e['event'] == 'Send' and e['type'] == 'CONTROL']
    for s in ctln_sends:
        key = (s['type'], s['seq'])
        recvs = packet_events[key]['recvs']
        if all(node in recvs for node in target_nodes):
            ref_seq = s['seq']
            ref_type = s['type']
            break

    if ref_seq is None:
        print("Warning: 基準パケットが見つかりませんでした。")
        return events

    print(f"Sync Reference: {ref_type} Seq={ref_seq} を基準に時間軸を補正します（ホップ間隔: {base_delay}s）")
    
    key = (ref_type, ref_seq)
    t_cn = packet_events[key]['sends']['CtlN']['time']
    
    offsets = {'CtlN': 0.0}
    # 管内の直鎖状トポロジに基づく理想遅延の加算 (0.001s, 0.002s, 0.003s)
    hop_delays = {'RN1': base_delay * 1, 'RN2': base_delay * 2, 'CamN': base_delay * 3}
    
    for node in target_nodes:
        t_recv = packet_events[key]['recvs'][node]['time']
        ideal_time = t_cn + hop_delays[node]
        offsets[node] = ideal_time - t_recv

    # 全パケットにオフセットを適用して時計を完全同期
    for e in events:
        e['time'] += offsets.get(e['node'], 0.0)
        
    events.sort(key=lambda x: x['time'])
    return events

def extract_links(events):
    links = []
    groups = defaultdict(lambda: {'sends': [], 'recvs': []})
    
    for ev in events:
        key = (ev['type'], ev['seq'])
        if ev['event'] == 'Send':
            groups[key]['sends'].append(ev)
        elif ev['event'] == 'Recv':
            groups[key]['recvs'].append(ev)
            
    for key, group in groups.items():
        for r in group['recvs']:
            best_s = None
            min_diff = float('inf')
            
            for s in group['sends']:
                if s['node'] == r['node']: 
                    continue
                    
                diff = r['time'] - s['time']
                
                # 時計が合っているため、方向(上り/下り)に関わらず「少し過去の送信」が常に正解になる
                # わずかな揺らぎ(-0.05秒)〜長めの遅延(1.0秒)を許容
                if -0.05 <= diff <= 1.0:
                    abs_diff = abs(diff)
                    # 一番時間差が小さい＝一番手前で中継してくれたノード
                    if abs_diff < min_diff:
                        min_diff = abs_diff
                        best_s = s
                        
            if best_s:
                links.append({
                    'type': r['type'],
                    'seq': r['seq'],
                    'sender_node': best_s['node'],
                    'sender_time': best_s['time'],
                    'receiver_node': r['node'],
                    'receiver_time': r['time']
                })
                
    return links

def plot_sequence(links, start_time, duration):
    end_time = start_time + duration
    fig, ax = plt.subplots(figsize=(12, 8))
    
    for node, x in nodes.items():
        ax.axvline(x=x, color='black', linestyle='-', alpha=0.3)
        ax.text(x, start_time - duration*0.02, node, ha='center', fontweight='bold')

    for link in links:
        if not (start_time <= link['sender_time'] <= end_time):
            continue
            
        x = [nodes[link['sender_node']], nodes[link['receiver_node']]]
        y = [link['sender_time'], link['receiver_time']]
        
        if link['type'] == 'CONTROL':
            color = 'blue'
        elif link['type'] == 'VIDEO':
            color = 'orange'
        elif link['type'] == 'DUMMY':
            color = 'gray'
        else:
            color = 'black'
            
        ax.plot(x, y, color=color, linewidth=1.0, alpha=0.7, marker='o', markersize=2)

    ax.set_ylim(end_time, start_time)
    ax.set_ylabel(f'Synchronized Time (s) [Hop Interval = 0.001s]')
    ax.set_title(f'MUCViS Packet Trace\nRange: {start_time}s - {end_time}s')
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python3 script.py \"pattern\" start duration")
        sys.exit(1)
    
    log_files = resolve_log_files(sys.argv[1])
    events = parse_logs(log_files)
    
    # ここでご指定の「間隔 0.001s」を引数として渡しています
    events = apply_initial_packet_sync(events, base_delay=0.001) 
    
    links = extract_links(events)
    plot_sequence(links, float(sys.argv[2]), float(sys.argv[3]))