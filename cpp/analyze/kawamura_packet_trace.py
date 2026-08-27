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
    
    # OS時間の同期
    time_prefs = {}
    for node, filepath in log_files.items():
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if 'time_pref_counter=' in line:
                        m = re.search(r'time_pref_counter=\s*(\d+)', line)
                        if m: time_prefs[node] = int(m.group(1))
                        break
        except Exception: pass
            
    min_pref = min(time_prefs.values()) if time_prefs else 0
    
    for node, filepath in log_files.items():
        node_pref = time_prefs.get(node, min_pref)
        t_offset = (node_pref - min_pref) / 1e9 
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if 'Ev=' not in line or 'Seq=' not in line: continue
                        
                    t_match = re.search(r'T=\s*([\d\.]+)', line)
                    if not t_match: continue
                    t_sec = float(t_match.group(1))

                    ev_match = re.search(r'Ev=\s*(\S+)', line)
                    raw_ev = ev_match.group(1) if ev_match else ''

                    type_match = re.search(r'Type=\s*([A-Z_]+)', line)
                    p_type = type_match.group(1) if type_match else ''
                    
                    is_gen_cmd = 'Generate_Command' in raw_ev
                    is_exec_cmd = 'Command' in raw_ev and not is_gen_cmd

                    if is_gen_cmd or is_exec_cmd:
                        if not p_type: p_type = 'CONTROL'

                    if not p_type: continue
                    
                    seq_match = re.search(r'Seq=\s*(\d+)', line)
                    seq = int(seq_match.group(1)) if seq_match else 0
                    
                    # 🌟 追加: Directionのパース（これで正しいフィルタリングが機能します）
                    dir_match = re.search(r'Direction=\s*([A-Za-z]+)', line)
                    direction = dir_match.group(1) if dir_match else None
                    
                    events.append({
                        'node': node,
                        'time': t_sec + t_offset, 
                        'event': raw_ev,
                        'is_send': 'Send' in raw_ev,
                        'is_recv': raw_ev == 'Recv',
                        'is_gen_cmd': is_gen_cmd,
                        'is_exec_cmd': is_exec_cmd,
                        'type': p_type,
                        'seq': seq,
                        'direction': direction  # 辞書に追加
                    })
        except Exception as e:
            print(f"Read Error: {filepath}: {e}")
            
    events.sort(key=lambda x: x['time'])
    return events

def extract_links(events):
    links = []
    cmds = []
    
    groups = defaultdict(lambda: {'sends': [], 'recvs': []})
    for ev in events:
        if ev['is_gen_cmd'] or ev['is_exec_cmd']:
            cmds.append(ev)
            continue
            
        key = (ev['type'], ev['seq'])
        if ev['is_send']: groups[key]['sends'].append(ev)
        elif ev['is_recv']: groups[key]['recvs'].append(ev)

    def get_intended_dest_for_ctln(raw_ev):
        if 'outside_num_2' in raw_ev: return 'RN2'
        if 'outside_num_3' in raw_ev: return 'RN1'
        return None
            
    for key, group in groups.items():
        sends = sorted(group['sends'], key=lambda x: x['time'])
        recvs = sorted(group['recvs'], key=lambda x: x['time'])
        
        # 🚨 used_sends (1対1の制約) を完全撤廃！
        # 同軸ケーブルなので、1つのSendを複数のノードが受信するのが物理的に正しい挙動です。

        for r in recvs:
            r_node = r['node']
            best_s = None
            min_diff = float('inf')
            
            for s in sends:
                s_node = s['node']
                if s_node == r_node: continue 
                
                # 🌟 トポロジーフィルタの厳密化
                if s_node == 'CtlN':
                    intended_dest = get_intended_dest_for_ctln(s['event'])
                    if intended_dest and intended_dest != r_node:
                        continue 
                    if nodes[r_node] <= nodes[s_node]: continue
                else:
                    s_dir = s.get('direction')
                    # Up送信（CtlN方向）なら、受信側は自分よりインデックスが小さいべき
                    if s_dir == 'Up' and nodes[r_node] >= nodes[s_node]: continue
                    # Down送信（CamN方向）なら、受信側は自分よりインデックスが大きいべき
                    if s_dir == 'Down' and nodes[r_node] <= nodes[s_node]: continue

                r_dir = r.get('direction')
                # Up受信（CtlN側からの受信）なら、送信側は自分よりインデックスが小さいべき
                if r_dir == 'Up' and nodes[s_node] >= nodes[r_node]: continue
                # Down受信（CamN側からの受信）なら、送信側は自分よりインデックスが大きいべき
                if r_dir == 'Down' and nodes[s_node] <= nodes[r_node]: continue

                diff = r['time'] - s['time']
                p_type = key[0]
                allowed_delay = 0.5 if p_type == 'DUMMY' else 2.0
                
                # 🌟 時刻同期の微小なズレ（マイナス遅延）を許容
                if -0.1 <= diff <= allowed_delay:
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
                
    return links, cmds

