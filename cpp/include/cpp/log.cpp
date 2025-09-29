// ログ出力のためのクラスの実装  C++17以降

#include "../header/log.hpp"
#include <iostream>
#include <ctime>
#include <iomanip>
#include <sstream>
#include <mutex>
#include <chrono>
#include <sys/stat.h>
#include <filesystem>

using std::cout;
using std::endl;


using hr_clock = std::chrono::high_resolution_clock;
using system_clock = std::chrono::system_clock;


Log::Log(const std::string& method, const std::string& log_name, system_clock::time_point time_pref_counter) {
    // logディレクトリがない時，作成
    std::string logDir = "log/";
    if (!(std::filesystem::exists(logDir))) {
        cout << "make log directory" << endl;
        mkdir("log", 0755);  // 0755: owner rwx, group rx, others rx
    }
    // ファイル名: method_num.log
    logName = logDir + method + "_" + log_name + ".log";
    std::cout << "log file: " << logName << std::endl;

    // ファイルが既に存在している場合，上書きすることを知らせる
    if (std::filesystem::exists(logName)) {
        cout << "the log file is already exists so overwrite" << endl;
    }

    // ファイルを開いて日時を書き込む ファイルが存在しても新規作成
    log.open(logName, std::ios::out | std::ios::trunc);
    if (log.is_open()) {
        std::time_t start_date = system_clock::to_time_t(time_pref_counter);
        std::tm* start_date_tm = std::localtime(&start_date);
        log << method << "_" << std::put_time(start_date_tm, "%Y-%m-%d_%H-%M-%S") << ".log" << std::endl;
        log << "Time= 0 time_pref_counter= " << time_pref_counter.time_since_epoch().count() << std::endl;  // 時刻同期ズレのためのカウンタ
        // log.close();
    }
}

void Log::write(const std::string& msg) {
    lock.lock();
    // log.open(logName, std::ios::out | std::ios::app);
    if (log.is_open()) {
        log << msg << std::endl;
        // log.close();
    }
    lock.unlock();
}

void Log::write_camn_cn(std::chrono::duration<double> time, std::string event, std::string packet_type, int ack, int seq, int payload_size, system_clock::time_point system_time) {
    std::string log_message = 
    "T= " + std::to_string(time.count()) + 
    " Ev= " + event +
    " Type= " + packet_type +
    " ACK= " + std::to_string(ack) +
    " Seq= " + std::to_string(seq) +
    " PayloadSize= " + std::to_string(payload_size) +
    " SystemTime= " + std::to_string(system_time.time_since_epoch().count());

    write(log_message);
}

void Log::write_rn(std::chrono::duration<double> time, std::string event, std::string packet_type, std::string direction, int seq, int payload_size, int video_queue_size) {
    std::string log_message = 
    "T= " + std::to_string(time.count()) +
    " Ev= " + event +
    " Type= " + packet_type +
    " Direction= " + direction +
    " Seq= " + std::to_string(seq) +
    " PayloadSize= " + std::to_string(payload_size) +
    " VideoQueueSize= " + std::to_string(video_queue_size);

    write(log_message);
}

// video用(コマンド内容を書き込まないバージョン)
void Log::write_generate(std::chrono::duration<double> time, std::string type, int seq, int data_size) {
    // time_pointをdurationに変換
    std::string log_message = 
    "T= " + std::to_string(time.count()) +
    " Ev= Generate_" + type +
    " Seq= " + std::to_string(seq) + 
    " PacketBytes= " + std::to_string(data_size);

    write(log_message);
}

// command用(コマンド内容もログに書き込むバージョン)
void Log::write_generate(std::chrono::duration<double> time, std::string type, int seq, int data_size, std::string command) {
    // time_pointをdurationに変換
    std::string log_message = 
    "T= " + std::to_string(time.count()) +
    " Ev= Generate_" + type +
    " Seq= " + std::to_string(seq) + 
    " PacketBytes= " + std::to_string(data_size) +
    " Command= \"" + command + "\"";

    write(log_message);
}

void Log::write_command(std::chrono::duration<double> time, std::string event, int seq, std::string command) {
    std::string log_message = 
    "T= " + std::to_string(time.count()) +
    " Ev= " + event +
    " Seq= " + std::to_string(seq) +
    " Command= \"" + command + "\"";

    write(log_message);
}

Log::~Log() {
    if (log.is_open()) {
        log.close();
    }
    std::cout << "log file closed" << std::endl;
}

// CamN
// T= 1.003652530 Ev= Generate_Video Seq= 0 PacketBytes= 156250 Elapsed_Time= 0
// T= 1.005334860 Ev= Send Type= DUMMY ACK= -1 Seq= 0 PacketBytes= 4 TransmissionTime= 1739286713519813570 
// T= 1.007819737 Ev= Send Type= VIDEO Seq= 0 PacketBytes= 1464 TransmissionTime= 1739286713522298447
// T= 1.032877928 Ev= Recv Type= CONTROL ACK= -1 Seq= 0 PacketBytes= 64 ReceivedTime= 173928671354735663PacketBytes

// RN
// T= 1.008923 Ev= Recv Type= DUMMY Direction= Down ACK= 0 Seq= 0 PacketBytes= 4 Video_Queue_Size= 0 Command_Queue_Size= 0
// T= 1.010772 Ev= Send Type= DUMMY Direction= Down Seq= 0 PacketBytes= 4 Video_Queue_Size= 0
// T= 1.013882 Ev= Recv Type= VIDEO Direction= Down ACK= 0 Seq= 0 PacketBytes= 1464 Video_Queue_Size= 1 Command_Queue_Size= 0
// T= 1.014712 Ev= Send Type= VIDEO Direction= Down Seq= 0 PacketBytes= 1500 Video_Queue_Size= 0
// T= 1.032866 Ev= Recv Type= CONTROL Direction= Down ACK= 0 Seq= 0 PacketBytes= 64 Video_Queue_Size= 0 Command_Queue_Size= 1
// T= 1.035183 Ev= Send Type= CONTROL Direction= Up Seq= 0 PacketBytes= 64 Command_Queue_Size= 0
// T= 1.035454 Ev= Send Type= CONTROL Direction= Down Seq= 0 PacketBytes= 64 Video_Queue_Size= 1
// T= 2.040965124 Ev= Video_Packet_Drop Type= VIDEO Direction= Down ACK= 0 Seq= 497 PacketBytes= 1456 Video_Queue_Size= 9

// CN
// T= 1.011183113 Ev= Recv Type= DUMMY ACK= -1 Seq= 0 PacketBytes= 4 ReceivedTime= 1739286713525123064
// T= 1.015442246 Ev= Generate_Command Seq= 0 PacketBytes= 60 Elapsed_Time= 0
// T= 1.023954522 Ev= Recv Type= VIDEO ACK= 0 Seq= 1 PacketBytes= 1500 ReceivedTime= 1739286713537894473
// T= 1.024525611 Ev= Send Type= CONTROL ACK= -1 Seq= 0 PacketBytes= 64 TransmissionTime= 1739286713538465562



// 使用例
    // int main() {
    //     // 使用例
    //     Log logger("example", 1);
    //     logger.write("This is a test message.");
    //     return 0;
    // }