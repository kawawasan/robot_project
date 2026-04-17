// 制御ノード  同軸環境用
// 映像をtsファイルとして保存する
// 映像をストリーミング再生する．名前付きパイプを使用
// 制御情報を入力可能に

#include <iostream>
#include <thread>  // コンパイル時には-pthread
#include <algorithm>
#include <queue>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sstream>
#include <filesystem>
#include <csignal>
#include <sys/stat.h>
#include <atomic>
#include <cmath>
#include <chrono>
#include <pthread.h>
#include <time.h>


#include "../../include/header/bytequeue.hpp"  // 自作モジュール
#include "../../include/header/log.hpp"  // 自作モジュール
#include "../../include/header/packet.hpp"  // 自作モジュール

using std::cout ; // std::cout を cout と書ける
using std::endl ; // std::endl を endl と書ける
using hr_clock = std::chrono::high_resolution_clock;
using system_clock = std::chrono::system_clock;

// パケットタイプ 映像: 0, 制御情報: 1, ダミー: 2 31と30bit目
#define TYPE_VIDEO (uint32_t)0  // (00 << 30)
#define TYPE_CONTROL (uint32_t)(0b01 << 30)
#define TYPE_DUMMY (uint32_t)(0b10 << 30)
#define BUFFER_MAX 1500
#define MAX_VIDEO_SIZE 1316  // 映像データサイズ 最大1464byte(1500-UDPヘッダ-自作ヘッダ(8byte))．以前は1456，tsファイルは188byteのため，1316
#define CONTROL_SEQ_MAX (1 << 30)  // 30bitの最大値
#define VIDEO_SEQ_MAX 0xffffffff  // 32bitの最大値
#define DUMMY_SEQ_MAX 3  // ダミーパケット送信回数上限
#define FILE_NAME_PREFIX "videos/IPT_"  // 映像ファイル名プレフィックス

// グローバル変数
uint32_t g_control_seq = 0;  // 制御情報のシーケンス番号 0~2^30
uint32_t g_video_seq = 0;  // 映像シーケンス番号 0~2^32
uint32_t g_ack = -1;  // ack 0~2^30
ByteQueue g_video_bytequeue;  // 映像データキュー
ByteQueue g_command_bytequeue;  // 制御情報キュー
std::queue<std::vector<uint8_t>> g_video_queue;  // 映像データパケットキュー
std::queue<std::string> g_command_queue;  // 制御コマンドキュー
// std::mutex g_lock;　// 削除　20260416_河村
std::mutex g_command_mutex; //追加　河村　制御キュー
std::string g_video_file_name;  // 映像ファイル名

// int g_write_size = 0;  // 映像データ書き込みサイズ
// int g_recv_size = 0;  // 映像データ受信サイズ

// const double generate_time_all = 600.0;  // コマンド生成時間 [s]
bool generate_input_end = false;  // コマンド生成終了フラグ
int generate_num = 0;  // 生成したコマンド数
std::atomic<int> g_send_num;  // 送信先のノード番号

// 関数の宣言
void generate_command_from_input(Log& log, std::chrono::high_resolution_clock::time_point start_time, const int node_num, const double communication_range, const double Vehicle_body_length, std::vector<std::vector<std::string>>& routing_table);

void generate_command_fixed_interval(double generate_time_all, Log& log, std::chrono::high_resolution_clock::time_point start_time);
// void ffmpeg_ts_mp4();


void signal_handler(int sig) {
    std::cout << "\n終了処理中..." << std::endl;

    // 映像ファイルをmp4に変換
    // ffmpeg_ts_mp4();

    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    std::cout << "Program end" << std::endl;

    exit(0);
}

// MUCViS_CNクラス
class Mucvis_cn {
    hr_clock::time_point hr_start_time;  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()
    int send_socket = socket(AF_INET, SOCK_DGRAM, 0);
    int recv_socket = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in my_addr;
    struct sockaddr_in up_addr;
    Log *log;
    double ipt_interval;
    int my_node_num;
    std::vector<std::vector<std::string>> routing_table;
    int send_node_before;  // 直前に送信したノード

