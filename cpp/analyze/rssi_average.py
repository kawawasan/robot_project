#!/usr/bin/env python3
"""
rssi_average.py
複数のCSVファイルからRSSI平均値を計算して、ノード別にまとめて表示する

使い方：
  python3 rssi_average.py <csv_file1> <csv_file2> ... [--output result.csv]

例：
  python3 rssi_average.py rssi_dense_*.csv rssi_spread_*.csv rssi_camn_1m_*.csv
  python3 rssi_average.py rssi_dense_20260531_151548.csv --output results.csv
"""

import pandas as pd
import sys
import os
from pathlib import Path

# MACアドレス -> ノード名の対応（必要に応じて修正）
MAC_TO_NODE = {
    "34:76:c5:d3:90:cd": "CamN",
    "50:41:b9:65:b8:3d": "RN1",
    "50:41:b9:65:b8:51": "RN2",
}


def calculate_averages(csv_file: str) -> dict:
    """
    単一のCSVファイルからMAC別の平均値を計算する
    
    戻り値: {
        "filename": str,
        "results": {
            "mac1": {"rssi": float, "rssi_avg": float, ...},
            "mac2": {...},
            ...
        }
    }
    """
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error reading {csv_file}: {e}")
        return None

    results = {}
    
    for mac, group in df.groupby("mac"):
        if mac == "NO_STATION":
            continue
        
        stats = {
            "rssi_min": group["rssi_dBm"].min(),
            "rssi_max": group["rssi_dBm"].max(),
            "rssi_mean": group["rssi_dBm"].mean(),
            "rssi_std": group["rssi_dBm"].std(),
            "rssi_avg_mean": group["rssi_avg_dBm"].mean(),
            "tx_Mbps_mean": group["tx_Mbps"].mean(),
            "rx_Mbps_mean": group["rx_Mbps"].mean(),
            "exp_tput_mean": group["exp_tput_Mbps"].mean(),
            "count": len(group),
        }
        
        # ノード名を取得
        node_name = MAC_TO_NODE.get(mac, mac)
        results[node_name] = stats
    
    return {
        "filename": os.path.basename(csv_file),
        "results": results
    }


def format_table(file_results: list) -> str:
    """
    計算結果を見やすいテーブル形式で返す
    """
    output = []
    output.append("=" * 120)
    output.append("RSSI Analysis Results (Stationary Measurement)")
    output.append("=" * 120)
    
    for file_info in file_results:
        filename = file_info["filename"]
        results = file_info["results"]
        
        output.append(f"\n### {filename}")
        output.append("-" * 120)
        output.append(f"{'Node':<8} {'RSSI[dBm]':<20} {'RSSI_avg[dBm]':<18} "
                      f"{'TX[Mbps]':<12} {'RX[Mbps]':<12} {'ExpTP[Mbps]':<14}")
        output.append("-" * 120)
        
        for node in sorted(results.keys()):
            s = results[node]
            rssi_str = f"{s['rssi_mean']:.1f}±{s['rssi_std']:.1f} " \
                       f"({s['rssi_min']:.0f}~{s['rssi_max']:.0f})"
            
            output.append(
                f"{node:<8} {rssi_str:<20} {s['rssi_avg_mean']:>6.1f}         "
                f"{s['tx_Mbps_mean']:>6.2f}       {s['rx_Mbps_mean']:>6.2f}       {s['exp_tput_mean']:>6.2f}"
            )
    
    output.append("=" * 120)
    
    return "\n".join(output)


def save_csv_summary(file_results: list, output_file: str):
    """
    結果をCSVにまとめて保存（スライド用）
    """
    rows = []
    
    for file_info in file_results:
        filename = file_info["filename"]
        results = file_info["results"]
        
        for node in sorted(results.keys()):
            s = results[node]
            rows.append({
                "Condition": filename,
                "Node": node,
                "RSSI_mean[dBm]": round(s["rssi_mean"], 1),
                "RSSI_std[dBm]": round(s["rssi_std"], 2),
                "RSSI_min[dBm]": round(s["rssi_min"], 0),
                "RSSI_max[dBm]": round(s["rssi_max"], 0),
                "TX[Mbps]": round(s["tx_Mbps_mean"], 2),
                "RX[Mbps]": round(s["rx_Mbps_mean"], 2),
                "ExpTP[Mbps]": round(s["exp_tput_mean"], 2),
                "Samples": int(s["count"]),
            })
    
    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_file, index=False)
    print(f"\nSummary saved to: {output_file}")


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 rssi_average.py <csv_file1> [csv_file2 ...] [--output result.csv]")
        print("\n例:")
        print("  python3 rssi_average.py rssi_dense_20260531_151548.csv")
        print("  python3 rssi_average.py rssi_*.csv --output summary.csv")
        sys.exit(1)
    
    # 引数を解析
    csv_files = []
    output_file = None
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        else:
            # ワイルドカード展開
            files = list(Path(".").glob(sys.argv[i]))
            csv_files.extend([str(f) for f in files if f.is_file()])
            i += 1
    
    if not csv_files:
        print("Error: CSV files not found")
        sys.exit(1)
    
    csv_files = sorted(set(csv_files))  # 重複削除とソート
    print(f"Processing {len(csv_files)} file(s):")
    for f in csv_files:
        print(f"  - {f}")
    
    # 各ファイルを処理
    all_results = []
    for csv_file in csv_files:
        result = calculate_averages(csv_file)
        if result:
            all_results.append(result)
    
    # 結果を表示
    print("\n" + format_table(all_results))
    
    # CSVに保存（指定されていれば）
    if output_file:
        save_csv_summary(all_results, output_file)
    else:
        # デフォルトで summary_YYYYMMDD_HHMMSS.csv を作成
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"rssi_summary_{timestamp}.csv"
        save_csv_summary(all_results, output_file)


if __name__ == "__main__":
    main()
