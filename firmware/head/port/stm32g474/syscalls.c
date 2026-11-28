/* newlib-nano references these through its stdio clean-up code even though the firmware never
 * uses stdio. Minimal stubs keep the link free of "not implemented" warnings. */
#include <errno.h>
#include <sys/types.h>

int _close(int fd);
off_t _lseek(int fd, off_t offset, int whence);
int _read(int fd, void *buf, size_t count);
int _write(int fd, const void *buf, size_t count);

int _close(int fd) { (void)fd; errno = EBADF; return -1; }
off_t _lseek(int fd, off_t offset, int whence) { (void)fd; (void)offset; (void)whence; errno = EBADF; return (off_t)-1; }
int _read(int fd, void *buf, size_t count) { (void)fd; (void)buf; (void)count; errno = EBADF; return -1; }
int _write(int fd, const void *buf, size_t count) { (void)fd; (void)buf; (void)count; errno = EBADF; return -1; }
