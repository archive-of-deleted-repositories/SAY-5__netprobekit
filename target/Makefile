CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -pedantic -std=c11 -pthread

target: target.c
	$(CC) $(CFLAGS) target.c -o target

clean:
	rm -f target