def plot_sequence(links, cmds, start_time, duration):
    end_time = start_time + duration
    
    # 論文用のプレーンでアカデミックなフォント設定
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.size': 14,
        'axes.linewidth': 1.2,
    })

    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    
    colors = {
        'VIDEO': '#E66100',    
        'CONTROL': "#0C5BEE",  
    }

    for node, x in nodes.items():
        ax.axvline(x=x, color='#D0D0D0', linestyle='--', linewidth=1.5, zorder=1)
        ax.text(x, start_time - duration*0.015, node, ha='center', va='bottom', 
                fontweight='bold', fontsize=16, 
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.9, pad=2))

    for link in links:
        min_t = min(link['sender_time'], link['receiver_time'])
        max_t = max(link['sender_time'], link['receiver_time'])
        if max_t < start_time or min_t > end_time:
            continue
            
        x = [nodes[link['sender_node']], nodes[link['receiver_node']]]
        y = [link['sender_time'], link['receiver_time']]
        
        p_type = link['type']
        base_color = colors.get(p_type, '#000000')

        # パケット軌跡（CONTROLの場合はこの線が送受信を表す）
        ax.plot(x, y, color=base_color, linewidth=1.0, alpha=0.7, zorder=3, label=p_type)
        ax.scatter(x, y, color=base_color, s=40, edgecolor='white', linewidth=1.0, zorder=4)

    cmd_gen_labeled = False
    
    # コマンドのプロット（生成のみを描画し、白抜きは描画しない）
    for cmd in cmds:
        t = cmd['time']
        if t < start_time or t > end_time: continue
            
        x = nodes.get(cmd['node'])
        if x is not None:
            if cmd['is_gen_cmd']:
                # 生成 (CN): 塗りつぶしの小さな四角
                lbl = 'Generate Control' if not cmd_gen_labeled else None
                ax.scatter(x, t, color="#0C5BEE", marker='s', s=30, edgecolor='white', linewidth=1.0, zorder=6, label=lbl)
                cmd_gen_labeled = True
            # is_exec_cmd (白抜きの四角) の描画ブロックは削除しました

    ax.set_ylim(end_time, start_time)
    ax.set_ylabel('Elapsed Time (s)', fontsize=20, fontweight='bold', labelpad=15)
    ax.grid(True, axis='y', linestyle=':', color='#E0E0E0', linewidth=1.5, zorder=0)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.xaxis.set_ticks_position('none')
    ax.set_xticklabels([])

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    if by_label:
        ax.legend(by_label.values(), by_label.keys(), 
                  loc='upper right', bbox_to_anchor=(1.35, 1.0),
                  frameon=True, fancybox=False, edgecolor='#CCCCCC', fontsize=12)

    # ax.set_title('MUCViS Packet Trace (Control Signal Dynamics)', fontsize=18, fontweight='bold', pad=30)
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python3 script.py \"pattern\" start duration")
        sys.exit(1)
    
    log_files = resolve_log_files(sys.argv[1])
    events = parse_logs(log_files)
    links, cmds = extract_links(events)
    plot_sequence(links, cmds, float(sys.argv[2]), float(sys.argv[3]))
