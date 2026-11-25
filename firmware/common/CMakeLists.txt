# Rad Roomba portable firmware library (C11, no dynamic allocation, no OS dependencies).
# Usable stand-alone (host unit tests) or via add_subdirectory() from a firmware project.
cmake_minimum_required(VERSION 3.16)
project(rr_common C)

set(RR_COMMON_SOURCES
    src/rrc_base64.c src/rrc_clock.c src/rrc_crc32.c src/rrc_envelope.c src/rrc_frame.c
    src/rrc_json_reader.c src/rrc_json_writer.c src/rrc_ring.c src/rrc_sha256.c src/rrc_uuid.c)

add_library(rr_common STATIC ${RR_COMMON_SOURCES})
target_include_directories(rr_common PUBLIC include)
set_target_properties(rr_common PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
target_compile_options(rr_common PRIVATE -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes
                                         -Wmissing-prototypes -Wpedantic)

option(RR_COMMON_SANITIZE "Build with AddressSanitizer + UndefinedBehaviorSanitizer" ON)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  set(RR_COMMON_TOPLEVEL ON)
else()
  set(RR_COMMON_TOPLEVEL OFF)
endif()
option(RR_COMMON_BUILD_TESTS "Build the host unit tests and the codec CLI" ${RR_COMMON_TOPLEVEL})

if(RR_COMMON_BUILD_TESTS)
  if(RR_COMMON_SANITIZE AND RR_COMMON_TOPLEVEL)
    add_compile_options(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
  endif()
  enable_testing()
  add_executable(test_common tests/test_common.c)
  target_link_libraries(test_common PRIVATE rr_common)
  target_compile_options(test_common PRIVATE -Wall -Wextra -Werror -Wconversion)
  set_target_properties(test_common PROPERTIES C_STANDARD 11 C_EXTENSIONS OFF)
  add_test(NAME common_unit COMMAND test_common)

  add_executable(rrc_codec_tool tests/rrc_codec_tool.c)
  target_link_libraries(rrc_codec_tool PRIVATE rr_common)
  target_compile_options(rrc_codec_tool PRIVATE -Wall -Wextra -Werror -Wconversion)
  set_target_properties(rrc_codec_tool PROPERTIES C_STANDARD 11 C_EXTENSIONS OFF)
  find_package(Python3 COMPONENTS Interpreter)
  if(Python3_FOUND)
    add_test(NAME common_python_interop
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_interop.py $<TARGET_FILE:rrc_codec_tool>)
  endif()
endif()
