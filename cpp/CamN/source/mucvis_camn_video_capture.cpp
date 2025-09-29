// カメラノード  同軸環境用 グローバルミューテックス使用
// libcamra-vidの出力をffmpegでts形式にしてからMUCViSに渡す
// 映像ビットレートは指定可能

#include <iostream>
#include <thread>  // コンパイル時には-pthread
#include <queue>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sstream>
#include <mutex>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <fcntl.h>
#include <sys/wait.h>
#include <sys/epoll.h>
#include <filesystem>

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
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte．tsファイルは188byteのため，1316
#define VIDEO_BUFFER_SIZE (MAX_VIDEO_SIZE * 100)  // パイプから読み込むバッファサイズ
#define CONTROL_SEQ_MAX (1 << 30)  // 30bitの最大値
#define VIDEO_SEQ_MAX 0xffffffff  // 32bitの最大値
#define DUMMY_SEQ_MAX 3  // ダミーパケット送信回数上限
#define WIDTH "1920"  // 映像幅 1280 1920 
#define HEIGHT "1080"  // 映像高さ 720 1080
#define FRAMERATE "30"  // フレームレート
#define FILE_NAME_PREFIX "videos/IPT_"  // 映像ファイル名プレフィックス

// グローバル変数
uint32_t g_control_seq = 0;  // 制御情報のシーケンス番号 0~2^30
uint32_t g_video_seq = 0;  // 映像シーケンス番号 0~2^32
uint32_t g_ack = 0;  // ack 0~2^30
int g_dummy_seq = 0;  // ダミーパケットのシーケンス番号
ByteQueue g_video_bytequeue;  // 映像データキュー
std::queue<std::tuple<uint32_t, uint32_t, std::vector<uint8_t>>> g_video_queue;  // 映像データパケットキュー
std::queue<std::vector<uint8_t>> g_command_queue;  // 制御情報パケットキュー
std::mutex g_lock;
std::string g_video_file_name;  // 映像ファイル名

const double generate_time_all = 60.0;  // ビデオデータ生成時間 [s]

// void generate_video_fixed_interval(double generate_time_all, double video_bit_rate, Log& log, hr_clock::time_point start_time);
// void ffmpeg_ts_mp4();

// シグナルハンドラ
void signal_handler(int sig) {
    std::cout << "\n終了処理中..." << std::endl;

    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    std::cout << "Program end" << std::endl;

    exit(0);
}


// MUCViS_CamNクラス
class Mucvis_camn {
private:
    hr_clock::time_point hr_start_time;  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()
    int send_socket = socket(AF_INET, SOCK_DGRAM, 0);
    int recv_socket = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in my_addr;
    struct sockaddr_in down_addr;
    Log *log;
    double ipt_interval;

    int pipefd[2];  // パイプのファイルディスクリプタ
    int epoll_fd;
    struct epoll_event event;

