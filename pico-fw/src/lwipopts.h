#ifndef _LWIPOPTS_H
#define _LWIPOPTS_H

// Minimal lwIP config good enough for a simple HTTP server
#define NO_SYS                      1
#define LWIP_SOCKET                 0
#define LWIP_NETCONN                0

#define LWIP_DHCP                   1
#define LWIP_DNS                    1
#define LWIP_UDP                    1
#define LWIP_TCP                    1

#define MEM_LIBC_MALLOC             0
#define MEMP_MEM_MALLOC             0
#define MEM_ALIGNMENT               4
#define MEM_SIZE                    (16 * 1024)
#define MEMP_NUM_TCP_PCB            8
#define MEMP_NUM_TCP_SEG            32
#define TCP_MSS                     1460
#define TCP_SND_BUF                 (4 * TCP_MSS)
#define TCP_WND                     (4 * TCP_MSS)

#define LWIP_HTTPD                  0  // we’ll use a tiny raw HTTP server first

// Debug off
#define LWIP_DEBUG                  0

#endif