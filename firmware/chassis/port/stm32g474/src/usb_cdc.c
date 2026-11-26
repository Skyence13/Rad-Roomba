/* USB FS device, CDC-ACM: glue between ST's USB device library (STM32CubeG4 1.6.3), the HAL PCD
 * driver and the byte-stream link of the chassis core. NOT TESTED ON HARDWARE. The VID/PID are
 * the pid.codes test pair and MUST be replaced before any unit leaves the bench. */
#include "bsp.h"
#include "usbd_cdc.h"
#include "usbd_core.h"

#define USB_VID 0x1209u /* PLACEHOLDER (pid.codes) */
#define USB_PID 0x0001u /* PLACEHOLDER (test PID) */

static PCD_HandleTypeDef hpcd;
static USBD_HandleTypeDef husb;
static uint8_t rx_pkt[CDC_DATA_FS_MAX_PACKET_SIZE];
static uint8_t rx_store[4096];
static rrc_ring_t rx_ring;
static volatile bool tx_busy;

/* ---- descriptors ---- */
static uint8_t dev_desc[USB_LEN_DEV_DESC] = {0x12, USB_DESC_TYPE_DEVICE, 0x00, 0x02, 0x02, 0x02, 0x00, USB_MAX_EP0_SIZE, USB_VID & 0xFF, USB_VID >> 8,
                                             USB_PID & 0xFF, USB_PID >> 8, 0x00, 0x04, USBD_IDX_MFC_STR, USBD_IDX_PRODUCT_STR, USBD_IDX_SERIAL_STR, 1};
static uint8_t lang_desc[USB_LEN_LANGID_STR_DESC] = {USB_LEN_LANGID_STR_DESC, USB_DESC_TYPE_STRING, 0x09, 0x04};
static uint8_t str_buf[USBD_MAX_STR_DESC_SIZ];

static uint8_t *d_device(USBD_SpeedTypeDef s, uint16_t *len) { (void)s; *len = sizeof dev_desc; return dev_desc; }
static uint8_t *d_lang(USBD_SpeedTypeDef s, uint16_t *len) { (void)s; *len = sizeof lang_desc; return lang_desc; }
static uint8_t *d_str(const char *t, uint16_t *len) { USBD_GetString((uint8_t *)t, str_buf, len); return str_buf; }
static uint8_t *d_mfc(USBD_SpeedTypeDef s, uint16_t *len) { (void)s; return d_str("Rad Roomba", len); }
static uint8_t *d_prod(USBD_SpeedTypeDef s, uint16_t *len) { (void)s; return d_str("RR-CHS chassis link", len); }
static uint8_t *d_cfg(USBD_SpeedTypeDef s, uint16_t *len) { (void)s; return d_str("CDC Config", len); }
static uint8_t *d_itf(USBD_SpeedTypeDef s, uint16_t *len) { (void)s; return d_str("CDC Interface", len); }
static uint8_t *d_serial(USBD_SpeedTypeDef s, uint16_t *len)
{
    static const char H[] = "0123456789ABCDEF";
    char txt[25];
    uint32_t uid[3] = {HAL_GetUIDw0(), HAL_GetUIDw1(), HAL_GetUIDw2()};
    (void)s;
    for (int i = 0; i < 24; i++) {
        txt[i] = H[(uid[i / 8] >> (28 - 4 * (i % 8))) & 15u];
    }
    txt[24] = 0;
    return d_str(txt, len);
}
static USBD_DescriptorsTypeDef desc = {d_device, d_lang, d_mfc, d_prod, d_serial, d_cfg, d_itf};