    std::string video_file_name;
    std::ofstream video_file;
    std::vector<uint8_t> video_data;
    std::vector<uint8_t> payload;
    std::vector<uint8_t> recv_payload;
    uint8_t buffer[VIDEO_BUFFER_SIZE];
    char recv_buf[BUFFER_MAX];

public:
    Mucvis_camn(std::string my_address, int my_port, std::string down_address, int down_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time, int pipefd[2], std::string video_file_name) {
        my_addr.sin_family = AF_INET;
        my_addr.sin_addr.s_addr = inet_addr(my_address.c_str());
        my_addr.sin_port = htons(my_port);
        down_addr.sin_family = AF_INET;
        down_addr.sin_addr.s_addr = inet_addr(down_address.c_str());
        down_addr.sin_port = htons(down_port);
        this->log = &log;
        this->ipt_interval = ipt_interval;
        this->hr_start_time = hr_start_time;

        this->pipefd[0] = pipefd[0];
        this->pipefd[1] = pipefd[1];

        this->video_file_name = video_file_name;
        video_data.reserve(MAX_VIDEO_SIZE);
        payload.reserve(MAX_VIDEO_SIZE + 8);  // 1472
        recv_payload.reserve(MAX_VIDEO_SIZE + 8);  // 1472

        // 映像ファイルを開く
        std::string file_name_pass = FILE_NAME_PREFIX + video_file_name + "/" + video_file_name + ".ts";
        video_file.open(file_name_pass, std::ios::binary);
        if (!video_file) {
            std::cerr << "Failed to open video file: " << file_name_pass << std::endl;
            exit(EXIT_FAILURE);
        }

        // epollの初期化
        epoll_fd = epoll_create1(0);
        if (epoll_fd == -1) {
            perror("epoll_create1 failed");
            exit(EXIT_FAILURE);
        }

        event.events = EPOLLIN;
        event.data.fd = pipefd[0];
        if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, pipefd[0], &event) == -1) {
            perror("epoll_ctl failed");
            exit(EXIT_FAILURE);
        }
        // パイプを非ブロッキングにする
        int flags = fcntl(pipefd[0], F_GETFL, 0);
        if (flags == -1) {
            perror("fcntl failed");
        } else {
            if (fcntl(pipefd[0], F_SETFL, flags | O_NONBLOCK) == -1) {
                perror("fcntl failed");
            }
        }

        // send_socketを非ブロッキングにする
        // int flags = fcntl(send_socket, F_GETFL, 0);
        // if (flags == -1) {
        //     perror("fcntl failed");
        // } else {
        //     if (fcntl(send_socket, F_SETFL, flags | O_NONBLOCK) == -1) {
        //         perror("fcntl failed");
        //     }
        // }

    }

    // パケット生成
    Packet make_packet() {
        uint32_t packet_type = TYPE_VIDEO;

        // パイプに映像データがあれば，取り出す
        // uint8_t buffer[VIDEO_BUFFER_SIZE];
        ssize_t bytes_read = 0;

        g_lock.lock();
        int dummy_seq = g_dummy_seq;
        int video_bytequeue_size = g_video_bytequeue.size();
        g_lock.unlock();

        if (video_bytequeue_size == 0 && dummy_seq < DUMMY_SEQ_MAX) {
            // ダミーパケットを生成する前に，パイプに映像データがあるか確認
            // buffer[0] = '\0';  // バッファを初期化
            bytes_read = read(pipefd[0], buffer, VIDEO_BUFFER_SIZE);
            if (bytes_read > 0) {
                // .tsファイルに書き込む
                video_file.write(reinterpret_cast<const char*>(buffer), bytes_read);
                //河村コメントあうと0926

                // video_file.flush();

                // 読み込んだデータを映像データキューに入れる
                g_video_bytequeue.put(std::vector<uint8_t>(buffer, buffer + bytes_read));
            } else {
                packet_type = TYPE_DUMMY;
            }
        }

        if (packet_type == TYPE_VIDEO) {
            // std::vector<uint8_t> video_data;
            // video_data.reserve(MAX_VIDEO_SIZE);
            video_data.clear();

            // 映像データキューから映像データを取り出す
            while (video_data.size() == 0) {
                g_lock.lock();
                video_data = g_video_bytequeue.get(MAX_VIDEO_SIZE);
                g_lock.unlock();

                // 映像データキューが空の場合は，epollでパイプを監視し，映像データキューに取り出す
                if (video_data.empty()) {
                    // epollでパイプを監視し，映像データキューに取り出す
                    struct epoll_event events[1];
                    while (g_video_bytequeue.size() == 0) {
                        int nfds = epoll_wait(epoll_fd, events, 1, -1);
                        if (nfds == -1) {
                            perror("epoll_wait failed");
                            exit(EXIT_FAILURE);
                        }
                        // パイプからデータを映像データキューに取り出す
                        if (events[0].data.fd == pipefd[0]) {
                            // パイプからデータを読み込む
                            // buffer[0] = '\0';  // バッファを初期化
                            bytes_read = read(pipefd[0], buffer, VIDEO_BUFFER_SIZE);
                            
                            if (bytes_read > 0) {
                                // .tsファイルに書き込む
                                video_file.write(reinterpret_cast<const char*>(buffer), bytes_read);
                                //河村コメントあうと0926

                                // video_file.flush();
                                
                                // 読み込んだデータを映像データキューに入れる
                                g_video_bytequeue.put(std::vector<uint8_t>(buffer,buffer + bytes_read));
                            }
                        }
                    }
                } else {
                    break;
                }
            }

            g_lock.lock();
            uint32_t ack = g_ack;
            uint32_t seq = g_video_seq;
            g_video_seq++;
            g_dummy_seq = 0;
            g_lock.unlock();

            // ビデオデータパケット生成
            Packet packet(packet_type, ack, seq, video_data);

            return packet;
        } else if (packet_type == TYPE_DUMMY) {
            g_lock.lock();
            uint32_t ack = g_ack;
            g_dummy_seq++;
            g_lock.unlock();

            // ダミーパケット生成
            Packet packet(packet_type, ack);

            return packet;
        } else if (packet_type == TYPE_CONTROL) {
            cout << "error: make control packet in CamN" << endl;
            g_lock.lock();
            uint32_t sqe = g_control_seq;
            g_control_seq++;
            g_lock.unlock();

            // パケット生成
            Packet packet(packet_type, sqe, "control command by CamN");
            
            return packet;
        }
        Packet packet(0b11 << 30, 0);
        return packet;
    }

    void send_packet() {
        // パケット生成
        Packet packet = make_packet();

        std::string packet_type = packet.get_type();
        if (packet_type == "UNKNOWN") {
            cout << "UNKNOWN packet" << endl;
            return;
        }
        // std::vector<uint8_t> payload = packet.get_payload();
        // payload.clear();
        // payload = packet.get_payload();
        payload = std::move(packet.get_payload());  // ムーブで効率的に転送

        // 下りへ送信
        sendto(send_socket, payload.data(), payload.size(), 0, (struct sockaddr *)&down_addr, sizeof(down_addr));
        // while (true) {
        //     int send_size = sendto(send_socket, payload.data(), payload.size(), 0, (struct sockaddr *)&down_addr, sizeof(down_addr));
        //     if (send_size < 0) {
        //         perror("sendto failed");
        //             if (errno == EAGAIN || errno == EWOULDBLOCK) {
        //                 cout << "sendto EAGAIN" << endl;
        //                 continue;
        //             }
        //     } else {
        //         break;
        //     }
        // }

        system_clock::time_point system_send_time = system_clock::now();
        hr_clock::time_point send_time = hr_clock::now();
        std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

        // ログに書き込む
        packet_type = packet.get_type();
        uint32_t seq = packet.get_videoSeq();
        if (packet_type == "DUMMY") {
            g_lock.lock();
            seq = g_dummy_seq - 1;
            g_lock.unlock();
        }

        log->write_camn_cn(duration, "Send", packet_type, packet.get_ack(), seq, payload.size(), system_send_time);
    }

    void receive_packet() {
        // char recv_buf[BUFFER_MAX];
        // recv_buf[0] = '\0';  // バッファを初期化
        uint32_t seq = 0;
        uint32_t ack = 0;

        int recv_size = recv(recv_socket, recv_buf, sizeof(recv_buf), 0);

        system_clock::time_point system_recv_time = system_clock::now();
        hr_clock::time_point recv_time = hr_clock::now();
        // std::vector<uint8_t> recv_payload(buf, buf + recv_size);
        // recv_payload.clear();
        // recv_payload = std::vector<uint8_t>(recv_buf, recv_buf + recv_size);
        recv_payload.assign(recv_buf, recv_buf + recv_size);  // ムーブで効率的に転送
        Packet packet(recv_payload);
        std::string packet_type = packet.get_type();

        if (packet_type == "CONTROL") {
            seq = packet.get_commandSeq();
            
            g_lock.lock();
            ack = g_ack;
            g_ack = seq;
            g_lock.unlock();
            std::string command = packet.get_command();
        } 
        // ログ出力
        log->write_camn_cn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, ack, seq, recv_size, system_recv_time);
    }

    int start_receive() {
        if (bind(recv_socket, reinterpret_cast<sockaddr*>(&my_addr), sizeof(my_addr)) == -1) {
            std::cerr << "Failed to bind socket" << endl;
            close(recv_socket);
            return 1;
        }
        cout << "Waiting up packet" << endl;

        while (true) {
            receive_packet();
        }

        return 0;
    }

    int start_send() {
        cout << "Start sending" << endl;
        hr_clock::time_point ipt_start;
        hr_clock::time_point ipt_end;

        while (true) {
            // 送信開始時間計測
            ipt_start = hr_clock::now();

            send_packet();

            // ipt_interval待機
            std::this_thread::sleep_until(ipt_start + std::chrono::duration<double>(ipt_interval));
        }
        return 0;
    }

    ~Mucvis_camn() {
        close(send_socket);
        close(recv_socket);
        close(epoll_fd);
    if (video_file.is_open()) video_file.close();
    }
};