    std::string video_file_name;
    std::ofstream video_file;
    // 受け取った映像をストリーミング再生するための名前付きパイプを定義
    // std::ofstream pipe_file; 試しに変更　河村
    // ⭕️ 修正後
    std::fstream pipe_file;

    std::vector<uint8_t> video_data;
    std::size_t video_data_size;
    char buf[BUFFER_MAX];
    std::vector<uint8_t> send_payload;
    std::vector<uint8_t> recv_payload;
    // --- ここから追記 (ミューテックスの宣言) ---河村
    std::mutex m_command_mutex;
    std::mutex m_video_mutex;
    std::mutex m_ack_mutex;
    // --- ここまで ---

public:
    Mucvis_cn(std::string my_address, int my_port, std::string up_address, int up_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time, std::string video_file_name, int my_node_num, std::vector<std::vector<std::string>>& routing_table) {
        my_addr.sin_family = AF_INET;
        my_addr.sin_addr.s_addr = inet_addr(my_address.c_str());
        my_addr.sin_port = htons(my_port);
        up_addr.sin_family = AF_INET;
        up_addr.sin_addr.s_addr = inet_addr(up_address.c_str());
        up_addr.sin_port = htons(up_port);
        this->log = &log;
        this->ipt_interval = ipt_interval;
        this->hr_start_time = hr_start_time;
        this->video_file_name = video_file_name;
        this->my_node_num = my_node_num;
        this->routing_table = routing_table;
        this->send_node_before = g_send_num.load();

        video_data.reserve(MAX_VIDEO_SIZE);
        send_payload.reserve(MAX_VIDEO_SIZE + 8);  // ヘッダ8byte + 映像データ最大1464byte
        recv_payload.reserve(MAX_VIDEO_SIZE + 8);  // ヘッダ8byte + 映像データ最大1464byte

        // 映像ファイルを開く
        std::string file_name_pass = FILE_NAME_PREFIX + video_file_name + "/" + video_file_name + ".ts";
        video_file.open(file_name_pass, std::ios::binary);
        if (!video_file) {
            std::cerr << "Failed to open video file: " << file_name_pass << std::endl;
            exit(EXIT_FAILURE);
        }

        // 名前付きパイプを作成
        // if (!std::filesystem::exists("/tmp/ts_pipe")) {
        //     if (mkfifo("/tmp/ts_pipe", 0666) == -1) {
        //         std::cerr << "Failed to create named pipe: /tmp/ts_pipe" << std::endl;
        //         exit(EXIT_FAILURE);
        //     }
        // }
        // ⭕️ 修正後（カレントディレクトリに作成）20260416 河村
        if (!std::filesystem::exists("ts_pipe")) {
            if (mkfifo("ts_pipe", 0666) == -1) {
                std::cerr << "Failed to create named pipe: ts_pipe" << std::endl;
                exit(EXIT_FAILURE);
            }
        }

        cout << "名前付きパイプ生成: ./ts_pipe" << endl;
        // cout << "名前付きパイプ生成: /tmp/ts_pipe" << endl;
        // ⭕️ 修正後（inとoutの両方をつけて開く！）
        pipe_file.open("ts_pipe", std::ios::out | std::ios::binary);
        if (!pipe_file) {
            std::cerr << "Failed to open named pipe: ts_pipe" << std::endl;
            exit(EXIT_FAILURE);
        
        // pipe_file.open("/tmp/ts_pipe", std::ios::binary);
        // if (!pipe_file) {
        //     std::cerr << "Failed to open named pipe: /tmp/ts_pipe" << std::endl;
        //     exit(EXIT_FAILURE);
        } else {
            std::cout << "Named pipe opened successfully: /tmp/ts_pipe" << std::endl;
        }

        // 受信ソケットのバッファサイズを設定
        int recv_buffer_size = 1024 * 1024 * 10;  // 1MB
        if (setsockopt(recv_socket, SOL_SOCKET, SO_RCVBUF, &recv_buffer_size, sizeof(recv_buffer_size)) == -1) {
            perror("setsockopt failed");
        }
    }

