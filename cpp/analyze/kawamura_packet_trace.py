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
    
    # 大まかな時刻合わせ（time_pref_counter）
    time_prefs = {}
    for node, filepath in log_files.items():
        try:
            # errors='replace' で文字化けによるクラッシュを防止
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
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
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    # 対象外のログはスキップ
                    if 'Ev=' not in line or 'Type=' not in line or 'Seq=' not in line:
                        continue
                        
                    t_match = re.search(r'T=\s*([\d\.]+)', line)
                    if not t_match: continue
                    t_sec = float(t_match.group(1))

                    ev_match = re.search(r'Ev=\s*(\S+)', line)
                    ev_type = ev_match.group(1) if ev_match else ''
                    if 'Send' in ev_type: 
                        ev_type = 'Send' # Send_outside_num 等をSendに統一

                    type_match = re.search(r'Type=\s*([A-Z]+)', line)
                    p_type = type_match.group(1) if type_match else ''
                    
                    seq_match = re.search(r'Seq=\s*(\d+)', line)
                    seq = int(seq_match.group(1)) if seq_match else 0

                    ack_match = re.search(r'ACK=\s*(\d+)', line)
                    ack = int(ack_match.group(1)) if ack_match else None

                    dir_match = re.search(r'Direction=\s*([A-Za-z]+)', line)
                    direction = dir_match.group(1) if dir_match else None
                    
                    events.append({
                        'node': node,
                        'time': t_sec + t_offset,
                        'event': ev_type,
                        'type': p_type,
                        'seq': seq,
                        'ack': ack,
                        'direction': direction
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
        if node in packet_events[key]['recvs']:
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
    # (Type, Seq) の組み合わせでパケットをグループ化
    groups = defaultdict(lambda: {'sends': [], 'recvs': []})
    
    for ev in events:
        key = (ev['type'], ev['seq'])
        if ev['event'] == 'Send':
            groups[key]['sends'].append(ev)
        elif ev['event'] == 'Recv':
            groups[key]['recvs'].append(ev)
            
    for key, group in groups.items():
        sends = group['sends']
        recvs = group['recvs']

        for r in recvs:
            r_id = nodes[r['node']]
            best_s = None
            min_diff = float('inf')
            
            for s in sends:
                # 自身への送信は無視
                if s['node'] == r['node']: 
                    continue

                # VIDEOとDUMMYの場合はACKの一致も確認（CONTROLはACKを無視）
                if r['type'] != 'CONTROL':
                    if s['ack'] is not None and r['ack'] is not None and s['ack'] != r['ack']:
                        continue

                # トポロジの隣接チェック (ノードの飛び越えを防止)
                s_id = nodes[s['node']]
                is_valid = False

                if s['direction'] == 'Up' and r_id == s_id + 1: 
                    is_valid = True
                elif s['direction'] == 'Down' and r_id == s_id - 1: 
                    is_valid = True
                elif not s['direction']: # CtlNやCamNなどの始点
                    if s['node'] == 'CtlN' and r_id == s_id + 1: is_valid = True
                    elif s['node'] == 'CamN' and r_id == s_id - 1: is_valid = True

                if not is_valid:
                    continue

                # 時間差の許容範囲チェック
                diff = r['time'] - s['time']
                if -0.05 <= diff <= 1.0:
                    abs_diff = abs(diff)
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
            alpha = 1.0
            linewidth = 1.5
        elif link['type'] == 'VIDEO':
            color = 'orange'
            alpha = 0.7
            linewidth = 1.0
        elif link['type'] == 'DUMMY':
            color = 'gray'
            alpha = 0.5
            linewidth = 1.0
        else:
            color = 'black'
            alpha = 0.5
            linewidth = 1.0
            
        ax.plot(x, y, color=color, linewidth=linewidth, alpha=alpha, marker='o', markersize=2)

    ax.set_ylim(end_time, start_time)
    ax.set_ylabel('Synchronized Time (s) [Hop Interval = 0.001s]')
    ax.set_title(f'MUCViS Packet Trace\nRange: {start_time}s - {end_time}s')
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python3 script.py \"pattern\" start duration")
        sys.exit(1)
    
    log_files = resolve_log_files(sys.argv[1])
    events = parse_logs(log_files)
    
    events = apply_initial_packet_sync(events, base_delay=0.001) 
    
    links = extract_links(events)
    plot_sequence(links, float(sys.argv[2]), float(sys.argv[3]))