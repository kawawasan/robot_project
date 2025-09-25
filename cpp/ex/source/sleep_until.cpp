// sleep_untilの使い方を確認

#include <iostream>
#include <chrono>
#include <thread>

int main() {
    int a = 0;
    std::cout << "start" << std::endl;
    // 時間計測
    auto start = std::chrono::system_clock::now();

    for (int i = 0; i < 4000000000; i++) {
        a++;
    }

    auto end = std::chrono::system_clock::now();
    auto dur = end - start;
    std::cout << "duration = " << std::chrono::duration_cast<std::chrono::milliseconds>(dur).count() << "ms" << std::endl;
    
    std::this_thread::sleep_until(start + std::chrono::seconds(1));
    end = std::chrono::system_clock::now();
    dur = end - start;
    std::cout << "end" << std::endl;
    std::cout << "duration = " << std::chrono::duration_cast<std::chrono::milliseconds>(dur).count() << "ms" << std::endl;
    std::cout << "a = " << a << std::endl;
    return 0;
}
