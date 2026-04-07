CFLAGS := $(shell pkg-config --cflags hgsdk)
LIBS   := $(shell pkg-config --libs hgsdk)

.PHONY: all clean

all:
	gcc -std=c11 -pthread $(CFLAGS) main.c $(LIBS) -o app

clean:
	rm -f app
