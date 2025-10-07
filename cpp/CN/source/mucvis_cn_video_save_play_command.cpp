// 制御ノード  同軸環境用
// 映像をtsファイルとして保存する
// 映像をストリーミング再生する．名前付きパイプを使用
// 制御情報を入力可能に

#include <iostream>
#include <thread>  // コンパイル時には-pthread
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
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte(1500-UDPヘッダ-自作ヘッダ(8byte))．以前は1456，tsファイルは188byteのため，1316
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
std::mutex g_lock;
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
    std::ofstream pipe_file;

    std::vector<uint8_t> video_data;
    std::size_t video_data_size;
    char buf[BUFFER_MAX];
    std::vector<uint8_t> send_payload;
    std::vector<uint8_t> recv_payload;

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
        if (!std::filesystem::exists("/tmp/ts_pipe")) {
            if (mkfifo("/tmp/ts_pipe", 0666) == -1) {
                std::cerr << "Failed to create named pipe: /tmp/ts_pipe" << std::endl;
                exit(EXIT_FAILURE);
            }
        }
        cout << "名前付きパイプ生成: /tmp/ts_pipe" << endl;
        pipe_file.open("/tmp/ts_pipe", std::ios::binary);
        if (!pipe_file) {
            std::cerr << "Failed to open named pipe: /tmp/ts_pipe" << std::endl;
            exit(EXIT_FAILURE);
        } else {
            std::cout << "Named pipe opened successfully: /tmp/ts_pipe" << std::endl;
        }

        // 受信ソケットのバッファサイズを設定
        int recv_buffer_size = 1024 * 1024 * 10;  // 1MB
        if (setsockopt(recv_socket, SOL_SOCKET, SO_RCVBUF, &recv_buffer_size, sizeof(recv_buffer_size)) == -1) {
            perror("setsockopt failed");
        }
    }

    // パケット生成
    Packet make_packet() {
        uint32_t packet_type = (0b11 << 30);  // UNKNOWN
        g_lock.lock();
        int g_command_queue_size = g_command_queue.size();
        g_lock.unlock();

        if (g_command_queue_size != 0) {
            packet_type = TYPE_CONTROL;
        }

        if (packet_type == TYPE_CONTROL) {
            g_lock.lock();
            std::string control_command = g_command_queue.front();
            g_command_queue.pop();
            uint32_t sqe = g_control_seq;
            g_control_seq++;
            g_lock.unlock();

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

        g_lock.lock();
        uint32_t ack = g_ack;

        // ログに書き込む
        log->write_camn_cn(duration, "Send", packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
        g_lock.unlock();

        
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

            g_lock.lock();
            g_video_queue.push(packet.get_videoData());
            pre_ack = g_ack;
            g_ack = ack;

            pre_video_seq = g_video_seq;
            g_video_seq = seq;
            g_lock.unlock();

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
            
            g_lock.lock();
            pre_ack = g_ack;
            g_ack = ack;
            g_lock.unlock();
            
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
        // if (packet_type == "DUMMY" or packet_type == "CONTROL") {
            std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        // }

        // パケット送信
        if (packet_type == "VIDEO" or packet_type == "DUMMY") {
            send_packet();
        }
    }

    int start_receive() {
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
    hr_clock::time_point generate_time_now;
    hr_clock::time_point start_time = hr_start_time;

    std::vector<double> node_position(node_num);  // 各ノードと直後のノードの距離
    std::vector<double> node_cn_distance(node_num);  // 各ノードとCNの距離
    double input_distance;
    double distance;
    double correction_distance = (node_num - 1) * Vehicle_body_length;  // 車両サイズを考慮した補正距離
    
    // node_type IP default_up default_down
    // node_num = 4
    // std::vector<std::vector<std::string>> routing_table = {
    //     {"camn", "192.168.20.21", "0", "2"},
    //     {"rn", "192.168.20.22", "1", "3"},
    //     {"rn", "192.168.20.23", "2", "4"},
    //     {"cn", "192.168.20.24", "3", "0"}
    // };

    // 初期変数を出力
    std::cout << "Node number: " << node_num << std::endl;
    std::cout << "Communication range: " << communication_range << " m" << std::endl;
    std::cout << "Vehicle body length: " << Vehicle_body_length << " m" << std::endl;
    std::cout << "Correction distance: " << correction_distance << " m" << std::endl;
    std::cout << std::endl;
    
    while (generate_input_end == false) {
        std::string command_data;
        std::cout << "Enter control command (or 'exit' to quit): " << std::endl;
        std::cout << "(Input the distance from CamN to CN in meters. " << correction_distance << " < (m) < " << correction_distance + communication_range * (node_num - 1) << ")" << std::endl;
        std::getline(std::cin, command_data);
        if (command_data == "exit") {
            return;
        }
        if (command_data.size() > 60) {
            std::cout << "Control command must be 60 bytes or less in length. Please try again." << std::endl;
            continue;
        }

        // 入力が距離の場合，各ノードの位置を計算
        try {
            input_distance = std::stod(command_data) - correction_distance;  // input_distanceはCamNからCNまでの実際の距離

            // --- ここから提案コード ---河村1007
            // 入力が100の場合、全ノードの目標位置を0に設定して逆走させる
            if (std::stod(command_data) == 100) {
                std::cout << "Return command received. Setting all node positions to 0." << std::endl;
                for (int i = 0; i < node_num; i++) {
                    node_position[i] = 0;
                }
            } else {
            // --- ここまで提案コード ---
            
            std::cout << "input_distance = " << input_distance << std::endl;
            for (int i = 0; i < node_num; i++) {
                distance = (i == 0)? input_distance : input_distance;
                // std::cout << "distance = " << distance << std::endl;
                if (distance < 0) {
                    distance = 0;
                }
                node_position[i] = (communication_range > distance)? distance : communication_range;  // min{c指示ommunication_range, 前ノードの位置 - communication_range}
                input_distance -= node_position[i];

                // std::cout << "node_position[" << i << "] = " << node_position[i] << std::endl;
                // std::cout << "input_distance = " << input_distance << std::endl;

                node_cn_distance[i] = node_position[i] + (node_num - i - 2) * Vehicle_body_length;
            }
            if (node_position[node_num-1] > 0){
                std::cout << "error: The distance between the last node and the CN is greater than the communication range." << std::endl;
                continue;
            }
            } // 提案コードのelseブロックを閉じる
            double distance_sum = (node_num-1) * Vehicle_body_length;
            for (int i = 0; i < node_num; i++) {
                distance_sum += node_position[i];
            }

            // ルーティング計算
            // CamN (後ろ，CN)
            if (node_cn_distance[0] > communication_range) {
                routing_table[0][3] = "2";  // down
            } else {
                routing_table[0][3] = std::to_string(node_num);  // down
            }
            // CN
            for (int i = node_num - 3; i >= 0; i--) {
                if (node_cn_distance[i] > communication_range) {
                    routing_table[node_num-1][2] = std::to_string(i + 2);  // up
                    break;
                } else {
                    routing_table[node_num-1][2] = "1";  // up
                }
            }
            // RN
            for (int i = 1; i < node_num - 1; i++) {
                // std::cout << "i = " << i << std::endl;
                // up 2択
                if (node_cn_distance[i-1] > communication_range) {
                    routing_table[i][2] = std::to_string(i);
                } else {
                    routing_table[i][2] = "0";
                }
                // down 2or3択(後ろ，CN，なし)
                if (node_num - i - 1 > 1) {  // RNが1台以上後ろにいる場合
                    if (node_cn_distance[i] > communication_range) {
                        routing_table[i][3] = std::to_string(i + 2);  // down
                        continue;
                    }
                }
                if (node_cn_distance[i-1] > communication_range) {
                    routing_table[i][3] = std::to_string(node_num);  // down
                } else {
                    routing_table[i][3] = std::to_string(node_num);  // down
                }
            }

            // 出力
            // std::cout << "command_data: " << command_data << std::endl;
            std::cout << "distance sum: " << distance_sum << std::endl;
            for (int i = 0; i < node_num; i++) {
                std::cout << "Node " << i + 1 << ": " 
                          << std::setw(5) << routing_table[i][0] << " " 
                          << std::setw(10) << node_position[i] << " " 
                          << std::setw(10) << node_cn_distance[i] << " " 
                          << std::setw(5) << routing_table[i][2] << " " 
                          << std::setw(5) << routing_table[i][3] << std::endl;
            }
            std::cout << "CN next up address: " << routing_table[node_num-1][2] << " " << routing_table[std::stoi(routing_table[node_num-1][2])-1][1] << std::endl;
            // int i = 1;
            // std::cout << "Routing Table:" << std::endl;
            // for (const auto& row : routing_table) {
            //     std::cout << i << " ";
            //     for (const auto& elem : row) {
            //         std::cout << elem << " ";
            //     }
            //     std::cout << std::endl;
            //     i++;
            // }

            // 制御コマンド生成
            command_data.clear();
            // node_positionをcm単位に変換
            for (int i = 0; i < node_num; i++) {
                node_position[i] = std::round(node_position[i] * 100);  // cm単位に変換
            }
            command_data = std::to_string(static_cast<int>(node_position[0])) + " " + routing_table[0][3] + ",";
            for (int i = 1; i < node_num-1; i++) {
                command_data += std::to_string(static_cast<int>(node_position[i])) + " " + routing_table[i][2] + " " + routing_table[i][3] + ",";
            }
            command_data.pop_back();  // 最後のカンマを削除
            g_send_num.store(std::stoi(routing_table[node_num - 1][2]));  // 送信先ノード番号を更新
        }
        catch (const std::invalid_argument& e) {  // 変換できない場合はそのままコマンドとして使用
            // std::cout << "Invalid input. Please enter a valid number." << std::endl;
            // continue;
        }

        std::cout << "Final command_data: " << std::endl << command_data << std::endl;
        std::cout << "command_data size: " << command_data.size() << " bytes" << std::endl;
        std::cout << std::endl;

        // キュー内にコマンドがある場合，取り出してから格納する(ダミーコマンドを削除)
        lock.lock();
        if (g_command_queue.size() != 0) {
            g_command_queue.pop();
        }
        g_command_queue.push(command_data);
        lock.unlock();

        generate_time_now = hr_clock::now();
        std::chrono::duration<double> log_time = std::chrono::duration<double>(generate_time_now - start_time);

        // ログに書き込む
        log.write_generate(log_time, "Command", generate_num, command_data.size(), command_data);

        generate_num++;
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

        g_lock.lock();
        g_command_queue.push(command_data);
        g_lock.unlock();

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
