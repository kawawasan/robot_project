// ログ出力のためのクラスの宣言

#ifndef LOG_HPP
#define LOG_HPP

#include <string>
#include <fstream>
#include <mutex>


class Log {
private:
    std::string logName;
    std::ofstream log;
    std::mutex lock;

public:
    Log(const std::string& method, const std::string& log_name, std::chrono::system_clock::time_point time_pref_counter);

    void write(const std::string& msg);
    void write_camn_cn(std::chrono::duration<double> time, std::string event, std::string packet_type, int ack, int seq, int payload_size, std::chrono::system_clock::time_point system_time);
    void write_rn(std::chrono::duration<double> time, std::string event, std::string packet_type, std::string direction, int seq, int payload_size, int video_queue_size);
    void write_generate(std::chrono::duration<double> time, std::string type, int seq, int data_size);
    void write_generate(std::chrono::duration<double> time, std::string type, int seq, int data_size, std::string command);
    void write_command(std::chrono::duration<double> time, std::string event, int seq, std::string command);

    ~Log();


};

#endif // LOG_HPP
