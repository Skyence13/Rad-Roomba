# Host build of the head firmware: core library, emulator (rr_head_sim) and unit tests.
# The STM32G474 image is built with PlatformIO (platformio.ini), not from here.
cmake_minimum_required(VERSION 3.16)
project(rr_head_host C)

option(RRH_SANITIZE "Build with AddressSanitizer + UndefinedBehaviorSanitizer" ON)
if(RRH_SANITIZE)
  add_compile_options(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

set(RR_COMMON_BUILD_TESTS ON CACHE BOOL "" FORCE)
enable_testing()
add_subdirectory(../common common)

set(RRH_WARN -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes)

add_library(rrh_core STATIC core/rrh_core.c core/rrh_acq.c core/rrh_setup.c core/rrh_control.c core/rrh_eng.c
                            core/rrh_evtcap.c)
target_include_directories(rrh_core PUBLIC core hal)
target_link_libraries(rrh_core PUBLIC rr_common)
target_compile_options(rrh_core PRIVATE ${RRH_WARN} -Wpedantic)
set_target_properties(rrh_core PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)

add_executable(rr_head_sim port/host/sim_main.c port/host/sim_hal.c)
target_link_libraries(rr_head_sim PRIVATE rrh_core m)
target_compile_options(rr_head_sim PRIVATE ${RRH_WARN})
set_target_properties(rr_head_sim PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)

add_executable(test_core tests/test_core.c)
target_link_libraries(test_core PRIVATE rrh_core)
target_include_directories(test_core PRIVATE ../common/tests)
target_compile_options(test_core PRIVATE ${RRH_WARN})
set_target_properties(test_core PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
add_test(NAME head_core_unit COMMAND test_core)

add_executable(test_evtcap tests/test_evtcap.c)
target_link_libraries(test_evtcap PRIVATE rrh_core m)
target_include_directories(test_evtcap PRIVATE ../common/tests)
target_compile_options(test_evtcap PRIVATE ${RRH_WARN})
set_target_properties(test_evtcap PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
add_test(NAME head_evtcap_unit COMMAND test_evtcap)

find_package(Python3 COMPONENTS Interpreter)
if(Python3_FOUND)
  add_test(NAME head_sim_interop
           COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_sim_interop.py $<TARGET_FILE:rr_head_sim>)
  set_tests_properties(head_sim_interop PROPERTIES TIMEOUT 300)
endif()
