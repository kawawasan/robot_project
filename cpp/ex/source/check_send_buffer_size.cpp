// 送信バッファのサイズを確認する

#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

int main() {
    int sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
    int sndbuf_size;
    socklen_t optlen = sizeof(sndbuf_size);

    // デフォルトの送信バッファサイズを取得
    getsockopt(sock_fd, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, &optlen);
    std::cout << "Default send buffer size: " << sndbuf_size << std::endl;

    // バッファサイズを変更
    sndbuf_size = 1024 * 1024;  // 1MB
    setsockopt(sock_fd, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, sizeof(sndbuf_size));
    getsockopt(sock_fd, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, &optlen);
    std::cout << "Changed send buffer size to 1MB: " << sndbuf_size << std::endl;
    

    sndbuf_size = 1024 * 1024 * 10;  // 10MB
    setsockopt(sock_fd, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, sizeof(sndbuf_size));
    getsockopt(sock_fd, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, &optlen);
    std::cout << "Changed send buffer size to 10MB: " << sndbuf_size << std::endl;

    return 0;
}