# import sys
# import glob
# import os
# import re
# import matplotlib.pyplot as plt
# from collections import defaultdict

# nodes = {
#     'CtlN': 0,
#     'RN1': 1,
#     'RN2': 2,
#     'CamN': 3
# }

# def resolve_log_files(file_pattern):
#     expanded_pattern = os.path.expanduser(file_pattern)
#     matched_files = glob.glob(expanded_pattern)
#     log_files = {}
#     for filepath in matched_files:
#         basename = os.path.basename(filepath)
#         if any(x in basename for x in ['CtlN', 'cn', 'CN']):
#             log_files['CtlN'] = filepath
#         elif 'RN1' in basename: log_files['RN1'] = filepath
#         elif 'RN2' in basename: log_files['RN2'] = filepath
#         elif 'CamN' in basename: log_files['CamN'] = filepath
#     return log_files

# def parse_logs(log_files):
#     events = []
    
#     # OS時間の同期
#     time_prefs = {}
#     for node, filepath in log_files.items():
#         try:
#             with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
#                 for line in f:
#                     if 'time_pref_counter=' in line:
#                         m = re.search(r'time_pref_counter=\s*(\d+)', line)
#                         if m: time_prefs[node] = int(m.group(1))
#                         break
#         except Exception: pass
            
#     min_pref = min(time_prefs.values()) if time_prefs else 0
    
#     for node, filepath in log_files.items():
#         node_pref = time_prefs.get(node, min_pref)
#         t_offset = (node_pref - min_pref) / 1e9 
        
#         try:
#             with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
#                 for line in f:
#                     if 'Ev=' not in line or 'Type=' not in line or 'Seq=' not in line: continue
                        
#                     t_match = re.search(r'T=\s*([\d\.]+)', line)
#                     if not t_match: continue
#                     t_sec = float(t_match.group(1))

#                     ev_match = re.search(r'Ev=\s*(\S+)', line)
#                     raw_ev = ev_match.group(1) if ev_match else ''
#                     ev_type = 'Send' if 'Send' in raw_ev else raw_ev

#                     type_match = re.search(r'Type=\s*([A-Z]+)', line)
#                     p_type = type_match.group(1) if type_match else ''
                    
#                     seq_match = re.search(r'Seq=\s*(\d+)', line)
#                     seq = int(seq_match.group(1)) if seq_match else 0

#                     ack_match = re.search(r'ACK=\s*(\d+)', line)
#                     ack = int(ack_match.group(1)) if ack_match else None
                    
#                     events.append({
#                         'node': node,
#                         'time': t_sec + t_offset, 
#                         'event': ev_type,
#                         'type': p_type,
#                         'seq': seq,
#                         'ack': ack
#                     })
#         except Exception as e:
#             print(f"Read Error: {filepath}: {e}")
            
#     events.sort(key=lambda x: x['time'])
#     return events

# def extract_links(events):
#     links = []
    
#     # ★最大の修正点: (Type, Seq, ACK) を完全に一致させるグループを作成
#     groups = defaultdict(lambda: {'sends': [], 'recvs': []})
#     for ev in events:
#         key = (ev['type'], ev['seq'], ev['ack'])
#         if ev['event'] == 'Send': groups[key]['sends'].append(ev)
#         elif ev['event'] == 'Recv': groups[key]['recvs'].append(ev)
            
#     for key, group in groups.items():
#         sends = sorted(group['sends'], key=lambda x: x['time'])
#         recvs = sorted(group['recvs'], key=lambda x: x['time'])
#         used_sends = set() 

#         # 受信(Recv)イベントに対して、同じIDを持つ送信(Send)を「時間」だけで結びつける
#         for r in recvs:
#             r_node = r['node']

#             best_s = None
#             best_s_idx = -1
#             min_diff = float('inf')
            
