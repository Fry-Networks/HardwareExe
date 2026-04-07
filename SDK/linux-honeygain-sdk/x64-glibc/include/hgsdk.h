#pragma once

#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

int32_t hgsdk_start(const char *api_key, int32_t *state);

int32_t hgsdk_stop(void);

int32_t hgsdk_is_running(int32_t *state);

int32_t hgsdk_opt_in(void);

int32_t hgsdk_opt_out(void);

int32_t hgsdk_is_opted_in(int32_t *state);

int32_t hgsdk_request_consent(int32_t *state);

int32_t hgsdk_identify(char *data, size_t *size);

int32_t hgsdk_log(const char *dir);

int32_t hgsdk_mute(void);

#ifdef __cplusplus
}  // extern "C"
#endif  // __cplusplus