int main(int argc, char* argv[]) {
    system_clock::time_point system_start_time = system_clock::now();  // システム起動時刻 ノード間時刻同期用
    hr_clock::time_point hr_start_time = hr_clock::now();  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()

    // 引数チェック
    if (argc != 6) {
        std::cerr << "Usage: " << argv[0] << " [My IP Address] [Send IP Address] [IPT interval(s)] [video bit rate(Mbps)] [log_name]" << endl;
        return 1;
    }

    std::string host = argv[1];  // 自身のIPアドレス
    std::string down_address = argv[2];  // 宛先IPアドレス
    int down_port = 60202;  // ポート番号60202: 下り用
    int up_port = 60201;  // ポート番号60201: 上り用
    double ipt_interval = std::stod(argv[3]);  // 送信間隔 1msぐらい?
    double video_bit_rate = std::stod(argv[4]);  // 映像ビットレート
    // double generate_time_all = std::stod(argv[4]) * 60;  // 映像撮影時間 [s]
    std::string video_file_name = argv[5];  // 映像ファイル名
    g_video_file_name = video_file_name;

    // ディレクトリが存在しない場合は作成
    if (!std::filesystem::exists("videos")) {
        std::filesystem::create_directory("videos");
    }
    if (!std::filesystem::exists(FILE_NAME_PREFIX + video_file_name)) {
        std::filesystem::create_directory(FILE_NAME_PREFIX + video_file_name);
    }

    // ログファイル作成
    Log log("IPT", argv[5], system_start_time);
    log.write("CamN");
    log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");
    log.write("video_bit_rate = " + std::to_string(video_bit_rate) + " Mbps");
    log.write("video_file_name = " + video_file_name);
    log.write("resolution = " + std::string(WIDTH) + "x" + std::string(HEIGHT) + " @ " + FRAMERATE + " fps");

    // 標準出力
    std::cout << "CamN" << std::endl;
    std::cout << "my_IP_address = " + host << std::endl;
    std::cout << "down_address = " + down_address + ":" + std::to_string(down_port) << std::endl;
    std::cout << "ipt_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
    std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
    std::cout << "video_bit_rate" + std::to_string(video_bit_rate) << std::endl;
    std::cout << "log_name = " + std::string(argv[5]) << std::endl;
    std::cout << "video_file_name = " + video_file_name << std::endl;
    std::cout << "resolution = " << WIDTH << "x" << HEIGHT << " @ " << FRAMERATE << " fps" << std::endl;

    // パイプ作成
    int pipefd[2];
    if (pipe(pipefd) == -1) {
        std::cerr << "Failed to create pipe" << std::endl;
        return 1;
    }

    // クラスのインスタンス化
    Mucvis_camn mucvis_camn(host, up_port, down_address, down_port, log, ipt_interval, hr_start_time, pipefd, video_file_name);
    
    // スレッド生成 受信
    std::thread receiver_thread(&Mucvis_camn::start_receive, &mucvis_camn);
    // スレッド生成 映像生成
    // std::thread video_generate_thread(generate_video_fixed_interval, generate_time_all, video_bit_rate, std::ref(log), hr_start_time);

    // 映像生成プロセス生成
    std::string capture_time = std::to_string((int)generate_time_all);
    // libcamera-vidプロセス起動
    pid_t pid = fork();
    if (pid == 0) {
        dup2(pipefd[1], STDOUT_FILENO);
        close(pipefd[0]);
        setenv("LIBCAMERA_LOG_LEVELS", "*:4", 1); // ログをほぼ抑制
        // コマンド文字列構築
        std::string cmd = 
            "libcamera-vid -n -t " + std::to_string(std::stoi(capture_time)*1000) +
            " --width " + WIDTH +
            " --height " + HEIGHT +
            " --framerate " + FRAMERATE +
            " --bitrate " + std::to_string(int(video_bit_rate * 1000 * 1000)) +  // ビットレート指定
            " --codec h264 --inline -o - | "  // libcamera-vidの出力をパイプ
            "ffmpeg -fflags +genpts -analyzeduration 100000 -i - -c copy -f mpegts "  // 入力ストリームの解析に使う最大時間を0.1秒に設定
            "-loglevel fatal "  // ログレベルをfatalに設定;
            "-";
        execlp("sh", "sh", "-c", cmd.c_str(), nullptr);
        exit(EXIT_FAILURE);
    }
    
    // スレッド生成 送信
    std::thread sender_thread(&Mucvis_camn::start_send, &mucvis_camn);

    // シグナルハンドラ設定
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // 映像生成終了まで待機
    // video_generate_thread.join();

    // libcamera-vidプロセスの終了を待つ
    int status;
    waitpid(pid, &status, 0);
    if (WIFEXITED(status)) {
        std::cout << "映像撮影終了" << std::endl;
    } else {
        std::cerr << "映像撮影異常終了" << std::endl;
    }

    std::this_thread::sleep_for(std::chrono::seconds(5));  // 映像生成終了後5秒待機

    // 終了処理
    close(pipefd[1]);
    close(pipefd[0]);
    mucvis_camn.~Mucvis_camn();
    // ffmpeg_ts_mp4();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    std::cout << "Program end" << std::endl;
    return 0;
}


