// sleepによるマルチスレッドのへの影響を確認

#include <iostream>
#include <thread>
#include <chrono>


using std::cout;
using std::endl;

void func1() {
    auto start = std::chrono::system_clock::now();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    std::cout << "func1" << std::endl;
    auto end = std::chrono::system_clock::now();
    auto dur = end - start;
    cout << "duration = " << std::chrono::duration_cast<std::chrono::milliseconds>(dur).count() << "ms" << endl;
}

void func2() {
    auto start = std::chrono::system_clock::now();
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
    std::cout << "func2" << std::endl;
    auto end = std::chrono::system_clock::now();
    auto dur = end - start;
    cout << "duration = " << std::chrono::duration_cast<std::chrono::milliseconds>(dur).count() << "ms" << endl;
}

int main() {
    std::thread th1(func1);
    std::thread th2(func2);

    // 時間計測
    auto start = std::chrono::system_clock::now();

    th1.join();
    th2.join();

    auto end = std::chrono::system_clock::now();
    auto dur = end - start;
    cout << "duration = " << std::chrono::duration_cast<std::chrono::milliseconds>(dur).count() << "ms" << endl;

    return 0;
}
