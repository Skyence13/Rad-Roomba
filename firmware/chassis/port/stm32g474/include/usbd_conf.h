/* USB device library configuration for the RR-CHS chassis link (CDC-ACM, full speed).
 * Derived from ST's usbd_conf_template.h (STM32CubeG4 1.6.3). The defines for classes this
 * firmware does not use are kept only because PlatformIO compiles every class library. */
#ifndef USBD_CONF_H
#define USBD_CONF_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stm32g4xx.h"
#include "stm32g4xx_hal.h"

#define USBD_MAX_NUM_INTERFACES 1U
#define USBD_MAX_NUM_CONFIGURATION 1U
#define USBD_MAX_STR_DESC_SIZ 0x100U
#define USBD_SELF_POWERED 1U
#define USBD_DEBUG_LEVEL 0U
#define USBD_LPM_ENABLED 0U
#define USBD_SUPPORT_USER_STRING_DESC 0U
#define USBD_CLASS_USER_STRING_DESC 0U
#define USBD_CLASS_BOS_ENABLED 0U
#define USB_BB_MAX_NUM_ALT_MODE 0x2U
#define DEVICE_FS 0U

/* unused classes (compile-only) */
#define MSC_MEDIA_PACKET 512U
#define USBD_CDC_INTERVAL 2000U
#define USBD_DFU_MAX_ITF_NUM 1U
#define USBD_DFU_XFERS_IZE 1024U
#define USBD_AUDIO_FREQ 22100U
#define CUSTOM_HID_HS_BINTERVAL 0x05U
#define CUSTOM_HID_FS_BINTERVAL 0x05U
#define USBD_CUSTOMHID_OUTREPORT_BUF_SIZE 0x02U
#define USBD_CUSTOM_HID_REPORT_DESC_SIZE 163U
#define UVC_1_1
#define USBD_UVC_FORMAT_UNCOMPRESSED
#define UVC_BITS_PER_PIXEL 12U
#define UVC_UNCOMPRESSED_GUID UVC_GUID_NV12
#define UVC_COLOR_PRIMARIE 0x01U
#define UVC_TFR_CHARACTERISTICS 0x01U
#define UVC_MATRIX_COEFFICIENTS 0x04U
#define UVC_WIDTH 176U
#define UVC_HEIGHT 144U
#define UVC_IN_EP 0x81U
#define UVC_CAM_FPS_FS 10U
#define UVC_CAM_FPS_HS 5U
#define UVC_ISO_FS_MPS 512U
#define UVC_ISO_HS_MPS 512U
#define UVC_PACKET_SIZE UVC_ISO_FS_MPS
#define UVC_MAX_FRAME_SIZE (UVC_WIDTH * UVC_HEIGHT * 16U / 8U)

#define USBD_malloc (void *)USBD_static_malloc
#define USBD_free USBD_static_free
#define USBD_memset memset
#define USBD_memcpy memcpy
#define USBD_Delay HAL_Delay
#define USBD_UsrLog(...) do {} while (0)
#define USBD_ErrLog(...) do {} while (0)
#define USBD_DbgLog(...) do {} while (0)

void *USBD_static_malloc(uint32_t size);
void USBD_static_free(void *p);

#endif
