#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <iostream>
#include <fstream>
#include <cstring>
#include <csignal>
#include <ctime>
#include <filesystem>

namespace fs = std::filesystem;

#define BUFFER_SIZE 1316  // MTUサイズ
#define PORT 60600

std::ofstream output_file;
int sockfd;
char file_prefix[64];

void signal_handler(int sig) {
    std::cout << "\n終了処理中..." << std::endl;
    output_file.close();
    close(sockfd);

    // .tsファイルをmp4に変換
    std::string command = "ffmpeg -i videos/" + std::string(file_prefix) + ".ts" + " -c copy " + "videos/output_" + std::string(file_prefix) + ".mp4 " + "-loglevel fatal";
    std::system(command.c_str());
    std::cout << "FFmpegコマンド: " << command << std::endl;
    std::cout << "変換完了: " << "videos/output_" << file_prefix << ".mp4" << std::endl;

    exit(0);
}

int main(int argc, char *argv[]) {
    // シグナルハンドラ設定
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // 引数チェック
    if (argc < 2 || argc > 3) {
        std::cerr << "Usage: " << argv[0] << " [自身のIP] [映像保存名(なしで実行日時)]" << std::endl;
        return 1;
    }
    std::string my_ip = argv[1];  // 自身のIPアドレス
    std::cout << "自身のIPアドレス: " << my_ip << std::endl;
    if (argc >= 3) {
        std::strncpy(file_prefix, argv[2], sizeof(file_prefix) - 1);
        file_prefix[sizeof(file_prefix) - 1] = '\0'; // Ensure null termination
    } else {
        auto t = std::time(nullptr);
        auto tm = *std::localtime(&t);
        std::strftime(file_prefix, sizeof(file_prefix), "%Y%m%d_%H%M%S", &tm);
    }
    std::string filename = "videos/" + std::string(file_prefix) + ".ts";
    std::cout << "映像保存名: " << filename << std::endl;

    // ソケット作成
    if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
        std::cerr << "ソケット作成失敗" << std::endl;
        return 1;
    }

    // アドレス設定
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = inet_addr(my_ip.c_str());
    server_addr.sin_port = htons(PORT);

    // バインド
    if (bind(sockfd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "バインド失敗" << std::endl;
        return 1;
    }

    // ファイルオープン
    fs::path dir = fs::current_path() / "videos";
    if (!fs::exists(dir)) {
        fs::create_directory(dir);
    }
    output_file.open(filename, std::ios::binary);
    if (!output_file.is_open()) {
        std::cerr << "ファイルオープン失敗" << std::endl;
        return 1;
    }

    // 受信ループ
    char buffer[BUFFER_SIZE];
    std::cout << "受信開始... (Ctrl+Cで終了)" << std::endl;

    while (true) {
        ssize_t len = recv(sockfd, buffer, BUFFER_SIZE, 0);
        if (len < 0) {
            std::cerr << "受信エラー" << std::endl;
            continue;
        }

        // TSデータ書き込み
        output_file.write(buffer, len);
        output_file.flush();

        // std::cout << "受信パケット: " << len << "バイト" << std::endl;
    }

    return 0;
}
