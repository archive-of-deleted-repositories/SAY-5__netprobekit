// target.c — minimal simulated DUT.
//
// Speaks line-delimited JSON over TCP. Designed to be compiled with
// just `cc -O2 -o target target.c` — no libraries, no build system.
// Stays under ~400 lines so it's readable in one sitting.

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static const char *FIRMWARE_VERSION = "1.4.2";
static const char *EXPECTED_FIRMWARE_CRC = "0xa5b3c1d7";

// Sensors: id, simulated stable value, simulated jitter
typedef struct { const char *id; double base; double jitter; } sensor_t;
static sensor_t SENSORS[] = {
    { "tempC0", 23.5, 0.4 },
    { "tempC1", 24.1, 0.4 },
    { "vbat",   12.3, 0.05 },
    { "imu_g",   9.81, 0.02 },
};
static const int NSENS = sizeof(SENSORS)/sizeof(SENSORS[0]);

// Crude CRC32 — just enough to give the integrity check something
// that matches across both sides.
static unsigned crc32(const unsigned char *buf, size_t n) {
    unsigned c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) {
        c ^= buf[i];
        for (int j = 0; j < 8; ++j) c = (c >> 1) ^ (0xEDB88320u & -(c & 1));
    }
    return ~c;
}

// Splits a JSON-line "OP" + key/value pairs. Tiny, opinionated parser
// — we don't accept arbitrary JSON, only the request envelopes we
// ourselves define. That makes the parser ~30 lines of pure ASCII work.
typedef struct {
    char op[32];
    long n;
    long seed;
    long id;
    double valf;
    char idstr[64];
    long addr, len;
} req_t;

static int parse_req(const char *line, req_t *r) {
    memset(r, 0, sizeof(*r));
    const char *p = strstr(line, "\"op\":\"");
    if (!p) return 0;
    p += 6;
    int i = 0;
    while (*p && *p != '"' && i < 31) r->op[i++] = *p++;
    r->op[i] = 0;
    const char *kn = strstr(line, "\"n\":");
    if (kn) r->n = strtol(kn + 4, NULL, 10);
    const char *ks = strstr(line, "\"seed\":");
    if (ks) r->seed = strtol(ks + 7, NULL, 10);
    const char *kid = strstr(line, "\"id\":\"");
    if (kid) {
        kid += 6; int j = 0;
        while (*kid && *kid != '"' && j < 63) r->idstr[j++] = *kid++;
        r->idstr[j] = 0;
    }
    const char *kaddr = strstr(line, "\"addr\":");
    if (kaddr) r->addr = strtol(kaddr + 7, NULL, 10);
    const char *klen = strstr(line, "\"len\":");
    if (klen) r->len = strtol(klen + 6, NULL, 10);
    return 1;
}

static void send_line(int fd, const char *s) {
    size_t n = strlen(s);
    write(fd, s, n);
    if (n == 0 || s[n-1] != '\n') write(fd, "\n", 1);
}