    // ⭕️ 新設：CNの裏方書き込みスレッド
    void video_writer_thread() {
        while (true) {
            std::vector<uint8_t> data;
            {
                std::lock_guard<std::mutex> lock(m_video_mutex);
                if (!g_video_queue.empty()) {
                    data = std::move(g_video_queue.front());
                    g_video_queue.pop();
                }
            }
            if (!data.empty()) {
                pipe_file.write(reinterpret_cast<const char*>(data.data()), data.size());
                pipe_file.flush();
                video_file.write(reinterpret_cast<const char*>(data.data()), data.size());
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
    }

    // グローバルまたはクラスメンバとしてロガーのインスタンスを渡す想定
    // 20260416_河村　追加
    // ★ どんな時間の型(TimePoint)が来ても自動で対応するテンプレート関数
    template <typename TimePoint>
    void precise_sleep_until(TimePoint target_time) {
        using namespace std::chrono;
        
        // target_time をそのままエポックからのナノ秒に変換
        auto epoch_ns = duration_cast<nanoseconds>(target_time.time_since_epoch()).count();

        struct timespec ts;
        ts.tv_sec = epoch_ns / 1000000000LL;
        ts.tv_nsec = epoch_ns % 1000000000LL;

        // 第2引数に TIMER_ABSTIME を指定し、絶対時刻でOSに厳密な休眠を委ねる
        while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, nullptr) == EINTR);
    }
        //20260416_河村
        void set_realtime_priority(int priority) {
            struct sched_param param;
            param.sched_priority = priority; 
            if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) != 0) {
                std::cerr << "Failed to set SCHED_FIFO (Priority: " << priority << ")" << std::endl;
            }
        }

        
    // パケット生成
    Packet make_packet() {
        uint32_t packet_type = (0b11 << 30);  // UNKNOWN
        // g_lock.lock(); 河村
        int g_command_queue_size;
        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            g_command_queue_size = g_command_queue.size();
        }
            // g_lock.unlock();

        if (g_command_queue_size != 0) {
            packet_type = TYPE_CONTROL;
        }

        if (packet_type == TYPE_CONTROL) {
            // g_lock.lock(); 河村
            uint32_t sqe;
            std::string control_command;
            {
                std::lock_guard<std::mutex> lock(g_command_mutex);
                control_command = g_command_queue.front();
                g_command_queue.pop();
                sqe = g_control_seq;
                g_control_seq++;
            // g_lock.unlock();
            }

            // パケット生成
            Packet packet(packet_type, sqe, control_command);

            return packet;
        }
        Packet packet(packet_type, 0);  // UNKNOWN packet
        return packet;
    }

    void send_packet() {
        // パケット生成
        Packet packet = make_packet();

        std::string packet_type = packet.get_type();
        if (packet_type == "UNKNOWN") {
            return;
        }

        // std::vector<uint8_t> send_payload = packet.get_payload();
        // send_payload.clear();
        // send_payload = packet.get_payload();
        send_payload = std::move(packet.get_payload());  // ムーブで効率的に転送

        // 上りへ送信
        sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

        system_clock::time_point system_send_time = system_clock::now();
        hr_clock::time_point send_time = hr_clock::now();
        std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

        // g_lock.lock();
        uint32_t ack;
        {
            std::lock_guard<std::mutex> lock(m_video_mutex);
            ack = g_ack;

            // ログに書き込む
            log->write_camn_cn(duration, "Send", packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
        // g_lock.unlock();
        }

        
        // 中継外の送信先を決める
        int send_node = g_send_num.load();
        if (send_node_before > send_node) {
            send_node_before = send_node;
        }
        // 中継外のノードに制御情報を送信する
        for (int i = send_node_before; i < my_node_num - 1; i++) {
            up_addr.sin_addr.s_addr = inet_addr(routing_table[i][1].c_str());  // 送信先アドレスを更新
            
            sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

            // ログに書き込む
            std::string event = "Send_outside_num_" + std::to_string(i + 1);
            log->write_camn_cn(duration, event, packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
            send_node_before = send_node;
        }

        up_addr.sin_addr.s_addr = inet_addr(routing_table[send_node - 1][1].c_str());  // 送信先アドレスを更新
        // up_addr.sin_port = htons(std::stoi(routing_table[send_node - 1][1].c_str()));  // ローカルのため，ポート番号を変更
    }

    void receive_packet() {
        // char buf[BUFFER_MAX];
        buf[0] = '\0';  // バッファを初期化
        uint32_t seq = 0;
        uint32_t ack = 0;
        uint32_t pre_ack;
        uint32_t pre_video_seq;

        int recv_size = recv(recv_socket, buf, sizeof(buf), 0);

        system_clock::time_point system_recv_time = system_clock::now();
        hr_clock::time_point recv_time = hr_clock::now();
        // recv_payload(buf, buf + recv_size);
        // recv_payload.clear();
        // recv_payload = std::vector<uint8_t>(buf, buf + recv_size);
        recv_payload.assign(buf, buf + recv_size);
        // std::vector<uint8_t> payload(buf, buf + recv_size);
        Packet packet(recv_payload);
        std::string packet_type = packet.get_type();

        if (packet_type == "VIDEO") {
            ack = packet.get_ack();
            seq = packet.get_videoSeq();

            // g_lock.lock();河村
            {
            std::lock_guard<std::mutex> lock(m_video_mutex);
                g_video_queue.push(packet.get_videoData());
                pre_ack = g_ack;
                g_ack = ack;

                pre_video_seq = g_video_seq;
                g_video_seq = seq;
            // g_lock.unlock();
            }

            // video_seqが連番でないときは書き込まず終了
            if (seq != pre_video_seq + 1 and seq != 0) {
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Video_seq_lost"
                    << " Pre_Seq= " << pre_video_seq 
                    << " Seq= " << seq;
                log->write(ss.str());
                // 連番でない場合は異常終了
                // exit(EXIT_FAILURE);
            }

            // パケットから映像データをサイズを取得
            // std::vector<uint8_t> video_data = packet.get_videoData();
            // std::size_t video_data_size = video_data.size();
            // video_data.clear();  // 映像データをクリア
            // video_data = packet.get_videoData();
            video_data = std::move(packet.get_videoData());  // 映像データをムーブ
            video_data_size = video_data.size();
            // cout << "映像データ受信サイズ: " << video_data_size << " byte" << endl;

            // 映像データを名前付きパイプに渡す．ストリーミング再生用
            // pipe_file.write(reinterpret_cast<const char*>(packet.get_videoData().data()), packet.get_videoData().size());
            pipe_file.write(reinterpret_cast<const char*>(video_data.data()), video_data_size);
            // pipe_file.flush();  
            // 映像データをファイルに書き込む
            // video_file.write(reinterpret_cast<const char*>(packet.get_videoData().data()), packet.get_videoData().size());
            video_file.write(reinterpret_cast<const char*>(video_data.data()), video_data_size);
            // video_file.flush();
            // cout << "映像データ書き込みサイズ: " << packet.get_videoData().size() << " byte" << endl;
            // g_write_size += packet.get_videoData().size();
            // g_recv_size += recv_size;
            
            // コマンドパケットのロストをackで検知
            if (ack > pre_ack + 1) {
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Command_lost"
                    << " Pre_ACK= " << pre_ack 
                    << " ACK= " << ack;
                log->write(ss.str());
            }
        } else if (packet_type == "DUMMY") {
            ack = packet.get_ack();
            
            // g_lock.lock();
            {
                std::lock_guard<std::mutex> lock(m_video_mutex);
                pre_ack = g_ack;
                g_ack = ack;
            // g_lock.unlock();
            }
            
            // コマンドパケットのロストをackで検知
            if (ack > pre_ack + 1) {
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Command_lost"
                    << " Pre_ACK= " << pre_ack 
                    << " ACK= " << ack;
                log->write(ss.str());
            }

            // 送信間隔 I / 3 待機
            // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        } else {  // CONTROL
            ack = packet.get_ack();
            std::string command = packet.get_command();

            // 送信間隔 I / 3 待機
            // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        }
        // ログ出力
        log->write_camn_cn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, ack, seq, recv_size, system_recv_time);

        // 送信間隔 I / 3 待機
        // if (packet_type == "DUMMY" or packet_type == "CONTROL") {西田さん実装
            // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
            // 20260416_河村
            // auto target_time = recv_time + std::chrono::duration<double>(ipt_interval / 3.0);
            // while (hr_clock::now() < target_time) {
            //     std::this_thread::yield(); // ほんの一瞬だけCPUを譲る
            // }
        // }
            // ⭕️ 修正後: 究極の待機関数を呼び出す
            precise_sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3.0));
        
        
        // パケット送信
        if (packet_type == "VIDEO" or packet_type == "DUMMY") {
            send_packet();
        }
    }

    int start_receive() {
        set_realtime_priority(80); //20260416_河村追加
        if (bind(recv_socket, reinterpret_cast<sockaddr*>(&my_addr), sizeof(my_addr)) == -1) {
            std::cerr << "Failed to bind socket" << endl;
            close(recv_socket);
            return 1;
        }
        cout << "Waiting down packet" << endl;

        while (true) {
            receive_packet();
        }

        return 0;
    }

    ~Mucvis_cn() {
        close(send_socket);
        close(recv_socket);
        video_file.close();
        pipe_file.close();

        // cout << "受信映像データサイズ: " << g_recv_size << " byte" << endl;
        // cout << "書き込み映像データサイズ: " << g_write_size << " byte" << endl;
    }
};