/* ---- CDC class interface ---- */
static int8_t cdc_init(void)
{
    USBD_CDC_SetRxBuffer(&husb, rx_pkt);
    return USBD_OK;
}
static int8_t cdc_deinit(void) { return USBD_OK; }
static int8_t cdc_control(uint8_t cmd, uint8_t *buf, uint16_t len)
{
    (void)cmd; (void)buf; (void)len; /* line coding and control lines are ignored (ICD section 1) */
    return USBD_OK;
}
static int8_t cdc_receive(uint8_t *buf, uint32_t *len)
{
    for (uint32_t i = 0; i < *len; i++) {
        (void)rrc_ring_push(&rx_ring, buf[i]); /* a full ring drops bytes: the record then fails its CRC */
    }
    USBD_CDC_ReceivePacket(&husb);
    return USBD_OK;
}
static int8_t cdc_tx_done(uint8_t *buf, uint32_t *len, uint8_t ep)
{
    (void)buf; (void)len; (void)ep;
    tx_busy = false;
    return USBD_OK;
}
static USBD_CDC_ItfTypeDef cdc_itf = {cdc_init, cdc_deinit, cdc_control, cdc_receive, cdc_tx_done};

void usb_cdc_init(void)
{
    (void)rrc_ring_init(&rx_ring, rx_store, sizeof rx_store);
    USBD_Init(&husb, &desc, 0);
    USBD_RegisterClass(&husb, &USBD_CDC);
    USBD_CDC_RegisterInterface(&husb, &cdc_itf);
    USBD_Start(&husb);
}

bool usb_cdc_up(void)
{
    return husb.dev_state == USBD_STATE_CONFIGURED;
}

size_t usb_cdc_read(uint8_t *buf, size_t cap)
{
    size_t n = 0;
    while (n < cap && rrc_ring_pop(&rx_ring, &buf[n])) {
        n++;
    }
    return n;
}

/* Blocking with a bound: one record (<= 2048 bytes) leaves in <= 33 full-speed packets. */
bool usb_cdc_write(const uint8_t *buf, size_t len)
{
    if (!usb_cdc_up()) {
        return false;
    }
    uint32_t t0 = HAL_GetTick();
    while (tx_busy) {
        if (HAL_GetTick() - t0 > 20u) {
            tx_busy = false; /* host is not reading: drop, the host retries */
            return false;
        }
    }
    tx_busy = true;
    USBD_CDC_SetTxBuffer(&husb, (uint8_t *)(uintptr_t)buf, (uint32_t)len);
    if (USBD_CDC_TransmitPacket(&husb) != USBD_OK) {
        tx_busy = false;
        return false;
    }
    while (tx_busy) { /* the reply buffer is reused by the next transaction: wait until it has left */
        if (HAL_GetTick() - t0 > 50u) {
            tx_busy = false;
            return false;
        }
    }
    return true;
}

void USB_LP_IRQHandler(void)
{
    HAL_PCD_IRQHandler(&hpcd);
}

/* ---- HAL PCD -> library ---- */
void HAL_PCD_MspInit(PCD_HandleTypeDef *h)
{
    if (h->Instance == USB) {
        __HAL_RCC_USB_CLK_ENABLE();
        HAL_NVIC_SetPriority(USB_LP_IRQn, 3, 0);
        HAL_NVIC_EnableIRQ(USB_LP_IRQn);
    }
}
void HAL_PCD_SetupStageCallback(PCD_HandleTypeDef *h) { USBD_LL_SetupStage((USBD_HandleTypeDef *)h->pData, (uint8_t *)h->Setup); }
void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef *h, uint8_t ep) { USBD_LL_DataOutStage((USBD_HandleTypeDef *)h->pData, ep, h->OUT_ep[ep].xfer_buff); }
void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef *h, uint8_t ep) { USBD_LL_DataInStage((USBD_HandleTypeDef *)h->pData, ep, h->IN_ep[ep].xfer_buff); }
void HAL_PCD_SOFCallback(PCD_HandleTypeDef *h) { USBD_LL_SOF((USBD_HandleTypeDef *)h->pData); }
void HAL_PCD_ResetCallback(PCD_HandleTypeDef *h)
{
    USBD_LL_SetSpeed((USBD_HandleTypeDef *)h->pData, USBD_SPEED_FULL);
    USBD_LL_Reset((USBD_HandleTypeDef *)h->pData);
}
void HAL_PCD_SuspendCallback(PCD_HandleTypeDef *h) { USBD_LL_Suspend((USBD_HandleTypeDef *)h->pData); }
void HAL_PCD_ResumeCallback(PCD_HandleTypeDef *h) { USBD_LL_Resume((USBD_HandleTypeDef *)h->pData); }

