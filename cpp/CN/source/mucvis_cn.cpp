// 制御ノード  同軸環境用

#include <iostream>
#include <thread>  // コンパイル時には-pthread
#include <queue>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sstream>

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
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte(1500-UDPヘッダ-自作ヘッダ(8byte))．以前は1456
#define CONTROL_SEQ_MAX (1 << 30)  // 30bitの最大値
#define VIDEO_SEQ_MAX 0xffffffff  // 32bitの最大値
#define DUMMY_SEQ_MAX 3  // ダミーパケット送信回数上限

// グローバル変数
uint32_t g_control_seq = 0;  // 制御情報のシーケンス番号 0~2^30
uint32_t g_video_seq = 0;  // 映像シーケンス番号 0~2^32
uint32_t g_ack = -1;  // ack 0~2^30
ByteQueue g_video_bytequeue;  // 映像データキュー
ByteQueue g_command_bytequeue;  // 制御情報キュー
std::queue<std::vector<uint8_t>> g_video_queue;  // 映像データパケットキュー
std::queue<std::string> g_command_queue;  // 制御コマンドキュー
std::mutex g_lock;

const double generate_time_all = 30.0;  // コマンド生成時間 [s]

void generate_command_fixed_interval(double generate_time_all, Log& log, std::chrono::high_resolution_clock::time_point start_time);

// MUCViS_CNクラス
class Mucvis_cn {
    hr_clock::time_point hr_start_time;  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()
    int send_socket = socket(AF_INET, SOCK_DGRAM, 0);
    int recv_socket = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in my_addr;
    struct sockaddr_in up_addr;
    Log *log;
    double ipt_interval;

public:
    Mucvis_cn(std::string my_address, int my_port, std::string up_address, int up_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time) {
        my_addr.sin_family = AF_INET;
        my_addr.sin_addr.s_addr = inet_addr(my_address.c_str());
        my_addr.sin_port = htons(my_port);
        up_addr.sin_family = AF_INET;
        up_addr.sin_addr.s_addr = inet_addr(up_address.c_str());
        up_addr.sin_port = htons(up_port);
        this->log = &log;
        this->ipt_interval = ipt_interval;
        this->hr_start_time = hr_start_time;
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

        std::vector<uint8_t> payload = packet.get_payload();

        // 上りへ送信
        sendto(send_socket, payload.data(), payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

        system_clock::time_point system_send_time = system_clock::now();
        hr_clock::time_point send_time = hr_clock::now();
        std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

        g_lock.lock();
        uint32_t ack = g_ack;
        g_lock.unlock();

        // ログに書き込む
        log->write_camn_cn(duration, "Send", packet_type, ack, packet.get_commandSeq(), payload.size(), system_send_time);
    }

    void receive_packet() {
        char buf[BUFFER_MAX];
        uint32_t seq = 0;
        uint32_t ack = 0;
        uint32_t pre_ack;

        int recv_size = recv(recv_socket, buf, sizeof(buf), 0);

        system_clock::time_point system_recv_time = system_clock::now();
        hr_clock::time_point recv_time = hr_clock::now();
        std::vector<uint8_t> payload(buf, buf + recv_size);
        Packet packet(payload);
        std::string packet_type = packet.get_type();

        if (packet_type == "VIDEO") {
            ack = packet.get_ack();
            seq = packet.get_videoSeq();

            g_lock.lock();
            g_video_queue.push(packet.get_videoData());
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
            // std::this_thread::sleep_for(std::chrono::duration<double>(ipt_interval / 3));
            std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        } else {  // CONTROL
            ack = packet.get_ack();
            std::string command = packet.get_command();

            // 送信間隔 I / 3 待機
            // std::this_thread::sleep_for(std::chrono::duration<double>(ipt_interval / 3));
            std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        }
        // ログ出力
        log->write_camn_cn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, ack, seq, recv_size, system_recv_time);

        // パケット送信
        send_packet();
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
    }
};


int main(int argc, char* argv[]) {
    system_clock::time_point system_start_time = system_clock::now();  // システム起動時刻 ノード間時刻同期用
    hr_clock::time_point hr_start_time = hr_clock::now();  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()

    // 引数チェック
    if (argc != 5) {
        std::cerr << "Usage: " << argv[0] << " [My IP Address] [Send IP Address] [IPT interval(s)] [log_name]" << endl;
        return 1;
    }

    std::string host = argv[1];  // 自身のIPアドレス
    std::string up_address = argv[2];  // 宛先IPアドレス
    int down_port = 60202;  // ポート番号60202: 下り用, ローカル: 60204: 3ノード, 60202: 2ノード(1対1)
    int up_port = 60201;  // ポート番号60201: 上り用, ローカル: 60203: 3ノード, 60201: 2ノード(1対1)
    double ipt_interval = std::stod(argv[3]);  // 送信間隔 1msぐらい?

    // ログファイル作成
    Log log("IPT", argv[4], system_start_time);
    log.write("CN");
    log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");

    // 標準出力
    std::cout << "CamN" << std::endl;
    std::cout << "my_IP_address = " + host << std::endl;
    std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
    std::cout << "ipt_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
    std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
    int send_socket = socket(AF_INET, SOCK_DGRAM, 0);

    // クラスのインスタンス化
    Mucvis_cn mucvis_cn(host, down_port, up_address, up_port, log, ipt_interval, hr_start_time);  // 実験環境用
    // Mucvis_cn mucvis_cn(host, 60204, up_address, 60203, log, start_time);  // ローカル環境用(ポートで振り分け)

    std::thread receiver_thread(&Mucvis_cn::start_receive, &mucvis_cn);


    while (g_video_queue.size() == 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 0.001秒待機
        continue;
    }  // 映像データを受信したらコマンド生成スレッドを開始
    std::thread command_generate_thread(generate_command_fixed_interval, generate_time_all, std::ref(log), hr_start_time);

    // コマンド生成終了まで待機
    command_generate_thread.join();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 0.001秒待機

    mucvis_cn.~Mucvis_cn();

    std::cout << "Closing socket" << std::endl;
    close(send_socket);
    std::cout << "Program end" << std::endl;
    return 0;
}

void generate_command_fixed_interval(double generate_time_all, Log& log, hr_clock::time_point hr_start_time) {
    double generate_command_interval = 0.1;  // 100ms ごとに コマンド生成
    std::string command_data = "The control command is generated so that it is 60 bytes long";

    std::cout << "Start generate command data" << std::endl;
    hr_clock::time_point generate_time_now;
    hr_clock::time_point start_time = hr_start_time;

    int generate_num = 0;
    while (true) {
        generate_time_now = hr_clock::now();
        std::chrono::duration<double> duration = std::chrono::duration<double>(generate_time_now - start_time);
        if (duration.count() >= generate_time_all) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));  // コマンド生成後0.1秒待ったあと，終了
            return;
        }

        g_lock.lock();
        g_command_queue.push(command_data);
        g_lock.unlock();

        std::chrono::duration<double> log_time = std::chrono::duration<double>(generate_time_now - start_time);

        // ログに書き込む
        log.write_generate(log_time, "Command", generate_num, command_data.size());

        generate_num++;
        
        std::this_thread::sleep_for(std::chrono::milliseconds((int)(generate_command_interval*1000)));
    }
}
