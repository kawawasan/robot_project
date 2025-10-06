#!/usr/bin/env python3
import sys
import os
import subprocess

# --- 設定 ---
# 解析に使うPythonスクリプトのファイル名
ANALYSIS_SCRIPT_NAME = 'analyze_logs.py' 

# ### 変更点: 必須ノードとオプションノードを分ける ###
REQUIRED_NODES = ["CamN", "CN"]
OPTIONAL_NODES = ["RN1", "RN2"]

# --- 関数 (変更なし) ---

def run_command(command, capture_output=False):
    """コマンドを実行し、エラーがあればスクリプトを停止する"""
    print(f"  > Executing: {' '.join(command)}")
    try:
        result = subprocess.run(
            command, 
            check=True, 
            capture_output=capture_output, 
            text=True
        )
        return result
    except FileNotFoundError:
        print(f"エラー: コマンド '{command[0]}' が見つかりません。パスが通っているか確認してください。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"エラー: コマンドの実行に失敗しました (終了コード: {e.returncode})")
        if e.stderr:
            print(f"標準エラー:\n{e.stderr}")
        sys.exit(1)

def sort_log_file(src_path, dst_path):
    """ログファイルをタイムスタンプ(2列目)で数値的にソートする"""
    print(f"  > Sorting: {src_path} -> {dst_path}")
    try:
        with open(src_path, 'r') as f:
            lines = f.readlines()
        
        def sort_key(line):
            try:
                return float(line.split()[1])
            except (IndexError, ValueError):
                return float('inf')

        lines.sort(key=sort_key)
        
        with open(dst_path, 'w') as f:
            f.writelines(lines)
            
    except FileNotFoundError:
        print(f"警告: ソースファイル {src_path} が見つかりませんでした。スキップします。")
        return False
    except Exception as e:
        print(f"エラー: ファイル '{src_path}' のソート中にエラーが発生しました: {e}")
        return False
    return True

# --- メイン処理 ---
def main():
    if len(sys.argv) != 2:
        print(f"使い方: python3 {sys.argv[0]} [log_file_prefix]")
        sys.exit(1)

    log_prefix = sys.argv[1]
    print(f"解析を開始します: {log_prefix}")

    source_dir = os.path.expanduser('~/logs_cpp')
    output_dir = os.path.join("logs_cpp", log_prefix)
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n[ステップ1] 結果保存ディレクトリを作成/確認しました: {output_dir}")

    print("\n[ステップ2] ローカルのログファイルをソートします...")
    
    sorted_log_paths = {}
    
    # ### 変更点: 必須・オプションを分けて処理 ###
    # 必須ノードを処理
    for node in REQUIRED_NODES:
        source_path = os.path.join(source_dir, f"{log_prefix}_{node}.log")
        sorted_path = os.path.join(output_dir, f"{log_prefix}_{node}.log")
        if sort_log_file(source_path, sorted_path):
            sorted_log_paths[node] = sorted_path
    
    # オプションノードを処理（存在すれば）
    for node in OPTIONAL_NODES:
        source_path = os.path.join(source_dir, f"{log_prefix}_{node}.log")
        # ファイルが存在する場合のみソートする
        if os.path.exists(source_path):
            sorted_path = os.path.join(output_dir, f"{log_prefix}_{node}.log")
            if sort_log_file(source_path, sorted_path):
                sorted_log_paths[node] = sorted_path

    # 解析に必要な必須ログが揃っているか確認
    if not all(node in sorted_log_paths for node in REQUIRED_NODES):
        print("\nエラー: 解析に必須のログファイル(CamN, CN)が見つからなかったため、処理を中断します。")
        sys.exit(1)

    print(f"\n[ステップ3] 解析スクリプト ({ANALYSIS_SCRIPT_NAME}) を実行します...")
    analysis_result_path = os.path.join(output_dir, f"{log_prefix}_analyze.txt")
    
    # ### 変更点: 見つかったログファイルだけでコマンドを組み立てる ###
    analysis_command = [
        'python3',
        ANALYSIS_SCRIPT_NAME,
        sorted_log_paths["CamN"],
        sorted_log_paths["CN"]
    ]
    # RNのログが見つかっていれば引数に追加
    if "RN1" in sorted_log_paths:
        analysis_command.append(sorted_log_paths["RN1"])
    if "RN2" in sorted_log_paths:
        analysis_command.append(sorted_log_paths["RN2"])
    
    result = run_command(analysis_command, capture_output=True)
    
    with open(analysis_result_path, 'w') as f:
        f.write(result.stdout)
    print(f"  > 解析結果を {analysis_result_path} に保存しました。")

    print("\n--- 解析結果 ---")
    print(result.stdout.strip())
    print("------------------")
    print("\nすべての処理が完了しました。")

if __name__ == "__main__":
    main()