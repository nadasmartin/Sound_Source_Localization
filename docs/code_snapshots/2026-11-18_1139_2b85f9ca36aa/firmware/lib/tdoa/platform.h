// The few platform-specific bits: ring buffer memory and a microsecond clock.
//
// Memory for the ring buffer:
// On the ESP32 ~80 KB of the internal RAM (IRAM heap) only accepts 32-bit
// *integer* loads and stores: 8/16-bit accesses and even the FPU's float
// loads raise a LoadStoreError there. The ring buffer is therefore stored as
// uint32 words (two 12-bit samples per word) and only ever touched as whole
// words, which lets it live in IRAM and leaves the normal DRAM for the float
// FFT buffers. On the PC this is plain malloc.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#ifdef ESP_PLATFORM
#include <esp_heap_caps.h>
#include <esp_timer.h>
#else
#include <chrono>
#endif

namespace dsp {

// Only for memory accessed exclusively as uint32_t (never float, never bytes).
inline uint32_t *allocWords32(size_t words) {
#ifdef ESP_PLATFORM
  void *p = heap_caps_malloc(words * 4, MALLOC_CAP_32BIT | MALLOC_CAP_INTERNAL);
  if (!p) p = heap_caps_malloc(words * 4, MALLOC_CAP_8BIT);
  return static_cast<uint32_t *>(p);
#else
  return static_cast<uint32_t *>(malloc(words * 4));
#endif
}

inline int64_t nowUs() {
#ifdef ESP_PLATFORM
  return esp_timer_get_time();
#else
  return std::chrono::duration_cast<std::chrono::microseconds>(
             std::chrono::steady_clock::now().time_since_epoch()).count();
#endif
}

}  // namespace dsp
