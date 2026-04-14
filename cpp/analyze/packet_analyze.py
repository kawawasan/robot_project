import sys, os, re
import matplotlib.pyplot as plt
import pandas as pd

def parse_log(file_path):
    fname = os.path.basename(file_path).lower()
    if "cn" in fname or "ctln" in fname: node = "CtlN"
    elif "rn1" in fname: node = "RN1"
    elif "rn2" in fname: node = "RN2"
    elif "camn" in fname: node = "CamN"
    else: return None, [], 0

    data, t_zero_sys = [], 0
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "time_pref_counter=" in line:
                t_zero_sys = int(line.split("time_pref_counter=")[1].strip())
            if "T=" not in line or "Seq=" not in line: continue
            
            # Send_outside_num 等も「送信」として一括取得
            ev_m = re.search(r'Ev=\s*(\w+)', line)
            if not ev_m: continue
            ev = "Send" if "Send" in ev_m.group(1) else "Recv" if "Recv" in ev_m.group(1) else None
            if not ev: continue

            try:
                t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
                ptype = re.search(r'Type=\s*(\w+)', line).group(1)
                seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
                sys_m = re.search(r'SystemTime=\s*(\d+)', line)
                # analyze_loss_delay_cpp.pyの同期スキル: システム時刻を優先
                sys_time = int(sys_m.group(1)) if sys_m else t_zero_sys + int(t * 1e9)
                data.append({'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 'Node': node, 'Event': ev})
            except: continue
    return node, data, t_zero_sys

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
        return
    log_files, start_t, window_size = sys.argv[1:-2], float(sys.argv[-2]), float(sys.argv[-1])
    all_raw, t_zeros = {}, {}
    for f in log_files:
        name, d, tz = parse_log(f)
        if name: all_raw[name], t_zeros[name] = d, tz

    # --- 同期処理: analyze_loss_delay_cpp.py のロジックを忠実に再現 ---
    # 全ノードの時刻をCtlNの起動時(time_pref_counter)を0として統一
    base_ctl = t_zeros.get("CtlN", 0)
    offsets = {node: base_ctl - t_zeros[node] for node in t_zeros}

    processed = []
    for n, entries in all_raw.items():
        for d in entries:
            # 共通時刻 (s) = (SystemTime + オフセット - 基準カウンタ) / 10^9
            adj_t = (d['SystemTime'] + offsets[n] - base_ctl) / 1e9
            if start_t <= adj_t <= start_t + window_size:
                processed.append({**d, 'Time': adj_t})
    
    df = pd.DataFrame(processed)
    if df.empty: return print("No data.")
    
    # 描画設定
    node_order = ["CtlN", "RN1", "RN2", "CamN"]
    node_x = {n: i for i, n in enumerate(node_order)}
    # 物理的なパケットの流れ (トポロジー)
    flows = {
        "CONTROL": ["CtlN", "RN1", "RN2", "CamN"], # 右斜め下へ
        "VIDEO":   ["CamN", "RN2", "RN1", "CtlN"]  # 左斜め下へ
    }
    
    fig, ax = plt.subplots(figsize=(12, 10))
    colors = {"VIDEO": "orange", "CONTROL": "blue"}

    # Seq番号ごとにグループ化して結線
    for (ptype, seq), group in df.groupby(['Type', 'Seq']):
        if ptype not in flows: continue
        path = flows[ptype]
        
        # 1. ノード間の伝送を結ぶ
        for i in range(1, len(path)):
            n_prev, n_curr = path[i-1], path[i]
            # 送信側と受信側のイベントを探す (同じSeqであることは確定済み)
            s_ev = group[(group['Node'] == n_prev) & (group['Event'] == 'Send')]
            r_ev = group[(group['Node'] == n_curr) & (group['Event'] == 'Recv')]
            
            if not s_ev.empty and not r_ev.empty:
                ax.plot([node_x[n_prev], node_x[n_curr]], 
                        [s_ev.iloc[0]['Time'], r_ev.iloc[0]['Time']], 
                        color=colors[ptype], linewidth=1.2, alpha=0.7)

        # 2. ノード内部の処理を結ぶ (Recv -> Send)
        for node in path:
            node_group = group[group['Node'] == node]
            if len(node_group) >= 2:
                ev_recv = node_group[node_group['Event'] == 'Recv']
                ev_send = node_group[node_group['Event'] == 'Send']
                if not ev_recv.empty and not ev_send.empty:
                    ax.plot([node_x[node], node_x[node]], 
                            [ev_recv.iloc[0]['Time'], ev_send.iloc[0]['Time']], 
                            color=colors[ptype], linewidth=0.8, alpha=0.4)

        # ドットを描画
        for _, row in group.iterrows():
            ax.scatter(node_x[row['Node']], row['Time'], color=colors[ptype], s=18, zorder=3)

    ax.set_xticks(range(len(node_order))); ax.set_xticklabels(node_order, fontweight='bold')
    ax.set_ylim(start_t + window_size, start_t) # 時間を上から下へ
    ax.set_ylabel("Time (s)"); ax.set_title(f"Sequence Diagram: {start_t}s - {start_t+window_size}s")
    plt.grid(True, axis='y', alpha=0.3); plt.tight_layout(); plt.show()

if __name__ == "__main__":
    main()

# import sys, os, re
# import matplotlib.pyplot as plt
# import pandas as pd

# def parse_log(file_path):
#     fname = os.path.basename(file_path).lower()
#     if "cn" in fname or "ctln" in fname: node = "CtlN"
#     elif "rn1" in fname: node = "RN1"
#     elif "rn2" in fname: node = "RN2"
#     elif "camn" in fname: node = "CamN"
#     else: return None, [], 0

#     data, t_zero = [], 0
#     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
#         for line in f:
#             if "time_pref_counter=" in line:
#                 t_zero = int(line.split("time_pref_counter=")[1].strip())
#             if "T=" not in line or "Seq=" not in line: continue
#             if "Ev= Send" not in line and "Ev= Recv" not in line: continue
#             try:
#                 t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
#                 ptype = re.search(r'Type=\s*(\w+)', line).group(1)
#                 seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
#                 ev = "Send" if "Ev= Send" in line else "Recv"
#                 dir_m = re.search(r'Direction=\s*(\w+)', line)
#                 direction = dir_m.group(1) if dir_m else 'NONE'
#                 sys_m = re.search(r'SystemTime=\s*(\d+)', line)
#                 sys_time = int(sys_m.group(1)) if sys_m else t_zero + int(t * 1e9)
#                 data.append({
#                     'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 
#                     'Node': node, 'Event': ev, 'Direction': direction
#                 })
#             except: continue
#     return node, data, t_zero

# def main():
#     if len(sys.argv) < 4:
#         print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
#         return
#     log_files, start_t, window_size = sys.argv[1:-2], float(sys.argv[-2]), float(sys.argv[-1])
#     all_raw, counters = {}, {}
#     for f in log_files:
#         name, d, c = parse_log(f)
#         if name: all_raw[name], counters[name] = d, c

#     # --- NTP Sync ---
#     offsets = {"CtlN": 0, "RN1": 0, "RN2": 0, "CamN": 0}
#     def get_st(node, ptype, seq, ev, dr):
#         if node not in all_raw: return None
#         return next((d['SystemTime'] for d in all_raw[node] if d['Type']==ptype and d['Seq']==seq and d['Event']==ev and (dr=='ANY' or d['Direction']==dr)), None)

#     links = [("CtlN", "RN1"), ("RN1", "RN2"), ("RN2", "CamN")]
#     for nl, nr in links:
#         vl, vr = get_st(nl, "VIDEO", 0, "Recv", "ANY"), get_st(nr, "VIDEO", 0, "Send", "ANY")
        
#         # CONTROLパケットはRNで両方向に送信されるため、正しい進行方向(Down)の送信時刻を同期に利用する
#         sl_dir = "Down" if nl in ["RN1", "RN2"] else "ANY"
#         sl = get_st(nl, "CONTROL", 0, "Send", sl_dir)
#         sr = get_st(nr, "CONTROL", 0, "Recv", "ANY")
        
#         if all([vl, vr, sl, sr]):
#             rel = ((vl - vr) - (sr - sl)) // 2
#             offsets[nr] = offsets[nl] + rel
#     # links = [("CtlN", "RN1"), ("RN1", "RN2"), ("RN2", "CamN")]
#     # for nl, nr in links:
#     #     vl, vr = get_st(nl, "VIDEO", 0, "Recv", "ANY"), get_st(nr, "VIDEO", 0, "Send", "ANY")
#     #     sl, sr = get_st(nl, "CONTROL", 0, "Send", "ANY"), get_st(nr, "CONTROL", 0, "Recv", "ANY")
#     #     if all([vl, vr, sl, sr]):
#     #         rel = ((vl - vr) - (sr - sl)) // 2
#     #         offsets[nr] = offsets[nl] + rel

#     # --- Process ---
#     processed = []
#     base_c = counters.get("CtlN", 0)
#     for n, entries in all_raw.items():
#         for d in entries:
#             adj_t = (d['SystemTime'] + offsets[n] - base_c) / 1e9
#             if start_t <= adj_t <= start_t + window_size:
#                 processed.append({**d, 'Time': adj_t})
    
#     df = pd.DataFrame(processed)
#     if df.empty: return print("No data found.")
#     df_clean = df.sort_values('Time').groupby(['Type', 'Seq', 'Node', 'Event', 'Direction']).first().reset_index()

#     # --- Draw ---
#     node_order = ["CtlN", "RN1", "RN2", "CamN"]
#     fig, ax = plt.subplots(figsize=(12, 8))
#     colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}

#     # --- 修正前 ---
#     # candidates = sends[((sends['Node'] != r['Node'])) & (sends['Time'] <= r['Time'] + 0.005)]
#     # if candidates.empty: continue
#     #
#     # best_s = candidates.iloc[abs(candidates['Time'] - r['Time']).argsort()[:1]]

#     # --- 修正後 ---
#     for (ptype, seq), group in df_clean.groupby(['Type', 'Seq']):
#         sends, recvs = group[group['Event']=='Send'], group[group['Event']=='Recv']
#         for _, r in recvs.iterrows():
#             r_idx = node_order.index(r['Node'])
#             # 送信元候補を特定
#             candidates = sends[((sends['Node'] != r['Node'])) & (sends['Time'] <= r['Time'] + 0.005)].copy()
#             if candidates.empty: continue
            
#             # 【追加】CONTROLパケットは両隣に同時送信されるため、物理的な送信方向でフィルタリングする
#             if ptype == "CONTROL":
#                 valid_idx = []
#                 for idx, s in candidates.iterrows():
#                     s_idx = node_order.index(s['Node'])
#                     s_dir = s['Direction']
#                     # 左(Up側)から右(Down側)への送信: 送信元が「Down」へ送っている必要がある
#                     if s_idx < r_idx and (s['Node'] == "CtlN" or s_dir == "Down"):
#                         valid_idx.append(idx)
#                     # 右(Down側)から左(Up側)への送信: 送信元が「Up」へ送っている必要がある
#                     elif s_idx > r_idx and (s['Node'] == "CamN" or s_dir == "Up"):
#                         valid_idx.append(idx)
                
#                 candidates = candidates.loc[valid_idx]
#                 if candidates.empty: continue
            
#             # 因果関係が最も近い送信元を1つ選んで結ぶ
#             best_s = candidates.iloc[abs(candidates['Time'] - r['Time']).argsort()[:1]]
#             for _, s in best_s.iterrows():
#                 ax.plot([node_order.index(s['Node']), r_idx], [s['Time'], r['Time']], 
#                         color=colors.get(ptype, "black"), linewidth=1, alpha=0.7)
#     # for (ptype, seq), group in df_clean.groupby(['Type', 'Seq']):
#     #     sends, recvs = group[group['Event']=='Send'], group[group['Event']=='Recv']
#     #     for _, r in recvs.iterrows():
#     #         r_idx = node_order.index(r['Node'])
#     #         # 送信元候補を特定 (Upなら左、Downなら右)
#     #         candidates = sends[((sends['Node'] != r['Node'])) & (sends['Time'] <= r['Time'] + 0.005)]
#     #         if candidates.empty: continue
            
#     #         # 因果関係が最も近い送信元を1つ選んで結ぶ
#     #         best_s = candidates.iloc[abs(candidates['Time'] - r['Time']).argsort()[:1]]
#     #         for _, s in best_s.iterrows():
#     #             ax.plot([node_order.index(s['Node']), r_idx], [s['Time'], r['Time']], 
#     #                     color=colors.get(ptype, "black"), linewidth=1, alpha=0.7)
        
#     #     for _, row in group.iterrows():
#     #         ax.scatter(node_order.index(row['Node']), row['Time'], color=colors.get(ptype, "black"), s=12, zorder=3)

#     ax.set_xticks(range(len(node_order)))
#     ax.set_xticklabels(node_order, fontweight='bold')
#     ax.set_ylim(start_t + window_size, start_t)
#     ax.grid(True, axis='y', linestyle='--', alpha=0.5)
#     plt.tight_layout()
#     plt.show()

# if __name__ == "__main__":
#     main()
# # 
# # import sys, os, re
# # import matplotlib.pyplot as plt
# # import pandas as pd

# # def parse_log(file_path):
# #     fname = os.path.basename(file_path).lower()
# #     if "cn" in fname or "ctln" in fname: node = "CtlN"
# #     elif "rn1" in fname: node = "RN1"
# #     elif "rn2" in fname: node = "RN2"
# #     elif "camn" in fname: node = "CamN"
# #     else: return None, [], 0

# #     data, t_zero = [], 0
# #     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
# #         for line in f:
# #             if "time_pref_counter=" in line:
# #                 t_zero = int(line.split("time_pref_counter=")[1].strip())
            
# #             if "T=" not in line or "Seq=" not in line: continue
# #             if "Ev= Send" not in line and "Ev= Recv" not in line: continue
                
# #             try:
# #                 t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
# #                 ptype = re.search(r'Type=\s*(\w+)', line).group(1)
# #                 seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
# #                 ev = "Send" if "Ev= Send" in line else "Recv"
                
# #                 dir_m = re.search(r'Direction=\s*(\w+)', line)
# #                 direction = dir_m.group(1) if dir_m else None
                
# #                 sys_m = re.search(r'SystemTime=\s*(\d+)', line)
# #                 sys_time = int(sys_m.group(1)) if sys_m else t_zero + int(t * 1e9)
# #                 data.append({
# #                     'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 
# #                     'Node': node, 'Event': ev, 'Direction': direction
# #                 })
# #             except: continue
# #     return node, data, t_zero

# # def main():
# #     if len(sys.argv) < 4:
# #         print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
# #         return
    
# #     log_files = sys.argv[1:-2]
# #     start_t = float(sys.argv[-2])
# #     window_size = float(sys.argv[-1])
    
# #     all_raw, counters = {}, {}
# #     for f in log_files:
# #         name, d, c = parse_log(f)
# #         if name:
# #             all_raw[name] = d
# #             counters[name] = c

# #     # 特定のリンク間でのイベント時間を取得する関数
# #     def get_link_event(node, ptype, seq, event, direction=None):
# #         if node not in all_raw: return None
# #         for d in all_raw[node]:
# #             if d['Type'] == ptype and d['Seq'] == seq and d['Event'] == event:
# #                 # 終端ノード(CtlN, CamN)はDirectionがない場合があるので許容する
# #                 if direction and node not in ["CtlN", "CamN"]:
# #                     if d['Direction'] == direction:
# #                         return d['SystemTime']
# #                 else:
# #                     return d['SystemTime']
# #         return None

# #     # --- 1. Hop-by-Hop NTP Synchronization ---
# #     # 隣接ノード間でのみ同期計算を行い、内部処理時間(キューイング遅延)の誤差を排除する
# #     print("--- Hop-by-Hop NTP Sync Adjustments (Base: CtlN) ---")
# #     offsets = {"CtlN": 0, "RN1": 0, "RN2": 0, "CamN": 0}
# #     links = [("CtlN", "RN1"), ("RN1", "RN2"), ("RN2", "CamN")]
    
# #     for n_left, n_right in links:
# #         if n_left not in all_raw or n_right not in all_raw: continue
        
# #         v_recv_left  = get_link_event(n_left, "VIDEO", 0, "Recv", "Down")
# #         v_send_right = get_link_event(n_right, "VIDEO", 0, "Send", "Down")
# #         c_send_left  = get_link_event(n_left, "CONTROL", 0, "Send", "Up")
# #         c_recv_right = get_link_event(n_right, "CONTROL", 0, "Recv", "Up")
        
# #         if v_recv_left and v_send_right and c_send_left and c_recv_right:
# #             # 隣り合うノード間だけの相対的なズレを計算
# #             rel_offset = ((v_recv_left - v_send_right) - (c_recv_right - c_send_left)) // 2
# #             offsets[n_right] = offsets[n_left] + rel_offset
# #             print(f"Link {n_left}-{n_right} diff: {rel_offset/1e6:7.2f} ms | Node {n_right:<4} total offset: {offsets[n_right]/1e6:7.2f} ms")
# #         else:
# #             print(f"Link {n_left}-{n_right}: Could not sync (Missing Seq=0 Events)")
# #             offsets[n_right] = offsets[n_left]

# #     # --- 2. Data Processing ---
# #     processed = []
# #     base_counter = counters.get("CtlN", 0)
    
# #     for n, entries in all_raw.items():
# #         for d in entries:
# #             adj_t = (d['SystemTime'] + offsets[n] - base_counter) / 1e9
# #             if start_t <= adj_t <= start_t + window_size:
# #                 processed.append({
# #                     'Node': n, 'Type': d['Type'], 'Seq': d['Seq'], 
# #                     'Time': adj_t, 'Event': d['Event'], 'Direction': d['Direction']
# #                 })
    
# #     df = pd.DataFrame(processed)
# #     if df.empty:
# #         return print("範囲内にパケットが見つかりませんでした。")

# #     df['Direction'] = df['Direction'].fillna('NONE')
# #     df_clean = df.sort_values('Time').groupby(['Type', 'Seq', 'Node', 'Event', 'Direction']).first().reset_index()

# #     node_order = ["CtlN", "RN1", "RN2", "CamN"]
    
# #     # --- 3. Drawing ---
# #     fig, ax = plt.subplots(figsize=(12, 8))
# #     colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}
    
# #     for (ptype, seq), group in df_clean.groupby(['Type', 'Seq']):
# #         sends = group[group['Event'] == 'Send'].copy()
# #         recvs = group[group['Event'] == 'Recv'].copy()
        
# #         # 受信イベントを起点に、直前の「正しい方向からの送信」を逆引きして線を結ぶ
# #         for _, r_row in recvs.iterrows():
# #             r_time = r_row['Time']
# #             r_idx = node_order.index(r_row['Node'])
            
# #             valid_sends = []
# #             for _, s_row in sends.iterrows():
# #                 s_time = s_row['Time']
# #                 s_idx = node_order.index(s_row['Node'])
# #                 s_dir = s_row['Direction']
                
# #                 # 【因果律フィルター】送信が受信より未来にある場合は絶対に結ばない (NTPの微細な揺らぎ1msだけ許容)
# #                 if s_time > r_time + 0.001:
# #                     continue
                
# #                 is_valid = False
# #                 if s_idx < r_idx:  # 左(CtlN側)からの送信
# #                     if s_row['Node'] == "CtlN" or s_dir == "Up": is_valid = True
# #                 elif s_idx > r_idx: # 右(CamN側)からの送信
# #                     if s_row['Node'] == "CamN" or s_dir == "Down": is_valid = True
                        
# #                 if is_valid:
# #                     valid_sends.append(s_row)
            
# #             # 条件に合う送信元のうち、最も時間が近い(直前の)イベントと結ぶ
# #             if valid_sends:
# #                 best_send = sorted(valid_sends, key=lambda x: x['Time'], reverse=True)[0]
# #                 x_vals = [node_order.index(best_send['Node']), r_idx]
# #                 y_vals = [best_send['Time'], r_time]
# #                 ax.plot(x_vals, y_vals, color=colors.get(ptype, "black"), linewidth=1.2, alpha=0.8)
        
# #         for _, row in group.iterrows():
# #             if row['Node'] in node_order:
# #                 ax.scatter(node_order.index(row['Node']), row['Time'], color=colors.get(ptype, "black"), s=15, zorder=3)

# #     ax.set_xticks(range(len(node_order)))
# #     ax.set_xticklabels(node_order, fontsize=12, fontweight='bold')
# #     ax.set_ylabel("Time (s)", fontsize=12)
# #     ax.set_ylim(start_t + window_size, start_t) 
# #     ax.set_title(f"High-Precision Sequence Diagram ({start_t}s - {start_t+window_size}s)", fontsize=14)
# #     ax.grid(True, axis='y', linestyle='--', alpha=0.5)
# #     ax.grid(True, axis='x', linestyle=':', alpha=0.3)
    
# #     plt.tight_layout()
# #     plt.show()

# # if __name__ == "__main__":
# #     main()




# # # import sys, os, re
# # # import matplotlib.pyplot as plt
# # # import pandas as pd

# # # def parse_log(file_path):
# # #     fname = os.path.basename(file_path).lower()
# # #     if "cn" in fname or "ctln" in fname: node = "CtlN"
# # #     elif "rn1" in fname: node = "RN1"
# # #     elif "rn2" in fname: node = "RN2"
# # #     elif "camn" in fname: node = "CamN"
# # #     else: return None, [], 0

# # #     data, t_zero = [], 0
# # #     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
# # #         for line in f:
# # #             if "time_pref_counter=" in line:
# # #                 t_zero = int(line.split("time_pref_counter=")[1].strip())
            
# # #             if "T=" not in line or "Seq=" not in line: continue
# # #             if "Ev= Send" not in line and "Ev= Recv" not in line: continue
                
# # #             try:
# # #                 t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
# # #                 ptype = re.search(r'Type=\s*(\w+)', line).group(1)
# # #                 seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
# # #                 ev = "Send" if "Ev= Send" in line else "Recv"
                
# # #                 # パケットの方向（Up/Down）を取得
# # #                 dir_m = re.search(r'Direction=\s*(\w+)', line)
# # #                 direction = dir_m.group(1) if dir_m else None
                
# # #                 sys_m = re.search(r'SystemTime=\s*(\d+)', line)
# # #                 sys_time = int(sys_m.group(1)) if sys_m else t_zero + int(t * 1e9)
# # #                 data.append({
# # #                     'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 
# # #                     'Node': node, 'Event': ev, 'Direction': direction
# # #                 })
# # #             except: continue
# # #     return node, data, t_zero

# # # def main():
# # #     if len(sys.argv) < 4:
# # #         print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
# # #         return
    
# # #     log_files = sys.argv[1:-2]
# # #     start_t = float(sys.argv[-2])
# # #     window_size = float(sys.argv[-1])
    
# # #     all_raw, counters = {}, {}
# # #     for f in log_files:
# # #         name, d, c = parse_log(f)
# # #         if name:
# # #             all_raw[name] = d
# # #             counters[name] = c

# # #     base = "CtlN"
# # #     offsets = {n: 0 for n in all_raw}

# # #     def get_event_st(node, ptype, seq, event):
# # #         if node not in all_raw: return None
# # #         return next((d['SystemTime'] for d in all_raw[node] if d['Type'] == ptype and d['Seq'] == seq and d['Event'] == event), None)

# # #     # --- NTP Sync ---
# # #     v0_base = get_event_st(base, "VIDEO", 0, "Recv")
# # #     c0_base = get_event_st(base, "CONTROL", 0, "Send")
    
# # #     print(f"--- NTP Sync Adjustments (Base: {base}) ---")
# # #     for n in all_raw:
# # #         if n == base: continue
# # #         vn = get_event_st(n, "VIDEO", 0, "Send")
# # #         cn = get_event_st(n, "CONTROL", 0, "Recv")
# # #         if vn and cn and v0_base and c0_base:
# # #             offsets[n] = ((v0_base - vn) - (cn - c0_base)) // 2
# # #             print(f"Node {n:<4} offset: {offsets[n]:>12} ns ({(offsets[n]/1e6):.2f} ms)")

# # #     # --- Data Processing ---
# # #     processed = []
# # #     base_counter = counters.get(base, 0)
    
# # #     for n, entries in all_raw.items():
# # #         for d in entries:
# # #             adj_t = (d['SystemTime'] + offsets[n] - base_counter) / 1e9
# # #             if start_t <= adj_t <= start_t + window_size:
# # #                 processed.append({
# # #                     'Node': n, 'Type': d['Type'], 'Seq': d['Seq'], 
# # #                     'Time': adj_t, 'Event': d['Event'], 'Direction': d['Direction']
# # #                 })
    
# # #     df = pd.DataFrame(processed)
# # #     if df.empty:
# # #         return print("範囲内にパケットが見つかりませんでした。")

# # #     df['Direction'] = df['Direction'].fillna('NONE')
# # #     # 同一ノードでの同イベント重複排除（最初の一発目だけを拾う）
# # #     df_clean = df.sort_values('Time').groupby(['Type', 'Seq', 'Node', 'Event', 'Direction']).first().reset_index()

# # #     node_order = ["CtlN", "RN1", "RN2", "CamN"]
    
# # #     # --- Drawing ---
# # #     fig, ax = plt.subplots(figsize=(12, 8))
# # #     colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}
    
# # #     for (ptype, seq), group in df_clean.groupby(['Type', 'Seq']):
# # #         sends = group[group['Event'] == 'Send'].copy()
# # #         recvs = group[group['Event'] == 'Recv'].copy()
        
# # #         # 【重要】受信イベント側から、直前の送信イベントを逆引きする（Hop数に依存しない動的ルーティング）
# # #         for _, r_row in recvs.iterrows():
# # #             r_time = r_row['Time']
# # #             r_idx = node_order.index(r_row['Node'])
            
# # #             valid_sends = []
# # #             for _, s_row in sends.iterrows():
# # #                 s_time = s_row['Time']
# # #                 s_idx = node_order.index(s_row['Node'])
# # #                 s_dir = s_row['Direction']
                
# # #                 # 送信時間は受信時間より前（NTPの微細な同期誤差を考慮し +0.005s の猶予）
# # #                 if s_time > r_time + 0.005:
# # #                     continue
                
# # #                 is_valid = False
# # #                 if s_idx < r_idx:  # 送信者が自分より左側（Up方向）
# # #                     if s_row['Node'] == "CtlN" or s_dir == "Up":
# # #                         is_valid = True
# # #                 elif s_idx > r_idx: # 送信者が自分より右側（Down方向）
# # #                     if s_row['Node'] == "CamN" or s_dir == "Down":
# # #                         is_valid = True
                        
# # #                 if is_valid:
# # #                     valid_sends.append(s_row)
            
# # #             # 条件に合う送信元が見つかった場合、最も「時間が近い（新しい）」送信元と結ぶ
# # #             if valid_sends:
# # #                 best_send = sorted(valid_sends, key=lambda x: x['Time'], reverse=True)[0]
                
# # #                 x_vals = [node_order.index(best_send['Node']), r_idx]
# # #                 y_vals = [best_send['Time'], r_time]
# # #                 ax.plot(x_vals, y_vals, color=colors.get(ptype, "black"), linewidth=1.2, alpha=0.8)
        
# # #         # イベントのポイントを描画
# # #         for _, row in group.iterrows():
# # #             if row['Node'] in node_order:
# # #                 ax.scatter(node_order.index(row['Node']), row['Time'], color=colors.get(ptype, "black"), s=15, zorder=3)

# # #     ax.set_xticks(range(len(node_order)))
# # #     ax.set_xticklabels(node_order, fontsize=12, fontweight='bold')
# # #     ax.set_ylabel("Time (s)", fontsize=12)
# # #     ax.set_ylim(start_t + window_size, start_t) 
# # #     ax.set_title(f"High-Precision Sequence Diagram ({start_t}s - {start_t+window_size}s)", fontsize=14)
# # #     ax.grid(True, axis='y', linestyle='--', alpha=0.5)
# # #     ax.grid(True, axis='x', linestyle=':', alpha=0.3)
    
# # #     plt.tight_layout()
# # #     plt.show()

# # # if __name__ == "__main__":
# # #     main()


# # # import sys, os, re
# # # import matplotlib.pyplot as plt
# # # import pandas as pd

# # # def parse_log(file_path):
# # #     fname = os.path.basename(file_path).lower()
# # #     if "cn" in fname or "ctln" in fname: node = "CtlN"
# # #     elif "rn1" in fname: node = "RN1"
# # #     elif "rn2" in fname: node = "RN2"
# # #     elif "camn" in fname: node = "CamN"
# # #     else: return None, [], 0

# # #     data, t_zero = [], 0
# # #     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
# # #         for line in f:
# # #             if "time_pref_counter=" in line:
# # #                 t_zero = int(line.split("time_pref_counter=")[1].strip())
            
# # #             if "T=" not in line or "Seq=" not in line: continue
# # #             if "Ev= Send" not in line and "Ev= Recv" not in line: continue
                
# # #             try:
# # #                 t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
# # #                 ptype = re.search(r'Type=\s*(\w+)', line).group(1)
# # #                 seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
# # #                 ev = "Send" if "Ev= Send" in line else "Recv"
                
# # #                 sys_m = re.search(r'SystemTime=\s*(\d+)', line)
# # #                 sys_time = int(sys_m.group(1)) if sys_m else t_zero + int(t * 1e9)
# # #                 data.append({
# # #                     'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 
# # #                     'Node': node, 'Event': ev
# # #                 })
# # #             except: continue
# # #     return node, data, t_zero

# # # def main():
# # #     if len(sys.argv) < 4:
# # #         print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
# # #         return
    
# # #     log_files = sys.argv[1:-2]
# # #     start_t = float(sys.argv[-2])
# # #     window_size = float(sys.argv[-1])
    
# # #     all_raw, counters = {}, {}
# # #     for f in log_files:
# # #         name, d, c = parse_log(f)
# # #         if name:
# # #             all_raw[name] = d
# # #             counters[name] = c

# # #     base = "CtlN"
# # #     offsets = {n: 0 for n in all_raw}

# # #     # イベントの種類（Send/Recv）を厳密に指定して時刻を取得する関数
# # #     def get_event_st(node, ptype, seq, event):
# # #         if node not in all_raw: return None
# # #         return next((d['SystemTime'] for d in all_raw[node] if d['Type'] == ptype and d['Seq'] == seq and d['Event'] == event), None)

# # #     # NTP-style Synchronization
# # #     # CtlNがVIDEOを受け取った時間と、CONTROLを送った時間を基準にする
# # #     v0_base = get_event_st(base, "VIDEO", 0, "Recv")
# # #     c0_base = get_event_st(base, "CONTROL", 0, "Send")
    
# # #     print(f"--- NTP Sync Adjustments (Base: {base}) ---")
# # #     for n in all_raw:
# # #         if n == base: continue
        
# # #         # 各ノードがVIDEOを「送信」した時間と、CONTROLを「受信」した時間
# # #         vn = get_event_st(n, "VIDEO", 0, "Send")
# # #         cn = get_event_st(n, "CONTROL", 0, "Recv")
        
# # #         if vn and cn and v0_base and c0_base:
# # #             offsets[n] = ((v0_base - vn) - (cn - c0_base)) // 2
# # #             print(f"Node {n:<4} offset: {offsets[n]:>12} ns ({(offsets[n]/1e6):.2f} ms)")
# # #         else:
# # #             print(f"Node {n:<4} offset: Could not sync")

# # #     # Data Processing
# # #     processed = []
# # #     base_counter = counters.get(base, 0)
    
# # #     for n, entries in all_raw.items():
# # #         for d in entries:
# # #             adj_t = (d['SystemTime'] + offsets[n] - base_counter) / 1e9
# # #             if start_t <= adj_t <= start_t + window_size:
# # #                 processed.append({
# # #                     'Node': n, 
# # #                     'Type': d['Type'], 
# # #                     'Seq': d['Seq'], 
# # #                     'Time': adj_t,
# # #                     'Event': d['Event']
# # #                 })
    
# # #     df = pd.DataFrame(processed)
# # #     if df.empty:
# # #         print("範囲内にパケットが見つかりませんでした。")
# # #         return

# # #     node_order = ["CtlN", "RN1", "RN2", "CamN"]
    
# # #     # Drawing
# # #     fig, ax = plt.subplots(figsize=(12, 8))
# # #     colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}
    
# # #     for (ptype, seq), group in df.groupby(['Type', 'Seq']):
# # #         # イベントを発生時間順に正確に並び替える
# # #         group = group.sort_values(by='Time')
        
# # #         if len(group) < 2: continue
            
# # #         x_vals, y_vals = [], []
# # #         for _, row in group.iterrows():
# # #             if row['Node'] in node_order:
# # #                 x_vals.append(node_order.index(row['Node']))
# # #                 y_vals.append(row['Time'])
        
# # #         ax.plot(x_vals, y_vals, color=colors.get(ptype, "black"), linewidth=1.0, alpha=0.8)
# # #         ax.scatter(x_vals, y_vals, color=colors.get(ptype, "black"), s=15, zorder=3)

# # #     ax.set_xticks(range(len(node_order)))
# # #     ax.set_xticklabels(node_order, fontsize=12, fontweight='bold')
# # #     ax.set_ylabel("Time (s)", fontsize=12)
# # #     ax.set_ylim(start_t + window_size, start_t) 
# # #     ax.set_title(f"High-Precision Sequence Diagram ({start_t}s - {start_t+window_size}s)", fontsize=14)
# # #     ax.grid(True, axis='y', linestyle='--', alpha=0.5)
# # #     ax.grid(True, axis='x', linestyle=':', alpha=0.3)
    
# # #     plt.tight_layout()
# # #     plt.show()

# # # if __name__ == "__main__":
# # #     main()




# # # # import sys, os, re, glob
# # # # import matplotlib.pyplot as plt
# # # # import pandas as pd

# # # # def parse_log(file_path):
# # # #     fname = os.path.basename(file_path).lower()
# # # #     if "cn" in fname: node = "CtlN"
# # # #     elif "rn1" in fname: node = "RN1"
# # # #     elif "rn2" in fname: node = "RN2"
# # # #     elif "camn" in fname: node = "CamN"
# # # #     else: return None, [], 0

# # # #     data, t_zero = [], 0
# # # #     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
# # # #         for line in f:
# # # #             if "time_pref_counter=" in line:
# # # #                 t_zero = int(line.split("time_pref_counter=")[1].strip())
# # # #             # Send/Recvイベントのみを対象とし、内部処理(Generate等)は除外
# # # #             if "T=" not in line or "Seq=" not in line or not any(x in line for x in ["Ev= Send", "Ev= Recv"]):
# # # #                 continue
# # # #             try:
# # # #                 t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
# # # #                 ptype = re.search(r'Type=\s*(\w+)', line).group(1)
# # # #                 seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
# # # #                 sys_m = re.search(r'SystemTime=\s*(\d+)', line)
# # # #                 sys_time = int(sys_m.group(1)) if sys_m else t_zero + int(t * 1e9)
# # # #                 data.append({'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 'Node': node})
# # # #             except: continue
# # # #     return node, data, t_zero

# # # # def main():
# # # #     if len(sys.argv) < 4:
# # # #         print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
# # # #         return
    
# # # #     log_files, start_t, window_size = sys.argv[1:-2], float(sys.argv[-2]), float(sys.argv[-1])
# # # #     all_raw, counters = {}, {}
# # # #     for f in log_files:
# # # #         name, d, c = parse_log(f)
# # # #         if name: all_raw[name], counters[name] = d, c

# # # #     # --- NTP-style Synchronization ---
# # # #     # 往復パケット(Seq 0)を用いて各ノードの時計のズレをナノ秒単位で補正
# # # #     def get_first_st(node, ptype, seq):
# # # #         return next((d['SystemTime'] for d in all_raw[node] if d['Type'] == ptype and d['Seq'] == seq), None)
    
# # # #     base = "CtlN"
# # # #     offsets = {n: 0 for n in all_raw}
# # # #     v0_base, c0_base = get_first_st(base, "VIDEO", 0), get_first_st(base, "CONTROL", 0)
    
# # # #     for n in all_raw:
# # # #         if n == base: continue
# # # #         vn, cn = get_first_st(n, "VIDEO", 0), get_first_st(n, "CONTROL", 0)
# # # #         if vn and cn and v0_base and c0_base:
# # # #             # 伝搬遅延を相殺して時計の差分(Offset)を算出
# # # #             offsets[n] = ((vn - v0_base) - (c0_base - cn)) // 2

# # # #     # --- Data Processing ---
# # # #     node_order = ["CtlN", "RN1", "RN2", "CamN"]
# # # #     processed = []
# # # #     base_counter = counters.get("CamN", 0)
    
# # # #     for n, entries in all_raw.items():
# # # #         for d in entries:
# # # #             adj_t = (d['SystemTime'] - offsets[n] - base_counter) / 1e9
# # # #             if start_t <= adj_t <= start_t + window_size:
# # # #                 processed.append({'Node': n, 'Type': d['Type'], 'Seq': d['Seq'], 'Time': adj_t})
    
# # # #     df = pd.DataFrame(processed)
# # # #     if df.empty: return print("範囲内にパケットが見つかりませんでした。")

# # # #     # パケットごとに、各ノードでの「最初のイベント」のみに絞り込む（描画をクリーンにする）
# # # #     df = df.sort_values('Time').groupby(['Type', 'Seq', 'Node']).first().reset_index()

# # # #     # --- Drawing ---
# # # #     fig, ax = plt.subplots(figsize=(12, 8))
# # # #     colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}
    
# # # #     for (ptype, seq), group in df.groupby(['Type', 'Seq']):
# # # #         # X軸(node_order)に従ってソートして線を結ぶ
# # # #         group = group.sort_values(by='Node', key=lambda x: x.map({n: i for i, n in enumerate(node_order)}))
# # # #         if len(group) < 2: continue
# # # #         x = [node_order.index(n) for n in group['Node']]
# # # #         ax.plot(x, group['Time'], color=colors.get(ptype, "black"), linewidth=0.7, alpha=0.8)
# # # #         ax.scatter(x, group['Time'], color=colors.get(ptype, "black"), s=15, zorder=3)

# # # #     ax.set_xticks(range(len(node_order)))
# # # #     ax.set_xticklabels(node_order, fontsize=12, fontweight='bold')
# # # #     ax.set_ylabel("Time (s)", fontsize=12)
# # # #     ax.set_ylim(start_t + window_size, start_t) # 時間を上から下へ
# # # #     ax.set_title(f"High-Precision Sequence Diagram ({start_t}s - {start_t+window_size}s)", fontsize=14)
# # # #     ax.grid(True, axis='y', linestyle='--', alpha=0.5)
# # # #     plt.tight_layout()
# # # #     plt.show()

# # # # if __name__ == "__main__":
# # # #     main()
# # # # # import sys
# # # # # import os
# # # # # import re
# # # # # import matplotlib.pyplot as plt
# # # # # import glob

# # # # # def parse_log(file_path):
# # # # #     # ファイル名からノード名を判定 (大文字小文字を区別しない)
# # # # #     fname = os.path.basename(file_path).lower()
# # # # #     node_name = ""
# # # # #     if "_cn" in fname: node_name = "CtlN"
# # # # #     elif "_rn1" in fname: node_name = "RN1"
# # # # #     elif "_rn2" in fname: node_name = "RN2"
# # # # #     elif "_camn" in fname: node_name = "CamN"

# # # # #     data = []
# # # # #     t_zero_sys_time = 0
    
# # # # #     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
# # # # #         for line in f:
# # # # #             if "time_pref_counter=" in line:
# # # # #                 t_zero_sys_time = int(line.split("time_pref_counter=")[1].strip())
            
# # # # #             if "T=" not in line or "Seq=" not in line:
# # # # #                 continue
            
# # # # #             try:
# # # # #                 t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
# # # # #                 p_type = re.search(r'Type=\s*(\w+)', line).group(1)
# # # # #                 seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
                
# # # # #                 sys_time_match = re.search(r'SystemTime=\s*(\d+)', line)
# # # # #                 if sys_time_match:
# # # # #                     sys_time = int(sys_time_match.group(1))
# # # # #                 else:
# # # # #                     # SystemTimeがない場合はTから計算（ナノ秒換算）
# # # # #                     sys_time = t_zero_sys_time + int(t * 1e9)
                
# # # # #                 data.append({
# # # # #                     'T': t, 'Type': p_type, 'Seq': seq, 
# # # # #                     'SystemTime': sys_time, 'Node': node_name
# # # # #                 })
# # # # #             except (AttributeError, ValueError):
# # # # #                 continue
# # # # #     return node_name, data

# # # # # def main():
# # # # #     if len(sys.argv) < 4:
# # # # #         print("Usage: python3 00.py [log_files...] start_t window_size")
# # # # #         return

# # # # #     # 後ろから2つを数値として取得
# # # # #     try:
# # # # #         window_size = float(sys.argv[-1])
# # # # #         start_t = float(sys.argv[-2])
# # # # #         log_files = sys.argv[1:-2]
# # # # #     except ValueError:
# # # # #         print("Error: 開始時刻とウィンドウサイズは数値で指定してください。")
# # # # #         return

# # # # #     # ユーザーの指定順序（PDFに合わせるなら ["CtlN", "RN2", "RN1", "CamN"] に変更してください）
# # # # #     node_order = ["CtlN", "RN1", "RN2", "CamN"]
# # # # #     all_data = {}
    
# # # # #     # 全ログ読み込み
# # # # #     expanded_files = []
# # # # #     for f in log_files:
# # # # #         expanded_files.extend(glob.glob(f))
        
# # # # #     for fpath in expanded_files:
# # # # #         name, data = parse_log(fpath)
# # # # #         if name: all_data[name] = data

# # # # #     if not all_data:
# # # # #         print("Error: 有効なログファイルが見つかりませんでした。")
# # # # #         return

# # # # #     # 1. 時刻同期 (VIDEO Seq 0 を基準にオフセット計算)
# # # # #     # 実環境データに合わせて、全ノードで確認できた最初のVIDEOパケットを探す
# # # # #     offsets = {node: 0 for node in node_order}
# # # # #     ref_node = "CamN"
# # # # #     if ref_node in all_data:
# # # # #         try:
# # # # #             # Seq 0 の VIDEO 送信時刻を基準にする
# # # # #             base_event = next(d for d in all_data[ref_node] if d['Seq'] == 0 and d['Type'] == "VIDEO")
# # # # #             base_sys_time = base_event['SystemTime']
            
# # # # #             for node in all_data:
# # # # #                 try:
# # # # #                     node_event = next(d for d in all_data[node] if d['Seq'] == 0 and d['Type'] == "VIDEO")
# # # # #                     offsets[node] = node_event['SystemTime'] - base_sys_time
# # # # #                 except StopIteration:
# # # # #                     pass 
# # # # #         except StopIteration:
# # # # #             base_sys_time = min(d['SystemTime'] for entries in all_data.values() for d in entries)
# # # # #     else:
# # # # #         base_sys_time = min(d['SystemTime'] for entries in all_data.values() for d in entries)

# # # # #     # 2. データの整理
# # # # #     start_sys_time = base_sys_time + int(start_t * 1e9)
# # # # #     end_sys_time = start_sys_time + int(window_size * 1e9)
    
# # # # #     packets = {} 
# # # # #     for node, entries in all_data.items():
# # # # #         for d in entries:
# # # # #             adj_time = d['SystemTime'] - offsets[node]
# # # # #             if start_sys_time <= adj_time <= end_sys_time:
# # # # #                 key = (d['Type'], d['Seq'])
# # # # #                 if key not in packets: packets[key] = {}
# # # # #                 # 各ノードの最初の通過時刻を記録
# # # # #                 if node not in packets[key]:
# # # # #                     packets[key][node] = (adj_time - start_sys_time) / 1e9

# # # # #     # 3. 描画
# # # # #     fig, ax = plt.subplots(figsize=(10, 7))
# # # # #     colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}
    
# # # # #     for (p_type, seq), nodes in packets.items():
# # # # #         active_nodes = [n for n in node_order if n in nodes]
# # # # #         active_nodes.sort(key=lambda x: node_order.index(x))
        
# # # # #         if len(active_nodes) < 2: continue
        
# # # # #         x_coords = [node_order.index(n) for n in active_nodes]
# # # # #         y_coords = [nodes[n] for n in active_nodes]
        
# # # # #         ax.plot(x_coords, y_coords, color=colors.get(p_type, "black"), 
# # # # #                 linewidth=0.5, alpha=0.7, zorder=1)
# # # # #         ax.scatter(x_coords, y_coords, color=colors.get(p_type, "black"), 
# # # # #                    s=10, zorder=2)

# # # # #     ax.set_xticks(range(len(node_order)))
# # # # #     ax.set_xticklabels(node_order)
# # # # #     ax.set_ylabel("Time (s) from window start")
# # # # #     ax.set_xlabel("Nodes")
# # # # #     ax.invert_yaxis()
# # # # #     ax.set_title(f"Sequence Diagram: {start_t}s to {start_t + window_size}s")
# # # # #     plt.grid(True, axis='y', linestyle=':', alpha=0.6)
# # # # #     plt.tight_layout()
# # # # #     plt.show()

# # # # # if __name__ == "__main__":
# # # # #     main()