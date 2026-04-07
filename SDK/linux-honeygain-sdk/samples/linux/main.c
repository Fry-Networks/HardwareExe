#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
#include <hgsdk.h>

static atomic_bool done = ATOMIC_VAR_INIT(false);

void *input_thread(void *arg) {
    getchar();
    atomic_store(&done, true);
    return NULL;
}

int main(void) {
    int32_t consent;

    if (hgsdk_is_opted_in(&consent) < 0) {
        printf("Failed to check if user is opted in\n");
        return EXIT_FAILURE;
    }

    if (!consent) {
        if (hgsdk_opt_in() < 0) {
            printf("Failed to opt in user\n");
            return EXIT_FAILURE;
        }
    }

    if (hgsdk_start("your-api-key", &consent) < 0) {
        printf("Failed to start HG SDK\n");
        return EXIT_FAILURE;
    }
    if (!consent) {
        printf("HG SDK is not started because consent is not given\n");
        return EXIT_FAILURE;
    }

    printf("HG SDK is started\n");
    printf("Press Enter to exit\n");

    pthread_t listener;
    if (pthread_create(&listener, NULL, input_thread, NULL) != 0) {
        printf("Failed to create input thread\n");
        return EXIT_FAILURE;
    }

    while (!atomic_load(&done)) {
        int32_t running;
        if (hgsdk_is_running(&running) < 0) {
            printf("Failed to check if HG SDK is running\n");
            return EXIT_FAILURE;
        }
        if (running)
            printf("HG SDK is running\n");
        else
            printf("HG SDK is not running\n");

        sleep(1);
    }

    pthread_join(listener, NULL);

    if (hgsdk_stop() < 0) {
        printf("Failed to stop HG SDK\n");
        return EXIT_FAILURE;
    }

    printf("HG SDK is stopped\n");
    return EXIT_SUCCESS;
}