// void generate_video_fixed_interval(double generate_time_all, double video_bit_rate, Log& log, hr_clock::time_point hr_start_time) {
//     hr_clock::time_point start_time = hr_start_time;
//     double stop_time = generate_time_all;
//     double generate_video_interval = 0.125;  // 125ms ごとに ビデオデータ生成+
//     size_t generate_video_data_size = static_cast<size_t>(video_bit_rate * 1e6 * generate_video_interval / 8);  // 一回の生成データ量 [byte]
//     std::vector<uint8_t> video_data(generate_video_data_size, 0xff);  // ビデオデータ
//     int generate_num = 0;

//     std::cout << "Start generate video data" << std::endl;
//     hr_clock::time_point generate_time_now;

//     while (true) {
//         generate_time_now = hr_clock::now();;
//         std::chrono::duration<double> duration = std::chrono::duration<double>(generate_time_now - start_time);
//         if (duration.count() >= stop_time) {
//             std::this_thread::sleep_for(std::chrono::seconds(10));  // 映像生成後10秒待ったあと，終了
//             return;
//         }

//         // 映像データをキューに入れる
//         // g_lock.lock();
//         // if (g_video_bytequeue.size() < generate_video_data_size * 2) {
//         //     g_video_bytequeue.put(video_data);
//         // }
//         // g_lock.unlock();
        
//         g_lock.lock();
//         g_video_bytequeue.put(video_data);
//         g_lock.unlock();

//         std::chrono::duration<double> log_time = std::chrono::duration<double>(generate_time_now - start_time);

//         // ログに書き込む
//         log.write_generate(log_time, "Video", generate_num, video_data.size());
//         generate_num++;
        
//         std::this_thread::sleep_for(std::chrono::milliseconds((int)(generate_video_interval*1000)));
//     }
// }

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