static void handle(int fd) {
    char buf[8192];
    ssize_t got = recv(fd, buf, sizeof(buf) - 1, 0);
    if (got <= 0) return;
    buf[got] = 0;

    req_t r;
    if (!parse_req(buf, &r)) {
        send_line(fd, "{\"ok\":false,\"err\":\"parse\"}");
        return;
    }
    char out[16384];

    if (!strcmp(r.op, "ping")) {
        snprintf(out, sizeof(out), "{\"ok\":true,\"pong\":\"%s\"}", FIRMWARE_VERSION);
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "firmware_version")) {
        snprintf(out, sizeof(out),
            "{\"ok\":true,\"version\":\"%s\",\"crc\":\"%s\"}",
            FIRMWARE_VERSION, EXPECTED_FIRMWARE_CRC);
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "throughput")) {
        // Echo n bytes back as the body of a response.
        long n = r.n > 0 ? r.n : 1024;
        if (n > 1 << 20) n = 1 << 20;
        // Header
        char hdr[128];
        snprintf(hdr, sizeof(hdr), "{\"ok\":true,\"bytes\":%ld,\"payload\":\"", n);
        write(fd, hdr, strlen(hdr));
        // Body — deterministic bytes derived from the seed.
        unsigned long seed = r.seed ? (unsigned long)r.seed : 0xdeadbeef;
        char chunk[256];
        long sent = 0;
        while (sent < n) {
            for (size_t i = 0; i < sizeof(chunk); ++i) {
                seed = seed * 6364136223846793005UL + 1442695040888963407UL;
                unsigned v = (unsigned)(seed >> 33) & 0x3F;
                chunk[i] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"[v];
            }
            long w = (n - sent < (long)sizeof(chunk)) ? n - sent : (long)sizeof(chunk);
            write(fd, chunk, (size_t)w);
            sent += w;
        }
        send_line(fd, "\"}");
        return;
    }
    if (!strcmp(r.op, "integrity")) {
        long n = r.n > 0 ? r.n : 256;
        if (n > 1 << 16) n = 1 << 16;
        unsigned long seed = r.seed ? (unsigned long)r.seed : 0xa5a5a5a5;
        unsigned char *buf2 = malloc((size_t)n);
        for (long i = 0; i < n; ++i) {
            seed = seed * 6364136223846793005UL + 1442695040888963407UL;
            buf2[i] = (unsigned char)(seed >> 33);
        }
        unsigned crc = crc32(buf2, (size_t)n);
        free(buf2);
        snprintf(out, sizeof(out),
            "{\"ok\":true,\"bytes\":%ld,\"seed\":%ld,\"crc\":%u}",
            n, r.seed, crc);
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "can_read_frames")) {
        long n = r.n > 0 ? r.n : 4;
        if (n > 32) n = 32;
        char *p = out;
        p += sprintf(p, "{\"ok\":true,\"frames\":[");
        for (long i = 0; i < n; ++i) {
            unsigned can_id = 0x100 + (unsigned)i;
            // 8 bytes simulated frame data.
            p += sprintf(p, "%s{\"id\":%u,\"dlc\":8,\"data\":[%u,%u,%u,%u,%u,%u,%u,%u]}",
                i ? "," : "", can_id,
                (unsigned)i & 0xff, ((unsigned)i >> 1) & 0xff,
                ((unsigned)i + 7) & 0xff, ((unsigned)i + 13) & 0xff,
                ((unsigned)i * 3) & 0xff, ((unsigned)i * 5) & 0xff,
                ((unsigned)i * 7) & 0xff, ((unsigned)i * 11) & 0xff);
        }
        sprintf(p, "]}");
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "can_tx")) {
        snprintf(out, sizeof(out), "{\"ok\":true,\"tx_id\":%ld,\"acked\":true}", r.id);
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "sensor_read")) {
        for (int i = 0; i < NSENS; ++i) {
            if (!strcmp(SENSORS[i].id, r.idstr)) {
                struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
                double j = ((double)(ts.tv_nsec % 1000) / 500.0 - 1.0) * SENSORS[i].jitter;
                snprintf(out, sizeof(out),
                    "{\"ok\":true,\"id\":\"%s\",\"value\":%.4f,\"unit\":\"x\"}",
                    SENSORS[i].id, SENSORS[i].base + j);
                send_line(fd, out);
                return;
            }
        }
        snprintf(out, sizeof(out), "{\"ok\":false,\"err\":\"unknown sensor %s\"}", r.idstr);
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "sensor_history")) {
        const sensor_t *s = NULL;
        for (int i = 0; i < NSENS; ++i)
            if (!strcmp(SENSORS[i].id, r.idstr)) { s = &SENSORS[i]; break; }
        if (!s) { send_line(fd, "{\"ok\":false,\"err\":\"unknown sensor\"}"); return; }
        char *p = out;
        p += sprintf(p, "{\"ok\":true,\"id\":\"%s\",\"values\":[", s->id);
        // Deterministic 100-sample history.
        unsigned long seed = (unsigned long)(s->base * 1000.0);
        for (int i = 0; i < 100; ++i) {
            seed = seed * 6364136223846793005UL + 1442695040888963407UL;
            double j = ((double)((seed >> 33) % 1000) / 500.0 - 1.0) * s->jitter;
            p += sprintf(p, "%s%.4f", i ? "," : "", s->base + j);
        }
        sprintf(p, "]}");
        send_line(fd, out);
        return;
    }
    if (!strcmp(r.op, "flash_region")) {
        unsigned char buf2[256];
        for (long i = 0; i < (r.len < 256 ? r.len : 256); ++i)
            buf2[i] = (unsigned char)((r.addr + i) ^ 0x5a);
        unsigned crc = crc32(buf2, (size_t)(r.len < 256 ? r.len : 256));
        snprintf(out, sizeof(out),
            "{\"ok\":true,\"addr\":%ld,\"len\":%ld,\"crc\":%u}",
            r.addr, r.len, crc);
        send_line(fd, out);
        return;
    }

    snprintf(out, sizeof(out), "{\"ok\":false,\"err\":\"unknown op '%s'\"}", r.op);
    send_line(fd, out);
}

int main(int argc, char **argv) {
    int port = 9999;
    if (argc > 1) port = atoi(argv[1]);
    signal(SIGPIPE, SIG_IGN);

    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) { perror("socket"); return 1; }
    int yes = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons((uint16_t)port);
    if (bind(s, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); return 1; }
    if (listen(s, 16) < 0) { perror("listen"); return 1; }

    fprintf(stderr, "target listening :%d (firmware %s)\n", port, FIRMWARE_VERSION);
    for (;;) {
        int c = accept(s, NULL, NULL);
        if (c < 0) continue;
        handle(c);
        close(c);
    }
    return 0;
}
