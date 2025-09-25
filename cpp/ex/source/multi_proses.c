#include <sys/param.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <netdb.h>

#include <ctype.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sysexits.h>
#include <unistd.h>
#include <time.h>

void send_recv_loop(int);
void plot_dot();
void event_process();
void recv_loop(int);
void accept_loop(int);
int server_socket(const char *);

/* サーバソケットの作成 */
int server_socket(const char *portnm) {
    char nbuf[NI_MAXHOST], sbuf[NI_MAXSERV];
    struct addrinfo hints, *res0;
    int soc, opt, errcode;
    socklen_t opt_len;

    (void) memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_PASSIVE;

    if ((errcode = getaddrinfo(NULL, portnm, &hints, &res0)) != 0 ) {
        (void) fprintf(stderr, "getaddrinfo():%s\n", gai_strerror(errcode));
        return -1;
    }
    if ((errcode = getnameinfo(res0->ai_addr, res0->ai_addrlen, nbuf, sizeof(nbuf), sbuf, sizeof(sbuf), NI_NUMERICHOST | NI_NUMERICSERV)) != 0) {
        (void) fprintf(stderr, "getnameinfo():%s\n", gai_strerror(errcode));
        freeaddrinfo(res0);
        return -1;
    }

    if ((soc = socket(res0->ai_family, res0->ai_socktype, res0->ai_protocol)) == -1) {
        perror("socket");
        freeaddrinfo(res0);
        return -1;
    }

    /* ソケットオプション（再利用フラグ）設定 */
    opt = 1;
    opt_len = sizeof(opt);
    if (setsockopt(soc, SOL_SOCKET, SO_REUSEADDR, &opt, opt_len) == -1) {
        perror("setsockopt");
        (void) close(soc);
        freeaddrinfo(res0);
        return -1;
    }

    if (bind(soc, res0->ai_addr, res0->ai_addrlen) == -1) {
        perror("bind");
        (void) close(soc);
        freeaddrinfo(res0);
        return -1;
    }

    if (listen(soc, SOMAXCONN) == -1) {
        perror("listen");
        (void) close(soc);
        freeaddrinfo(res0);
        return -1;
    }
    freeaddrinfo(res0);
    return (soc);
}


void accept_loop(int soc) {
    char hbuf[NI_MAXHOST], sbuf[NI_MAXSERV];
    struct sockaddr_storage from;
    int acc, status;
    pid_t pid;
    socklen_t len;

    for (;;) {
        len = (socklen_t) sizeof(from);
        if ((acc = accept(soc, (struct sockaddr *) &from, &len)) == -1) {
            if (errno != EINTR) {
                perror("accept");
            }
        } else {
            (void) getnameinfo((struct sockaddr *) &from, len, hbuf, sizeof(hbuf), sbuf, sizeof(sbuf), NI_NUMERICHOST | NI_NUMERICSERV);
            if ((pid = fork()) == 0) {
                /* 子プロセス */
                recv_loop(acc);
                (void) close(acc);
                _exit(1); // 子プロセス終了。exit()とは違って全体が終了するわけではない
            } else if (pid > 0) {
                /* 親プロセス */
                (void) close(acc);
                acc = -1;
                plot_dot();
            } else {
                perror("fork"); // リソース不足とか？
                (void) close(acc);
                acc = -1;
            }
        }
    }
}



void recv_loop(int acc) {
    char buf[512];
    ssize_t len;

    for (;;) {
        if ((len = recv(acc, buf, sizeof(buf), 0)) == -1) {
            perror("recv");
            break;
        }
        if (len == 0) {
            (void) fprintf(stderr, "<%d>recv:EOF\n", getpid());
            break;
        }
        event_process();
    }

}

void plot_dot() {
    for (;;) {
        // 時間計測
        time_t start_t = time(NULL);
        usleep(1000);
        // fprintf(stderr, ".");
        time_t end_t = time(NULL);
        printf("duration = %ld\n", end_t - start_t);
    }
}

void event_process() {
    time_t start_t = time(NULL);
    // fprintf(stderr,"#");
    usleep(1000/3);
    time_t end_t = time(NULL);
    printf("duration = %ld\n", end_t - start_t);
}


/* main関数 */
int main(int argc, char *argv[]) {
    int soc;

    if (argc <= 1) {
        (void) fprintf(stderr, "$ ./test [port number]\n");
        return (EX_USAGE);
    }

    if ((soc = server_socket(argv[1])) == -1) {
        (void) fprintf(stderr, "server_socket(%s): error\n", argv[1]);
        return (EX_UNAVAILABLE);
    }
    (void) fprintf(stderr, "ready for accept\n");

    accept_loop(soc);

    /* ソケットクローズ */
    (void) close(soc);
    return (EX_OK);
}
