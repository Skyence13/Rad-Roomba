/* rr_chassis_sim - the chassis firmware core on Linux with a plant model.
 *
 *   host link : TCP server (default 127.0.0.1:5550) carrying the CDC byte stream; optional PTY
 *   environment: UDP JSON socket (default 127.0.0.1:5551). Any datagram subscribes its sender to
 *                the 100 Hz ground-truth stream; JSON objects set inputs / inject faults.
 * SIMULATION ONLY.
 */
#define _DEFAULT_SOURCE
#define _XOPEN_SOURCE 600
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#include "sim.h"

static volatile sig_atomic_t g_run = 1;
static void on_sig(int s)
{
    (void)s;
    g_run = 0;
}

static double wall(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static void nonblock(int fd)
{
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
}

#define MAX_SUBS 4

int main(int argc, char **argv)
{
    const char *bind_ip = "127.0.0.1";
    int port = 5550, env_port = 5551, use_pty = 0, quiet = 0;
    double speed = 1.0, duration = 0.0;
    unsigned long long seed = 1;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i], *v = (i + 1 < argc) ? argv[i + 1] : "";
        if (!strcmp(a, "--port")) { port = atoi(v); i++; }
        else if (!strcmp(a, "--env-port")) { env_port = atoi(v); i++; }
        else if (!strcmp(a, "--bind")) { bind_ip = v; i++; }
        else if (!strcmp(a, "--seed")) { seed = strtoull(v, NULL, 10); i++; }
        else if (!strcmp(a, "--speed")) { speed = atof(v); i++; }
        else if (!strcmp(a, "--duration")) { duration = atof(v); i++; }
        else if (!strcmp(a, "--pty")) { use_pty = 1; }
        else if (!strcmp(a, "--quiet")) { quiet = 1; }
        else {
            fprintf(stderr,
                    "usage: rr_chassis_sim [--port 5550] [--env-port 5551] [--bind 127.0.0.1] [--seed N]\n"
                    "                      [--speed X] (simulated/real time ratio, default 1) [--duration S] (simulated s, 0 = forever)\n"
                    "                      [--pty] (also offer the link on a pseudo-terminal) [--quiet]\n");
            return 2;
        }
    }
    if (speed <= 0.0 || speed > 200.0) {
        fprintf(stderr, "--speed must be in (0, 200]\n");
        return 2;
    }
    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);
    signal(SIGPIPE, SIG_IGN);

    static sim_t sim;
    sim_init(&sim, seed);

    struct sockaddr_in sa = {0};
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = inet_addr(bind_ip);
    int one = 1;
    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    sa.sin_port = htons((uint16_t)port);
    if (bind(lfd, (struct sockaddr *)&sa, sizeof sa) != 0 || listen(lfd, 1) != 0) {
        perror("tcp bind/listen");
        return 1;
    }
    nonblock(lfd);
    int ufd = socket(AF_INET, SOCK_DGRAM, 0);
    sa.sin_port = htons((uint16_t)env_port);
    if (bind(ufd, (struct sockaddr *)&sa, sizeof sa) != 0) {
        perror("udp bind");
        return 1;
    }
    nonblock(ufd);
    int pfd = -1;
    if (use_pty) {
        pfd = posix_openpt(O_RDWR | O_NOCTTY);
        if (pfd < 0 || grantpt(pfd) != 0 || unlockpt(pfd) != 0) {
            perror("pty");
            return 1;
        }
        struct termios tio;
        tcgetattr(pfd, &tio);
        cfmakeraw(&tio);
        tcsetattr(pfd, TCSANOW, &tio);
        nonblock(pfd);
        printf("rr_chassis_sim: pty %s\n", ptsname(pfd));
    }
    printf("rr_chassis_sim: %s%s, link tcp %s:%d, env udp %s:%d, seed %llu, speed %.2f, boot_id %s\n", RRCH_FW_VERSION, RRCH_FW_SUFFIX, bind_ip, port,
           bind_ip, env_port, seed, speed, sim.core.boot_id);
    fflush(stdout);

    int cfd = -1;
    struct sockaddr_in subs[MAX_SUBS];
    int nsubs = 0;
    double t0 = wall();
    uint64_t t_base = sim.t_us;
    rrch_mode_t last_mode = sim.core.mode;
    uint8_t buf[4096];
    char js[1024];

    while (g_run) {
        /* ---- I/O ---- */
        if (cfd < 0) {
            int fd = accept(lfd, NULL, NULL);
            if (fd >= 0) {
                cfd = fd;
                nonblock(cfd);
                setsockopt(cfd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
                if (!quiet) {
                    printf("[%10.3f] host connected\n", (double)sim.t_us * 1e-6);
                }
            }
        } else {
            int fd = accept(lfd, NULL, NULL); /* a new client replaces the old one */
            if (fd >= 0) {
                close(cfd);
                cfd = fd;
                nonblock(cfd);
                setsockopt(cfd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
            }
            ssize_t n = recv(cfd, buf, sizeof buf, 0);
            if (n > 0) {
                sim_host_write(&sim, buf, (size_t)n);
            } else if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK)) {
                close(cfd);
                cfd = -1;
                if (!quiet) {
                    printf("[%10.3f] host disconnected\n", (double)sim.t_us * 1e-6);
                }
            }
        }
        if (pfd >= 0) {
            ssize_t n = read(pfd, buf, sizeof buf);
            if (n > 0) {
                sim_host_write(&sim, buf, (size_t)n);
            }
        }
        for (;;) {
            struct sockaddr_in from;
            socklen_t fl = sizeof from;
            ssize_t n = recvfrom(ufd, js, sizeof js, 0, (struct sockaddr *)&from, &fl);
            if (n <= 0) {
                break;
            }
            int known = 0;
            for (int k = 0; k < nsubs; k++) {
                known |= subs[k].sin_port == from.sin_port && subs[k].sin_addr.s_addr == from.sin_addr.s_addr;
            }
            if (!known) {
                if (nsubs < MAX_SUBS) {
                    subs[nsubs++] = from;
                } else {
                    memmove(&subs[0], &subs[1], sizeof subs[0] * (MAX_SUBS - 1));
                    subs[MAX_SUBS - 1] = from;
                }
            }
            bool ok = sim_env_apply(&sim, js, (size_t)n);
            const char *ack = ok ? "{\"type\":\"ACK\",\"ok\":true}" : "{\"type\":\"ACK\",\"ok\":false}";
            sendto(ufd, ack, strlen(ack), 0, (struct sockaddr *)&from, fl);
        }

        /* ---- simulated time ---- */
        double target = (wall() - t0) * speed * 1e6 + (double)t_base;
        int steps = 0;
        while ((double)sim.t_us + 1000.0 <= target && steps < 100) {
            sim_step_ms(&sim);
            steps++;
            if ((sim.t_us / 1000u) % 10u == 0u && nsubs > 0) {
                size_t n = sim_truth_json(&sim, js, sizeof js);
                for (int k = 0; k < nsubs; k++) {
                    sendto(ufd, js, n, 0, (struct sockaddr *)&subs[k], sizeof subs[k]);
                }
            }
            if (sim.core.mode != last_mode) {
                if (!quiet) {
                    printf("[%10.3f] mode %s -> %s\n", (double)sim.t_us * 1e-6, rrch_mode_names[last_mode], rrch_mode_names[sim.core.mode]);
                    fflush(stdout);
                }
                last_mode = sim.core.mode;
            }
            size_t n;
            while ((n = sim_host_read(&sim, buf, sizeof buf)) > 0) {
                if (cfd >= 0) {
                    (void)!send(cfd, buf, n, 0);
                }
                if (pfd >= 0) {
                    (void)!write(pfd, buf, n);
                }
            }
        }
        if (steps == 100) { /* fell behind (debugger, load): do not try to catch up */
            t0 = wall();
            t_base = sim.t_us;
        }
        if (duration > 0.0 && (double)sim.t_us * 1e-6 >= duration) {
            break;
        }
        fd_set rf;
        FD_ZERO(&rf);
        int mx = ufd;
        FD_SET(ufd, &rf);
        if (cfd >= 0) {
            FD_SET(cfd, &rf);
            mx = cfd > mx ? cfd : mx;
        } else {
            FD_SET(lfd, &rf);
            mx = lfd > mx ? lfd : mx;
        }
        if (pfd >= 0) {
            FD_SET(pfd, &rf);
            mx = pfd > mx ? pfd : mx;
        }
        struct timeval tv = {0, (suseconds_t)(speed >= 2.0 ? 200 : 500)};
        select(mx + 1, &rf, NULL, NULL, &tv);
    }
    printf("rr_chassis_sim: stopped at t=%.3f s, pose x=%.4f y=%.4f yaw=%.4f, %u watchdog strobes, %u MCU resets\n", (double)sim.t_us * 1e-6, sim.x, sim.y,
           sim.yaw, sim.n_strobes, sim.n_resets);
    return 0;
}
