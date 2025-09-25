// ソケットに優先度を設定する例

#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

int main() {
    int sock_fd = socket(AF_INET, SOCK_DGRAM, 0);

    // デフォルトの優先度を取得
    int default_priority;
    socklen_t optlen = sizeof(default_priority);
    if (getsockopt(sock_fd, SOL_SOCKET, SO_PRIORITY, &default_priority, &optlen) < 0) {
        std::cerr << "Failed to get default socket priority" << std::endl;
        return -1;
    }
    std::cout << "Default socket priority: " << default_priority << std::endl;

    // 優先度を設定
    int priority = 6;  // 優先度を設定（0-7の範囲）
    if (setsockopt(sock_fd, SOL_SOCKET, SO_PRIORITY, &priority, sizeof(priority)) < 0) {
        std::cerr << "Failed to set socket priority" << std::endl;
        return -1;
    }
    // 設定した優先度を確認
    int new_priority;
    if (getsockopt(sock_fd, SOL_SOCKET, SO_PRIORITY, &new_priority, &optlen) < 0) {
        std::cerr << "Failed to get new socket priority" << std::endl;
        return -1;
    }
    std::cout << "New socket priority: " << new_priority << std::endl;

    return 0;
}
