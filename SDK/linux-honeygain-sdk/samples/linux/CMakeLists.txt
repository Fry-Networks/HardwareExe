cmake_minimum_required(VERSION 3.1)

project(TestApp LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

find_package(Threads REQUIRED)
find_package(hgsdk CONFIG REQUIRED)

add_executable(app main.c)

target_link_libraries(app PRIVATE Threads::Threads hgsdk::hgsdk)
