// main.c — Pico W: Wi-Fi STA + HTTP :8080 + USB HID
// GET  /ping   -> pong
// GET  /ready  -> ready
// GET  /status -> ready=1;queue=N;wifi=1
// POST /cmd    body examples:
//   press A 200
//   dpad UP 120
//   wait 500
//   combo X Y A B 150
//   macro soft_reset
// POST /reset  -> queues soft_reset macro
//
// Build:
// cmake .. -DPICO_BOARD=pico_w -DWIFI_SSID='"yourssid"' -DWIFI_PASSWORD='"yourpass"'
// cmake --build . -j

#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <ctype.h>
#include <stdio.h>

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include "lwip/tcp.h"
#include "tusb.h"

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

#define HTTP_PORT 8080

// ------------------- LED state -------------------
// Behavior:
// - Wi-Fi connected, idle: LED ON
// - Every command received: LED blinks once
// - After blink: LED OFF until next command
static bool g_wifi_connected = false;
static bool g_led_blink_active = false;
static absolute_time_t g_led_blink_until;

static void led_set_ready(void) {
    if (g_wifi_connected) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
    } else {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
    }
}

static void led_trigger_command_blink(void) {
    g_led_blink_active = true;
    g_led_blink_until = make_timeout_time_ms(120);
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
}

static void led_tick(void) {
    if (g_led_blink_active) {
        if (absolute_time_diff_us(get_absolute_time(), g_led_blink_until) <= 0) {
            g_led_blink_active = false;
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        }
    }
}

// ------------------- Switch HID report (8 bytes) -------------------
typedef struct __attribute__((packed)) {
    uint16_t buttons;
    uint8_t  hat;
    uint8_t  x;
    uint8_t  y;
    uint8_t  z;
    uint8_t  rz;
    uint8_t  vendor;
} switch_report_t;

static switch_report_t g_rpt;

// Hat values
static inline uint8_t hat_neutral(void) { return 0x08; }
static inline uint8_t hat_up(void)      { return 0x00; }
static inline uint8_t hat_right(void)   { return 0x02; }
static inline uint8_t hat_down(void)    { return 0x04; }
static inline uint8_t hat_left(void)    { return 0x06; }

// Button bit mapping
enum {
    BTN_Y      = 1u << 0,
    BTN_B      = 1u << 1,
    BTN_A      = 1u << 2,
    BTN_X      = 1u << 3,
    BTN_L      = 1u << 4,
    BTN_R      = 1u << 5,
    BTN_ZL     = 1u << 6,
    BTN_ZR     = 1u << 7,
    BTN_MINUS  = 1u << 8,
    BTN_PLUS   = 1u << 9,
    BTN_LS     = 1u << 10,
    BTN_RS     = 1u << 11,
    BTN_HOME   = 1u << 12,
    BTN_CAP    = 1u << 13,
};

// ------------------- Action queue -------------------
typedef enum { ACT_PRESS_MASK, ACT_DPAD, ACT_WAIT } action_kind_t;

typedef enum {
    ABTN_A, ABTN_B, ABTN_X, ABTN_Y, ABTN_L, ABTN_R,
    ABTN_ZL, ABTN_ZR, ABTN_PLUS, ABTN_MINUS, ABTN_HOME, ABTN_CAPTURE
} button_t;

typedef enum { DPAD_UP, DPAD_RIGHT, DPAD_DOWN, DPAD_LEFT } dpad_t;

typedef struct {
    action_kind_t kind;
    uint32_t ms;
    union {
        uint16_t button_mask;
        dpad_t dpad;
    };
} action_t;

#define Q_MAX 128
static action_t q[Q_MAX];
static int q_head = 0, q_tail = 0;

static bool q_is_empty(void) { return q_head == q_tail; }
static bool q_is_full(void)  { return ((q_tail + 1) % Q_MAX) == q_head; }
static int q_count(void) {
    if (q_tail >= q_head) return q_tail - q_head;
    return Q_MAX - q_head + q_tail;
}

static bool q_push(action_t a) {
    if (q_is_full()) return false;
    q[q_tail] = a;
    q_tail = (q_tail + 1) % Q_MAX;
    return true;
}

static bool q_pop(action_t* out) {
    if (q_is_empty()) return false;
    *out = q[q_head];
    q_head = (q_head + 1) % Q_MAX;
    return true;
}

