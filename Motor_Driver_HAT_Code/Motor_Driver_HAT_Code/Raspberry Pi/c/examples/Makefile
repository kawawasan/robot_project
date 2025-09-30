# Target executable name
TARGET = move_mucvis

# Compiler
CC = gcc

# Source files
SRCS =  $(TARGET).c \
	../lib/Config/DEV_Config.c \
	main.c \
	../lib/PCA9685/PCA9685.c

# Include directories
INCLUDE = -I../lib/Config \
          -I../lib/Motor \
          -I../lib/PCA9685 \
          -I.

# Libraries to link
LIBS = -lwiringPi -lm

# Compiler flags
CFLAGS = -Wall $(INCLUDE)

# Build rule
all: $(TARGET)

$(TARGET): $(SRCS)
	$(CC) -o $@ $^ $(CFLAGS) $(LIBS)

# Clean rule
clean:
	rm -f $(TARGET)
