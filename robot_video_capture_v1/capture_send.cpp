// libcamera-vidを使用して映像をキャプチャし、ffmpegでtsファイルに変換し，UDPで送信するプログラム

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <thread>
#include <atomic>
#include <sys/wait.h>
#include <stdexcept>
#include <csignal>
#include <algorithm>
#include <cstring>
#include <system_error>
#include <ostream>
#include <iostream>
#include <fstream>
#include <sstream>
#include <filesystem>

#define MTU_SIZE 1316  // tsファイルは188byte単位であるため, 188 * 7
#define BUFFER_SIZE (1316 * 100)
// #define LOCAL_SAVE_INTERVAL 1 // 保存間隔（秒）
#define WIDTH "1280"  // 映像幅
#define HEIGHT "720"  // 映像高さ
#define FRAMERATE "30"  // フレームレート

using namespace std::chrono;
namespace fs = std::filesystem;

fs::path output_dir;
std::atomic<bool> running{true};
std::ofstream video_file;
std::time_t last_save_time = 0;
int file_counter = 1;


// タイムスタンプ付きディレクトリ作成
fs::path create_timestamp_dir() {
    auto now = system_clock::now();
    auto in_time_t = system_clock::to_time_t(now);

    std::stringstream ss;
    ss << "video_" << std::put_time(std::localtime(&in_time_t), "%Y%m%d_%H%M%S");
    fs::path dir = fs::current_path() / "videos" / ss.str();

    return dir;
}

// TSファイル連結処理
// void concat_ts_files() {
//     fs::path output_file = output_dir / "output.mp4";

//     // 連番の.tsファイルをconcat形式に変換
//     std::stringstream concat;
//     concat << "concat:";
//     for (int i = 1; i < file_counter; ++i) {
//         concat << output_dir.string() << "/" << i << ".ts";
//         if (i < file_counter) {
//             concat << "|";
//         }
//     }

//     // FFmpegによりtsファイルをmp4に変換
//     std::string cmd = "ffmpeg -i \"" + concat.str() + "\" -c copy \"" + output_file.string() + "\" " + "-loglevel fatal";
//     std::system(cmd.c_str());
//     std::cout << "FFmpeg command: " << cmd << std::endl;

//     // 一時ファイル削除（任意）
//     // for (int i = 1; i < file_counter; ++i) {
//     //     fs::remove(output_dir / (std::to_string(i) + ".ts"));
//     // }
//     // std::cout << "Temporary files deleted." << std::endl;
// }
void signal_handler(int signum){
    running = false; 
}

void udp_sender(int sock, struct sockaddr_in addr, int pipe_fd) {
    char buffer[BUFFER_SIZE];
    struct pollfd fds[1] = {{pipe_fd, POLLIN, 0}};

    std::cout << "送信開始" << std::endl;

    while (running) {
        int ret = poll(fds, 1, 100);
        if (ret > 0 && (fds[0].revents & POLLIN)) {
            ssize_t bytes_read = read(pipe_fd, buffer, BUFFER_SIZE);
            if (bytes_read > 0) {
                // ローカル保存
                if (video_file.is_open()) {
                    video_file.write(buffer, bytes_read);
                    video_file.flush();
                }

                // UDP送信
                for (size_t i = 0; i < static_cast<size_t>(bytes_read); i += MTU_SIZE) {
                    size_t chunk_size = std::min(
                        static_cast<size_t>(MTU_SIZE),
                        static_cast<size_t>(bytes_read - i)
                    );
                    try {
                        sendto(sock, buffer + i, chunk_size, 0,
                              (struct sockaddr*)&addr, sizeof(addr));
                    } catch (const std::system_error& e) {
                        std::cerr << "送信エラー: " << e.what() << std::endl;
                        running = false;
                        break;
                    }
                }
            }
        }
    }
}

int main(int argc, char* argv[]) {
    if (argc < 4 || argc > 5) {
       std::cerr << "Usage: " << argv[0] << " [送信先IP] [撮影時間(s) 0で止めるまで] [ビデオビットレート(kbps)] [映像保存フォルダ名(なしで実行日時)]\n";
       return 1;
    }

    std::string send_ip = argv[1];
    std::string capture_time = argv[2];
    std::string video_bitrate = argv[3];  // デフォルトビットレート
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    // 出力ディレクトリ作成
    if (argc > 4) {
        output_dir = fs::current_path() / "videos" / fs::path(argv[4]);
    } else {
        output_dir = create_timestamp_dir();
    }
    // ディレクトリが存在しない場合は作成
    if (!fs::exists(output_dir)) {
        fs::create_directory(output_dir);
    }
    
    // 映像ファイル名
    std::string filename = "output.ts";
    std::string full_path = (output_dir / filename).string();
    video_file.open(full_path, std::ios::binary);

    std::cout << "送信先IP: " << send_ip << std::endl;
    std::cout << "撮影時間: " << capture_time << "s" << std::endl;
    std::cout << "映像保存フォルダ名: " << output_dir << std::endl;
    std::cout << "ビデオビットレート: " << video_bitrate << "kbps" << std::endl;

    // パイプ作成
    int pipefd[2];
    if (pipe2(pipefd, O_NONBLOCK) == -1) {
        throw std::runtime_error("パイプ作成失敗: " + std::string(strerror(errno)));
    }

    // libcamera-vidプロセス起動
    pid_t pid = fork();
    if (pid == 0) {
        dup2(pipefd[1], STDOUT_FILENO);
        close(pipefd[0]);
        // コマンド文字列構築
        std::string cmd = 
            "libcamera-vid -t " + std::to_string(std::stoi(capture_time)*1000) +
            " --width " + WIDTH +
            " --height " + HEIGHT +
            " --framerate " + FRAMERATE +
            " --bitrate " + std::to_string(std::stoi(video_bitrate) * 1000) +  // ビットレート指定
            " --codec h264 --inline -o - | "  // libcamera-vidの出力をパイプ
            "ffmpeg -i - -c copy -f mpegts -";  // ffmpegでTS変換
        execlp("sh", "sh", "-c", cmd.c_str(), nullptr);
        exit(EXIT_FAILURE);
    }

    // UDPソケット設定
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(atoi("60600"));
    inet_pton(AF_INET, send_ip.c_str(), &addr.sin_addr);

    // ソケット最適化
    int buf_size = 1024 * 1024;
    setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &buf_size, sizeof(buf_size));

    // 送信スレッド起動
    std::thread sender(udp_sender, sock, addr, pipefd[0]);

    // ctrl+cで終了
    std::signal(SIGINT, [](int) {
        running = false;
        std::cout << "\n終了処理中..." << std::endl;
        kill(pid, SIGTERM);

    });

    // 子プロセス終了を待機
    if (pid > 0) {
        int status;
        waitpid(pid, &status, 0);
        if (WIFEXITED(status)) {
            std::cout << "映像撮影終了" << std::endl;
        } else {
            std::cerr << "映像撮影異常終了" << std::endl;
        }
        running = false;
    }

    // 終了処理
    sender.join();
    if (video_file.is_open()) video_file.close();
    close(sock);
    close(pipefd[0]);
    close(pipefd[1]);
    // kill(pid, SIGTERM);修正した河村
    // concat_ts_files();
    // std::cout << "変換完了: " << (output_dir / "output.mp4").string() << std::endl;
    return 0;
}