static uint16_t map_button(button_t b) {
    switch (b) {
        case ABTN_A: return BTN_A;
        case ABTN_B: return BTN_B;
        case ABTN_X: return BTN_X;
        case ABTN_Y: return BTN_Y;
        case ABTN_L: return BTN_L;
        case ABTN_R: return BTN_R;
        case ABTN_ZL: return BTN_ZL;
        case ABTN_ZR: return BTN_ZR;
        case ABTN_PLUS: return BTN_PLUS;
        case ABTN_MINUS: return BTN_MINUS;
        case ABTN_HOME: return BTN_HOME;
        case ABTN_CAPTURE: return BTN_CAP;
        default: return 0;
    }
}

static uint8_t map_hat(dpad_t d) {
    switch (d) {
        case DPAD_UP: return hat_up();
        case DPAD_RIGHT: return hat_right();
        case DPAD_DOWN: return hat_down();
        case DPAD_LEFT: return hat_left();
        default: return hat_neutral();
    }
}

// ------------------- Macros -------------------
static bool enqueue_soft_reset(void) {
    uint16_t mask =
        map_button(ABTN_X) |
        map_button(ABTN_Y) |
        map_button(ABTN_A) |
        map_button(ABTN_B);

    return q_push((action_t){
        .kind = ACT_PRESS_MASK,
        .ms = 150,
        .button_mask = mask
    });
}

// ------------------- Runner -------------------
typedef struct {
    bool active;
    action_t cur;
    absolute_time_t deadline;
    bool applied;
} runner_t;

static runner_t runner;

static void report_set_neutral(void) {
    g_rpt.buttons = 0;
    g_rpt.hat     = hat_neutral();
    g_rpt.x       = 128;
    g_rpt.y       = 128;
    g_rpt.z       = 128;
    g_rpt.rz      = 128;
    g_rpt.vendor  = 0;
}

static void runner_start(action_t a) {
    runner.active = true;
    runner.cur = a;
    runner.deadline = make_timeout_time_ms((int)a.ms);
    runner.applied = false;
}

static void runner_tick(void) {
    if (!runner.active) return;

    if (!runner.applied) {
        runner.applied = true;

        if (runner.cur.kind == ACT_PRESS_MASK) {
            g_rpt.buttons |= runner.cur.button_mask;
        } else if (runner.cur.kind == ACT_DPAD) {
            g_rpt.hat = map_hat(runner.cur.dpad);
        } else if (runner.cur.kind == ACT_WAIT) {
            // no-op
        }
    }

    if (absolute_time_diff_us(get_absolute_time(), runner.deadline) <= 0) {
        if (runner.cur.kind == ACT_PRESS_MASK) {
            g_rpt.buttons &= (uint16_t)~runner.cur.button_mask;
        } else if (runner.cur.kind == ACT_DPAD) {
            g_rpt.hat = hat_neutral();
        }
        runner.active = false;
    }
}

// ------------------- Command parser -------------------
static void trim(char* s) {
    while (*s && isspace((unsigned char)*s)) {
        memmove(s, s + 1, strlen(s));
    }
    size_t len = strlen(s);
    while (len > 0 && isspace((unsigned char)s[len - 1])) {
        s[--len] = 0;
    }
}

static bool parse_button(const char* s, button_t* out) {
    if (!strcmp(s, "A")) { *out = ABTN_A; return true; }
    if (!strcmp(s, "B")) { *out = ABTN_B; return true; }
    if (!strcmp(s, "X")) { *out = ABTN_X; return true; }
    if (!strcmp(s, "Y")) { *out = ABTN_Y; return true; }
    if (!strcmp(s, "L")) { *out = ABTN_L; return true; }
    if (!strcmp(s, "R")) { *out = ABTN_R; return true; }
    if (!strcmp(s, "ZL")) { *out = ABTN_ZL; return true; }
    if (!strcmp(s, "ZR")) { *out = ABTN_ZR; return true; }
    if (!strcmp(s, "+")) { *out = ABTN_PLUS; return true; }
    if (!strcmp(s, "-")) { *out = ABTN_MINUS; return true; }
    if (!strcmp(s, "HOME")) { *out = ABTN_HOME; return true; }
    if (!strcmp(s, "CAPTURE")) { *out = ABTN_CAPTURE; return true; }
    return false;
}

static bool parse_dpad(const char* s, dpad_t* out) {
    if (!strcmp(s, "UP"))    { *out = DPAD_UP; return true; }
    if (!strcmp(s, "RIGHT")) { *out = DPAD_RIGHT; return true; }
    if (!strcmp(s, "DOWN"))  { *out = DPAD_DOWN; return true; }
    if (!strcmp(s, "LEFT"))  { *out = DPAD_LEFT; return true; }
    return false;
}