int main(int argc, char* argv[]) {
    system_clock::time_point system_start_time = system_clock::now();  // システム起動時刻 ノード間時刻同期用
    hr_clock::time_point hr_start_time = hr_clock::now();  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()

    // 引数でパラメータ指定
    // 引数チェック
    // if (argc != 5) {
    //     std::cerr << "Usage: " << argv[0] << " [My IP Address] [Send IP Address] [IPT interval(s)] [log_name]" << endl;
    //     return 1;
    // }

    // std::string host = argv[1];  // 自身のIPアドレス
    // std::string up_address = argv[2];  // 宛先IPアドレス
    // int down_port = 60202;  // ポート番号60202: 下り用, ローカル: 60204: 3ノード, 60202: 2ノード(1対1)
    // int up_port = 60201;  // ポート番号60201: 上り用, ローカル: 60203: 3ノード, 60201: 2ノード(1対1)
    // double ipt_interval = std::stod(argv[3]);  // 送信間隔 1msぐらい?
    // std::string video_file_name = argv[4];  // 映像ファイル名
    // g_video_file_name = video_file_name;

    // const int node_num = 4;
    // const double communication_range = 1;  // 通信可能距離[m]
    // const double Vehicle_body_length = 0.1;  // 車両長[m]
    // node_type IP default_up default_down
    // std::vector<std::vector<std::string>> routing_table = {
    //     {"camn", "192.168.20.21", "0", "2"},
    //     {"rn", "192.168.20.22", "1", "3"},
    //     {"rn", "192.168.20.23", "2", "4"}, 
    //     {"cn", "192.168.20.24", "2", "0"}
    // };


    // 設定ファイルからパラメータ読み込み
    // 引数チェック
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " [node_num] [log_name]" << endl;
        return 1;
    }
    // ファイルオープン
    std::ifstream ifs("../include/mucvis.conf");
    if (!ifs) {
        std::cerr << "Failed to open setting file: mucvis_setting.txt" << std::endl;
        return 1;
    }
    // パラメータ読み込み
    std::string parameter_list[] = {
        "node_num", "communication_range(m)", "Vehicle_body_length(m)", "IPT_interval(s)", "video_bit_rete(Mbps)", "time(s)", "up_port", "down_port"
    };
    std::string line;
    for(int i = 0; i < int(std::size(parameter_list)); i++) {
        if (std::getline(ifs, line)) {
            auto delimiter_pos = line.find('=');
            if (delimiter_pos != std::string::npos) {
                parameter_list[i] = line.substr(delimiter_pos + 1);
                }
            }
        }

    // lineにnode_typeがあるまで読み飛ばす
    while(std::getline(ifs, line)) {
        if (line.find("node_type") != std::string::npos) {
            break;
        }
    }
    // 初期ルーティングテーブル読み込み
    std::vector<std::vector<std::string>> routing_table;
    while(std::getline(ifs, line)) {
        if (line.empty()) {
            break;
        }
        auto delimiter_pos = line.find(' ');
        std::vector<std::string> row;
        while (delimiter_pos != std::string::npos) {
            row.push_back(line.substr(0, delimiter_pos));
            line = line.substr(delimiter_pos + 1);
            delimiter_pos = line.find(' ');
        }
        row.push_back(line);
        routing_table.push_back(row);
        }
    ifs.close();
    
    const int node_num = std::stoi(parameter_list[0]);
    const double communication_range = std::stod(parameter_list[1]);  // 通信可能距離[m]
    const double Vehicle_body_length = std::stod(parameter_list[2]);  // 車両長[m]
    const double ipt_interval = std::stod(parameter_list[3]);  // 送信間隔 1msぐらい?
    const double video_bit_rate = std::stod(parameter_list[4]);  // 映像ビットレート [Mbps]
    const double generate_time_all = std::stod(parameter_list[5]);  // コマンド生成時間 [s]
    const int up_port = std::stoi(parameter_list[6]);  // ポート番号
    const int down_port = std::stoi(parameter_list[7]);  // ポート番号
    std::string video_file_name = argv[2];  // 映像ファイル名
    g_video_file_name = video_file_name;
    g_send_num.store(std::stoi(routing_table[node_num - 1][2]));
    const int my_node_num = node_num;
    std::string host = routing_table[my_node_num - 1][1];  // 自身のIPアドレス
    std::string up_address = routing_table[g_send_num.load() - 1][1];  // 宛先IPアドレス
    // int send_socket = socket(AF_INET, SOCK_DGRAM, 0);

    // 上のパラメータを表示
    std::cout << "CN" << std::endl;
    std::cout << "node_num = " + std::to_string(node_num) << std::endl;
    std::cout << "communication_range = " + std::to_string(communication_range) + " m" << std::endl;
    std::cout << "Vehicle_body_length = " + std::to_string(Vehicle_body_length) + " m" << std::endl;
    std::cout << "IPT_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
    std::cout << "video_bit_rete = " + std::to_string(video_bit_rate) + " Mbps" << std::endl;
    std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
    std::cout << "up_port = " + std::to_string(up_port) << std::endl;
    std::cout << "down_port = " + std::to_string(down_port) << std::endl;
    std::cout << "video_file_name = " + video_file_name << std::endl;
    std::cout << "my_IP_address = " + host << std::endl;
    std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
    std::cout << "down_port = " + std::to_string(down_port) << std::endl;
    std::cout << "my_node_num = " + std::to_string(my_node_num) << std::endl;
    std::cout << "send_node = " + std::to_string(g_send_num.load()) << std::endl;
    std::cout << "routing_table:" << std::endl;
    for (const auto& row : routing_table) {
        for (const auto& item : row) {
            std::cout << item << " ";
        }
        std::cout << std::endl;
    }

    // ディレクトリが存在しない場合は作成
    if (!std::filesystem::exists("videos")) {
        std::filesystem::create_directory("videos");
    }
    if (!std::filesystem::exists(FILE_NAME_PREFIX + video_file_name)) {
        std::filesystem::create_directory(FILE_NAME_PREFIX + video_file_name);
    }

    // ログファイル作成
    // Log log("IPT", argv[4], system_start_time);
    Log log("IPT", argv[2], system_start_time);
    log.write("CN");
    log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");

    // 標準出力
    // std::cout << "CN" << std::endl;
    // std::cout << "my_IP_address = " + host << std::endl;
    // std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
    // std::cout << "ipt_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
    // std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
    // int send_socket = socket(AF_INET, SOCK_DGRAM, 0);

    // クラスのインスタンス化
    Mucvis_cn mucvis_cn(host, down_port, up_address, up_port, log, ipt_interval, hr_start_time, video_file_name, node_num, std::ref(routing_table));  // 実験環境用
    // Mucvis_cn mucvis_cn(host, 60204, up_address, 60203, log, start_time);  // ローカル環境用(ポートで振り分け)

    // ⭕️ ここに2行追加！ 裏方の書き込みスレッドを作って、すぐに野に放つ（切り離す） 河村
    std::thread writer_thread(&Mucvis_cn::video_writer_thread, &mucvis_cn);
    writer_thread.detach();

    std::thread receiver_thread(&Mucvis_cn::start_receive, &mucvis_cn);

    // シグナルハンドラ設定
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    while (g_video_queue.size() == 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 0.001秒待機
        continue;
    }  // 映像データを受信したらコマンド生成スレッドを開始
    std::thread command_generate_thread(generate_command_fixed_interval, generate_time_all, std::ref(log), hr_start_time);
    std::thread command_input_thread(generate_command_from_input, std::ref(log), hr_start_time, node_num, communication_range, Vehicle_body_length, std::ref(routing_table));

    // コマンド生成終了まで待機
    command_generate_thread.join();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 0.001秒待機
    generate_input_end = true;  // コマンド生成終了フラグを立てる
    usleep(1000);  // 0.001秒待機

    mucvis_cn.~Mucvis_cn();
    // ffmpeg_ts_mp4();

    std::cout << "Closing socket" << std::endl;
    // close(send_socket);
    std::cout << "Program end" << std::endl;
    return 0;
}


