// 各スリープ機能の精度を確認するためのプログラム

#include <iostream>
#include <chrono>
#include <time.h>
#include <unistd.h>
#include <thread>
#include <iomanip>

using std::cout;
using std::endl;
using hr_clock = std::chrono::high_resolution_clock;


int main() {
    double sleep_time = 0.001;  // 1ms
    cout << "Sleeping for " << sleep_time << " seconds." << endl;
    hr_clock::time_point start_time = hr_clock::now();
    hr_clock::time_point end_time;
    // hr_clock::duration<double> elapsed_time;

    cout << "sleep()" << endl;
    for (int i = 0; i < 3; i++) {
        start_time = hr_clock::now();

        sleep(sleep_time);

        end_time = hr_clock::now();
        auto elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(end_time - start_time);
        cout << "Sleep time: " << std::fixed << std::setprecision(6) << elapsed_time.count() << " seconds." << endl;
    }
    cout << endl;

    cout << "usleep()" << endl;
    for (int i = 0; i < 3; i++) {
        start_time = hr_clock::now();

        usleep(sleep_time * 1e6);

        end_time = hr_clock::now();
        auto elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(end_time - start_time);
        cout << "Sleep time: " << std::fixed <<std::setprecision(6) << elapsed_time.count() << " seconds." << endl;
    }
    cout << endl;

    cout << "nanosleep()" << endl;
    for (int i = 0; i < 3; i++) {
        struct timespec ts;
        ts.tv_sec = 0;
        ts.tv_nsec = sleep_time * 1e9;
        start_time = hr_clock::now();

        nanosleep(&ts, NULL);

        end_time = hr_clock::now();
        auto elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(end_time - start_time);
        cout << "Sleep time: " << std::fixed <<std::setprecision(6) << elapsed_time.count() << " seconds." << endl;
    }
    cout << endl;

    cout << "clock_nanosleep()" << endl;
    for (int i = 0; i < 3; i++) {
        struct timespec ts;
        ts.tv_sec = 0;
        ts.tv_nsec = sleep_time * 1e9;
        start_time = hr_clock::now();

        clock_nanosleep(CLOCK_MONOTONIC, 0, &ts, NULL);

        end_time = hr_clock::now();
        auto elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(end_time - start_time);
        cout << "Sleep time: " << std::fixed <<std::setprecision(6) << elapsed_time.count() << " seconds." << endl;
    }
    cout << endl;

    cout << "std::this_thread::sleep_for()" << endl;
    for (int i = 0; i < 3; i++) {
        start_time = hr_clock::now();

        std::this_thread::sleep_for(std::chrono::duration<double>(sleep_time));
        
        end_time = hr_clock::now();
        auto elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(end_time - start_time);
        cout << "Sleep time: " << std::fixed <<std::setprecision(6) << elapsed_time.count() << " seconds." << endl;
    }
    cout << endl;

    cout << "while loop" << endl;
    for (int i = 0; i < 3; i++) {
        hr_clock::time_point sleep_start_time = hr_clock::now();
        hr_clock::time_point sleep_end_time;
        std::chrono::duration<double> sleep_elapsed_time;

        start_time = hr_clock::now();
        while (true) {
            sleep_end_time = hr_clock::now();
            sleep_elapsed_time = sleep_end_time - sleep_start_time;
            if (sleep_elapsed_time.count() > sleep_time) {
                break;
            }
        }

        end_time = hr_clock::now();
        auto elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(end_time - start_time);
        cout << "Sleep time: " << std::fixed <<std::setprecision(6) << elapsed_time.count() << " seconds." << endl;
    }

    return 0;
}
