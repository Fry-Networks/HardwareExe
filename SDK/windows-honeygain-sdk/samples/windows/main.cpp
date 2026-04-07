#include <iostream>
#include <thread>
#include <chrono>
#include <atomic>
#include <hgsdk.h>

std::atomic<bool> done = false;

static void input() {
    std::cin.get();
    done = true;
}

int main() {
    int32_t consent;
    if (hgsdk_is_opted_in(&consent) < 0) {
        std::cout << "Failed to check if user is opted in" << std::endl;
        return -1;
    }

    if (!consent) {
        if (hgsdk_request_consent(&consent) < 0) {
            std::cout << "Failed to request user consent" << std::endl;
            return -1;
        }

        if (!consent) {
            if (hgsdk_opt_out() < 0) {
                std::cout << "Failed to opt out user" << std::endl;
                return -1;
            }

            std::cout << "User did not give his consent" << std::endl;
            return -1;
        }
        else {
            std::cout << "User has given his consent" << std::endl;
        }
    }
    else {
        std::cout << "User has already given his consent" << std::endl;
    }

    if (hgsdk_start("your-api-key", &consent) < 0) {
        std::cout << "Failed to start HG SDK" << std::endl;
        return -1;
    }

    if (!consent) {
        std::cout << "HG SDK is not started because user has not given his consent" << std::endl;
        return -1;
    }

    std::cout << "HG SDK is started" << std::endl;
    std::cout << "Press enter to exit" << std::endl;

    std::thread listener(input);
    while (!done) {
        int32_t running;
        if (hgsdk_is_running(&running) < 0) {
            std::cout << "Failed to check if HG SDK is running" << std::endl;
            return -1;
        }

        if (running)
            std::cout << "HG SDK is running" << std::endl;
        else
            std::cout << "HG SDK is not running" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    listener.join();

    if (hgsdk_stop() < 0) {
        std::cout << "Failed to stop HG SDK" << std::endl;
        return -1;
    }

    std::cout << "HG SDK is stopped" << std::endl;
    return 0;
}