// 制御コマンドを標準入力から受け取り，ルーティングを計算し制御コマンドを作成，キューに格納する関数
void generate_command_from_input(Log& log, hr_clock::time_point hr_start_time, const int node_num, const double communication_range, const double Vehicle_body_length, std::vector<std::vector<std::string>>& routing_table) {
    static std::mutex lock;
    hr_clock::time_point start_time = hr_start_time;
    int robot_num = node_num - 1; 

    const double R = communication_range;
    const double Lb = Vehicle_body_length;

    while (generate_input_end == false) {
        // --- フェーズ表示 ---
        double t1 = R; double t2 = R + Lb * 2; double t3 = R * 2; double t4 = R * 2 + Lb; double t5 = R * 3;
        std::cout << "\n========================================" << std::endl;
        printf(" Guidance: (1)L<=%.1f, (2)<=%.1f, (3)<=%.1f, (4)<=%.1f, (5)<=%.1f\n", t1, t2, t3, t4, t5);
        std::cout << "Enter target L [m]: ";

        std::string input;
        std::getline(std::cin, input);
        if (input == "exit") return;

        try {
            double L = std::stod(input);
            int k = std::ceil(L / R);
            k = std::clamp(k, 1, robot_num);

            // 1. 各ノードの前端位置 P の計算
            std::vector<double> P(node_num, 0.0);
            P[3] = L; // CamN (Index 3)
            if (k == 1) { P[2] = 2 * Lb; P[1] = 1 * Lb; } 
            else if (k == 2) { P[2] = std::max(2 * Lb, L - R); P[1] = 1 * Lb; } 
            else if (k == 3) { P[2] = std::max(2 * Lb, L - R); P[1] = std::max(1 * Lb, P[2] - R); }

            // 2. 隙間 (Gap) の算出
            std::vector<double> gaps(robot_num);
            gaps[0] = P[3] - P[2] - Lb; // CamNの隙間
            gaps[1] = P[2] - P[1] - Lb; // RN2の隙間
            gaps[2] = P[1] - 0.0 - Lb;  // RN1の隙間

            // 3. ★ルーティングの動的更新（ここが重要）
            // CtlNの送信先(g_send_num)をkに設定
            g_send_num.store(k);
            
            // 下りパス（映像・ACKがCNへ戻る道）
            routing_table[0][3] = (k == 1) ? "4" : "2"; // CamN -> CN(4) または RN2(2)
            routing_table[1][3] = (k <= 2) ? "4" : "3"; // RN2 -> CN(4) または RN1(3)
            routing_table[2][3] = "4";                  // RN1 -> CN(4)

            // 4. コマンド文字列生成
            std::string final_command;
            for (int i = 0; i < robot_num; i++) {
                int cm = static_cast<int>(std::round(gaps[i] * 100));
                if (i == 0) {
                    final_command += std::to_string(cm) + " " + routing_table[0][3] + ",";
                } else {
                    final_command += std::to_string(cm) + " " + routing_table[i][2] + " " + routing_table[i][3] + ",";
                }
            }
            final_command.pop_back();

            // 5. 送信 20260416 河村修正
            // lock.lock();
            // if (!g_command_queue.empty()) g_command_queue.pop();
            // g_command_queue.push(final_command);
            // lock.unlock();
            {
                std::lock_guard<std::mutex> lock(g_command_mutex);
                if (!g_command_queue.empty()) g_command_queue.pop();
                g_command_queue.push(final_command);
            }

            log.write_generate(std::chrono::duration<double>(hr_clock::now() - start_time), "Command", generate_num++, final_command.size(), final_command);
            printf(">> Target: %.2fm (%d-hop), Command: %s\n", L, k, final_command.c_str());

        } catch (...) { continue; }
    }
}