static bool parse_cmd_and_enqueue(const char* body) {
    char buf[256];
    strncpy(buf, body, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = 0;
    trim(buf);
    if (buf[0] == 0) return false;

    char* save = NULL;
    char* t0 = strtok_r(buf, " \t\r\n", &save);
    if (!t0) return false;

    if (!strcmp(t0, "wait")) {
        char* t1 = strtok_r(NULL, " \t\r\n", &save);
        if (!t1) return false;
        uint32_t ms = (uint32_t)strtoul(t1, NULL, 10);
        return q_push((action_t){ .kind = ACT_WAIT, .ms = ms });
    }

    if (!strcmp(t0, "press")) {
        char* t1 = strtok_r(NULL, " \t\r\n", &save);
        char* t2 = strtok_r(NULL, " \t\r\n", &save);
        if (!t1 || !t2) return false;

        button_t b;
        if (!parse_button(t1, &b)) return false;

        uint32_t ms = (uint32_t)strtoul(t2, NULL, 10);
        return q_push((action_t){
            .kind = ACT_PRESS_MASK,
            .ms = ms,
            .button_mask = map_button(b)
        });
    }

    if (!strcmp(t0, "dpad")) {
        char* t1 = strtok_r(NULL, " \t\r\n", &save);
        char* t2 = strtok_r(NULL, " \t\r\n", &save);
        if (!t1 || !t2) return false;

        dpad_t d;
        if (!parse_dpad(t1, &d)) return false;

        uint32_t ms = (uint32_t)strtoul(t2, NULL, 10);
        return q_push((action_t){
            .kind = ACT_DPAD,
            .ms = ms,
            .dpad = d
        });
    }

    if (!strcmp(t0, "combo")) {
        uint16_t mask = 0;
        char* token = NULL;
        char* last = NULL;

        while ((token = strtok_r(NULL, " \t\r\n", &save)) != NULL) {
            last = token;
        }

        if (!last) return false;

        uint32_t ms = (uint32_t)strtoul(last, NULL, 10);
        if (ms == 0) return false;

        // Re-tokenize to collect buttons except final duration token
        strncpy(buf, body, sizeof(buf) - 1);
        buf[sizeof(buf) - 1] = 0;
        trim(buf);
        save = NULL;
        strtok_r(buf, " \t\r\n", &save); // skip "combo"

        while ((token = strtok_r(NULL, " \t\r\n", &save)) != NULL) {
            char* next = strtok_r(NULL, " \t\r\n", &save);
            if (!next) {
                // token is duration
                break;
            }

            button_t b;
            if (!parse_button(token, &b)) return false;
            mask |= map_button(b);

            // Put next token back by rebuilding parser position
            save -= strlen(next) + 1;
        }

        if (mask == 0) return false;

        return q_push((action_t){
            .kind = ACT_PRESS_MASK,
            .ms = ms,
            .button_mask = mask
        });
    }

    if (!strcmp(t0, "macro")) {
        char* t1 = strtok_r(NULL, " \t\r\n", &save);
        if (!t1) return false;

        if (!strcmp(t1, "soft_reset")) {
            return enqueue_soft_reset();
        }

        return false;
    }

    return false;
}

// ------------------- HTTP server -------------------
typedef struct {
    const char* resp;
    uint16_t resp_len;
} conn_state_t;

static err_t on_sent(void* arg, struct tcp_pcb* tpcb, u16_t len) {
    (void)len;
    conn_state_t* st = (conn_state_t*)arg;
    if (st) {
        tcp_arg(tpcb, NULL);
        free(st);
    }
    tcp_close(tpcb);
    return ERR_OK;
}

static err_t on_recv(void* arg, struct tcp_pcb* tpcb, struct pbuf* p, err_t err) {
    (void)err;

    if (!p) {
        conn_state_t* st = (conn_state_t*)arg;
        if (st) free(st);
        tcp_arg(tpcb, NULL);
        tcp_close(tpcb);
        return ERR_OK;
    }

    tcp_recved(tpcb, p->tot_len);

    char req[768];
    int n = pbuf_copy_partial(p, req, sizeof(req) - 1, 0);
    req[n] = 0;
    pbuf_free(p);

    static const char resp_pong[] =
        "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 4\r\n\r\npong";

    static const char resp_ready[] =
        "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 5\r\n\r\nready";

    static char resp_status[128];

    static const char resp_ok[] =
        "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 2\r\n\r\nOK";

    static const char resp_bad[] =
        "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 3\r\n\r\nBAD";

    static const char resp_404[] =
        "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 9\r\n\r\nnot found";

    const char* resp = resp_404;
    bool command_received = false;

    if (strncmp(req, "GET /ping", 9) == 0) {
        resp = resp_pong;
    } else if (strncmp(req, "GET /ready", 10) == 0) {
        resp = resp_ready;
    } else if (strncmp(req, "GET /status", 11) == 0) {
        int queue_len = q_count() + (runner.active ? 1 : 0);
        int body_len = snprintf(
            resp_status,
            sizeof(resp_status),
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            "Connection: close\r\n\r\n"
            "ready=1;queue=%d;wifi=%d",
            queue_len,
            g_wifi_connected ? 1 : 0
        );
        (void)body_len;
        resp = resp_status;
    } else if (strncmp(req, "POST /reset", 11) == 0) {
        bool ok = enqueue_soft_reset();
        if (ok) {
            led_trigger_command_blink();
            command_received = true;
        }
        resp = ok ? resp_ok : resp_bad;
    } else if (strncmp(req, "POST /cmd", 9) == 0) {
        char* body = strstr(req, "\r\n\r\n");
        if (!body) {
            resp = resp_bad;
        } else {
            body += 4;
            bool ok = parse_cmd_and_enqueue(body);
            if (ok) {
                led_trigger_command_blink();
                command_received = true;
            }
            resp = ok ? resp_ok : resp_bad;
        }
    }

    (void)command_received;

    uint16_t resp_len = (uint16_t)strlen(resp);

    conn_state_t* st = (conn_state_t*)arg;
    if (!st) {
        st = (conn_state_t*)calloc(1, sizeof(conn_state_t));
        tcp_arg(tpcb, st);
        tcp_sent(tpcb, on_sent);
    }

    st->resp = resp;
    st->resp_len = resp_len;

    if (tcp_write(tpcb, st->resp, st->resp_len, TCP_WRITE_FLAG_COPY) != ERR_OK) {
        free(st);
        tcp_arg(tpcb, NULL);
        tcp_close(tpcb);
        return ERR_OK;
    }

    tcp_output(tpcb);
    return ERR_OK;
}

static err_t on_accept(void* arg, struct tcp_pcb* newpcb, err_t err) {
    (void)arg;
    (void)err;
    tcp_recv(newpcb, on_recv);
    tcp_arg(newpcb, NULL);
    return ERR_OK;
}

static void start_http(void) {
    struct tcp_pcb* pcb = tcp_new_ip_type(IPADDR_TYPE_ANY);
    if (!pcb) return;
    if (tcp_bind(pcb, IP_ANY_TYPE, HTTP_PORT) != ERR_OK) {
        tcp_close(pcb);
        return;
    }
    pcb = tcp_listen_with_backlog(pcb, 4);
    tcp_accept(pcb, on_accept);
}

// ------------------- TinyUSB HID callbacks -------------------
static void hid_send_report(void) {
    if (!tud_hid_ready()) return;
    tud_hid_report(0, &g_rpt, sizeof(g_rpt));
}

void tud_mount_cb(void) {
    // Optional: auto handshake nudge for controller screen
    q_push((action_t){ .kind = ACT_PRESS_MASK, .ms = 120, .button_mask = map_button(ABTN_L) });
    q_push((action_t){ .kind = ACT_PRESS_MASK, .ms = 120, .button_mask = map_button(ABTN_R) });
}

void tud_hid_report_complete_cb(uint8_t instance, uint8_t const* report, uint16_t len) {
    (void)instance;
    (void)report;
    (void)len;
}

// ------------------- main -------------------
int main(void) {
    stdio_init_all();

    report_set_neutral();

    if (cyw43_arch_init()) {
        while (true) {
            sleep_ms(1000);
        }
    }

    cyw43_arch_enable_sta_mode();

    int rc = cyw43_arch_wifi_connect_timeout_ms(
        WIFI_SSID,
        WIFI_PASSWORD,
        CYW43_AUTH_WPA2_AES_PSK,
        20000
    );

    if (rc != 0) {
        while (true) {
            sleep_ms(500);
        }
    }

    g_wifi_connected = true;
    led_set_ready();

    cyw43_arch_lwip_begin();
    start_http();
    cyw43_arch_lwip_end();

    tusb_init();

    absolute_time_t next_hid = make_timeout_time_ms(5);

    while (true) {
        tud_task();

        if (!runner.active) {
            action_t a;
            if (q_pop(&a)) {
                runner_start(a);
            }
        }

        runner_tick();
        led_tick();

        if (absolute_time_diff_us(get_absolute_time(), next_hid) <= 0) {
            hid_send_report();
            next_hid = make_timeout_time_ms(5);
        }

        sleep_ms(1);
    }
}