#             for i, s in enumerate(sends):
#                 if i in used_sends: continue
#                 if s['node'] == r_node: continue # 自分自身への送信は無視
                
#                 diff = r['time'] - s['time']
                
#                 # -2秒（時計ズレ許容）から 120秒（超特大キュー遅延）まで、どんなにズレていても許容する
#                 if -2.0 <= diff <= 120.0:
#                     abs_diff = abs(diff)
#                     if abs_diff < min_diff:
#                         min_diff = abs_diff
#                         best_s = s
#                         best_s_idx = i
            
#             if best_s:
#                 used_sends.add(best_s_idx)
#                 links.append({
#                     'type': r['type'],
#                     'seq': r['seq'],
#                     'sender_node': best_s['node'],
#                     'sender_time': best_s['time'],
#                     'receiver_node': r['node'],
#                     'receiver_time': r['time']
#                 })
                
#     return links

# def plot_sequence(links, start_time, duration):
#     end_time = start_time + duration
    
#     # 論文向けの美しいスタイル（余計な縦線なし）
#     plt.rcParams.update({
#         'font.family': 'sans-serif',
#         'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
#         'font.size': 14,
#         'axes.linewidth': 1.2,
#     })

#     fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    
#     colors = {
#         'VIDEO': '#E66100',    
#         'CONTROL': '#5D3A9B',  
#         'DUMMY': '#999999',    
#     }

#     # ノードの軸
#     for node, x in nodes.items():
#         ax.axvline(x=x, color='#D0D0D0', linestyle='--', linewidth=1.5, zorder=1)
#         ax.text(x, start_time - duration*0.015, node, ha='center', va='bottom', 
#                 fontweight='bold', fontsize=16, 
#                 bbox=dict(facecolor='white', edgecolor='none', alpha=0.9, pad=2))

#     legend_handles = {}

#     for link in links:
#         min_t = min(link['sender_time'], link['receiver_time'])
#         max_t = max(link['sender_time'], link['receiver_time'])
#         if max_t < start_time or min_t > end_time:
#             continue
            
#         x = [nodes[link['sender_node']], nodes[link['receiver_node']]]
#         y = [link['sender_time'], link['receiver_time']]
        
#         p_type = link['type']
#         base_color = colors.get(p_type, '#000000')

#         # 空間通信（斜めの線）のみを描画
#         line, = ax.plot(x, y, color=base_color, linewidth=2.0, alpha=0.9, zorder=3)
#         ax.scatter(x, y, color=base_color, s=50, edgecolor='white', linewidth=1.2, zorder=4)
        
#         label_name = f"{p_type}"
#         if label_name not in legend_handles:
#             legend_handles[label_name] = line

#     ax.set_ylim(end_time, start_time)
#     ax.set_ylabel('Absolute Synchronized Time (s)', fontsize=14, fontweight='bold', labelpad=15)
#     ax.grid(True, axis='y', linestyle=':', color='#E0E0E0', linewidth=1.5, zorder=0)

#     ax.spines['top'].set_visible(False)
#     ax.spines['right'].set_visible(False)
#     ax.spines['bottom'].set_visible(False)
#     ax.xaxis.set_ticks_position('none')
#     ax.set_xticklabels([])

#     if legend_handles:
#         ax.legend(legend_handles.values(), legend_handles.keys(), 
#                   loc='upper right', bbox_to_anchor=(1.25, 1.0),
#                   frameon=True, fancybox=False, edgecolor='#CCCCCC', fontsize=12)

#     ax.set_title('MUCViS Packet Trace (Exact Sequence Matching)', fontsize=18, fontweight='bold', pad=30)
#     plt.tight_layout()
#     plt.show()

# if __name__ == '__main__':
#     if len(sys.argv) < 4:
#         print("Usage: python3 script.py \"pattern\" start duration")
#         sys.exit(1)
    
#     log_files = resolve_log_files(sys.argv[1])
#     events = parse_logs(log_files)
#     links = extract_links(events)
#     plot_sequence(links, float(sys.argv[2]), float(sys.argv[3]))