// 一定間隔でダミーコマンドを生成し，キューに格納する関数
void generate_command_fixed_interval(double generate_time_all, Log& log, hr_clock::time_point hr_start_time) {
    double generate_command_interval = 0.1;  // 100ms ごとに コマンド生成
    std::string command_data = "The control command is generated so that it is 60 bytes long";
    std::chrono::duration<double> duration;
    std::chrono::duration<double> log_time;

    std::cout << "Start generate command data" << std::endl;
    hr_clock::time_point generate_time_now;
    hr_clock::time_point start_time = hr_start_time;

    // int generate_num = 0;
    while (true) {
        generate_time_now = hr_clock::now();
        duration = std::chrono::duration<double>(generate_time_now - start_time);
        if (duration.count() >= generate_time_all) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));  // コマンド生成後0.1秒待ったあと，終了
            return;
        }

        // g_lock.lock();河村
        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            g_command_queue.push(command_data);
        }
        // g_lock.unlock();

        log_time = std::chrono::duration<double>(generate_time_now - start_time);

        // ログに書き込む
        // g_lock.lock();
        log.write_generate(log_time, "Command", generate_num, command_data.size());
        // g_lock.unlock();

        generate_num++;
        
        std::this_thread::sleep_for(std::chrono::milliseconds((int)(generate_command_interval*1000)));
    }
}

// void ffmpeg_ts_mp4() {
//     // ffmpegでtsファイルをmp4に変換
//     std::string file_dir_pass = FILE_NAME_PREFIX + g_video_file_name + "/" + g_video_file_name;
//     std::string ffmpeg_command = "ffmpeg -y -i " + file_dir_pass + ".ts" + " -c copy " + file_dir_pass + ".mp4 " + "-loglevel fatal";
//     int system_command = std::system(ffmpeg_command.c_str());
//     if (system_command == -1) {
//         std::cerr << "Failed to execute ffmpeg command" << std::endl;
//     } else {
//         std::cout << "FFmpeg command executed successfully" << std::endl;
//     }
//     cout << "ffmpeg command: " << ffmpeg_command << endl;
// }
