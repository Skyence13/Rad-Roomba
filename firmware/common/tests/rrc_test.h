/* Minimal unit-test helpers shared by the firmware host tests (no external framework). */
#ifndef RRC_TEST_H
#define RRC_TEST_H
#include <stdio.h>
#include <string.h>

static int rrc_t_failures;
static int rrc_t_checks;
static int rrc_t_tests;

#define CHECK(cond)                                                             \
    do {                                                                        \
        rrc_t_checks++;                                                         \
        if (!(cond)) {                                                          \
            rrc_t_failures++;                                                   \
            printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);           \
        }                                                                       \
    } while (0)

#define CHECK_STR(a, b)                                                         \
    do {                                                                        \
        rrc_t_checks++;                                                         \
        if (strcmp((a), (b)) != 0) {                                            \
            rrc_t_failures++;                                                   \
            printf("  FAIL %s:%d: \"%s\" != \"%s\"\n", __FILE__, __LINE__, (a), (b)); \
        }                                                                       \
    } while (0)

#define RUN(fn)                                                                 \
    do {                                                                        \
        const int before_ = rrc_t_failures;                                     \
        rrc_t_tests++;                                                          \
        fn();                                                                   \
        printf("[%s] %s\n", (rrc_t_failures == before_) ? " ok " : "FAIL", #fn); \
    } while (0)

#define TEST_SUMMARY()                                                          \
    (printf("%d tests, %d checks, %d failures\n", rrc_t_tests, rrc_t_checks, rrc_t_failures), \
     (rrc_t_failures == 0) ? 0 : 1)

#endif