/* ---- library -> HAL PCD ---- */
static USBD_StatusTypeDef st(HAL_StatusTypeDef s)
{
    return s == HAL_OK ? USBD_OK : (s == HAL_BUSY ? USBD_BUSY : USBD_FAIL);
}
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
    hpcd.pData = pdev;
    pdev->pData = &hpcd;
    hpcd.Instance = USB;
    hpcd.Init.dev_endpoints = 8;
    hpcd.Init.speed = PCD_SPEED_FULL;
    hpcd.Init.phy_itface = PCD_PHY_EMBEDDED;
    hpcd.Init.Sof_enable = DISABLE;
    hpcd.Init.low_power_enable = DISABLE;
    hpcd.Init.lpm_enable = DISABLE;
    hpcd.Init.battery_charging_enable = DISABLE;
    if (HAL_PCD_Init(&hpcd) != HAL_OK) {
        return USBD_FAIL;
    }
    /* packet memory layout: EP0 OUT/IN, CDC data IN/OUT, CDC notification IN */
    HAL_PCDEx_PMAConfig(&hpcd, 0x00, PCD_SNG_BUF, 0x18);
    HAL_PCDEx_PMAConfig(&hpcd, 0x80, PCD_SNG_BUF, 0x58);
    HAL_PCDEx_PMAConfig(&hpcd, CDC_IN_EP, PCD_SNG_BUF, 0xC0);
    HAL_PCDEx_PMAConfig(&hpcd, CDC_OUT_EP, PCD_SNG_BUF, 0x110);
    HAL_PCDEx_PMAConfig(&hpcd, CDC_CMD_EP, PCD_SNG_BUF, 0x100);
    return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef *pdev) { return st(HAL_PCD_DeInit(pdev->pData)); }
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *pdev) { return st(HAL_PCD_Start(pdev->pData)); }
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *pdev) { return st(HAL_PCD_Stop(pdev->pData)); }
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *pdev, uint8_t ep, uint8_t type, uint16_t mps) { return st(HAL_PCD_EP_Open(pdev->pData, ep, mps, type)); }
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *pdev, uint8_t ep) { return st(HAL_PCD_EP_Close(pdev->pData, ep)); }
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *pdev, uint8_t ep) { return st(HAL_PCD_EP_Flush(pdev->pData, ep)); }
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *pdev, uint8_t ep) { return st(HAL_PCD_EP_SetStall(pdev->pData, ep)); }
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *pdev, uint8_t ep) { return st(HAL_PCD_EP_ClrStall(pdev->pData, ep)); }
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef *pdev, uint8_t ep)
{
    PCD_HandleTypeDef *h = pdev->pData;
    return (ep & 0x80u) ? h->IN_ep[ep & 0x7Fu].is_stall : h->OUT_ep[ep & 0x7Fu].is_stall;
}
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef *pdev, uint8_t addr) { return st(HAL_PCD_SetAddress(pdev->pData, addr)); }
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *pdev, uint8_t ep, uint8_t *buf, uint32_t size) { return st(HAL_PCD_EP_Transmit(pdev->pData, ep, buf, size)); }
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *pdev, uint8_t ep, uint8_t *buf, uint32_t size) { return st(HAL_PCD_EP_Receive(pdev->pData, ep, buf, size)); }
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *pdev, uint8_t ep) { return HAL_PCD_EP_GetRxCount((PCD_HandleTypeDef *)pdev->pData, ep); }
void *USBD_static_malloc(uint32_t size)
{
    static uint32_t mem[(sizeof(USBD_CDC_HandleTypeDef) / 4u) + 1u];
    return size <= sizeof mem ? mem : NULL;
}
void USBD_static_free(void *p) { (void)p; }
void USBD_LL_Delay(uint32_t ms) { HAL_Delay(ms); }
