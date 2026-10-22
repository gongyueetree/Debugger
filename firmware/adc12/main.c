// SPDX-License-Identifier: MIT
// LA_RP2040 ADC acquisition, 2026. Built with the Raspberry Pi Pico SDK.
// DMA flow follows raspberrypi/pico-examples adc/dma_capture (BSD-3-Clause).
// Protocol v1: 16-byte little-endian request and response; no text on data port.
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/adc.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"

#define DEPTH 32768
static uint16_t samples[DEPTH];
static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void put32(uint32_t x) { for (int i=0;i<4;i++) putchar_raw(x>>(8*i)&255); }
static void header(const char *magic, uint32_t rate, uint32_t count, uint32_t status) {
    for(int i=0;i<4;i++) putchar_raw(magic[i]);
    put32(rate); put32(count); put32(status); stdio_flush();
}
static bool allowed_rate(uint32_t r) {
    return r==10000 || r==20000 || r==50000 || r==100000 || r==200000 || r==250000 || r==500000;
}
int main(void) {
    stdio_init_all();
    gpio_init(0); gpio_set_dir(0,GPIO_OUT);
    adc_init();
    for(int pin=26;pin<=28;pin++) adc_gpio_init(pin);
    int channel=dma_claim_unused_channel(true);
    while(true) {
        uint8_t req[16]; int c=getchar_timeout_us(100000);
        if(c!='A') continue;
        req[0]=(uint8_t)c; bool complete=true;
        for(int i=1;i<16;i++) {
            c=getchar_timeout_us(100000);
            if(c<0) { complete=false; break; }
            req[i]=(uint8_t)c;
        }
        if(!complete || memcmp(req,"ADC1",4)) continue;
        if(req[4]==0) { header("ADCI",500000,DEPTH,1); continue; }
        uint32_t count=u32(req+8), rate=u32(req+12);
        if(req[4]!=1 || req[5]>2 || req[6] || req[7] || count<4 || count>DEPTH || !allowed_rate(rate)) {
            header("ADC1",rate,0,1); continue;
        }
        adc_run(false); adc_fifo_drain(); adc_set_round_robin(0);
        adc_select_input(req[5]);
        adc_fifo_setup(true,true,1,true,false); // include error bit, preserve 12-bit result
        adc_hw->fcs |= ADC_FCS_OVER_BITS | ADC_FCS_UNDER_BITS; // clear sticky FIFO errors
        adc_set_clkdiv((float)clock_get_hz(clk_adc)/(float)rate - 1.0f);
        dma_channel_config cfg=dma_channel_get_default_config(channel);
        channel_config_set_transfer_data_size(&cfg,DMA_SIZE_16);
        channel_config_set_read_increment(&cfg,false);
        channel_config_set_write_increment(&cfg,true);
        channel_config_set_dreq(&cfg,DREQ_ADC);
        dma_channel_configure(channel,&cfg,samples,&adc_hw->fifo,count,true);
        gpio_put(0,1); adc_run(true);
        absolute_time_t until=make_timeout_time_ms(5000);
        bool cancelled=false;
        while(dma_channel_is_busy(channel)) {
            if(getchar_timeout_us(0)==0x18 || !stdio_usb_connected() || time_reached(until)) {
                cancelled=true; break;
            }
            tight_loop_contents();
        }
        adc_run(false);
        if(cancelled) dma_channel_abort(channel);
        uint32_t errors=(adc_hw->fcs & ADC_FCS_OVER_BITS) ? 2 : 0;
        adc_fifo_drain(); gpio_put(0,0);
        if(cancelled) { if(stdio_usb_connected()) header("ADC1",rate,0,3); continue; }
        header("ADC1",rate,count,errors);
        if(errors) continue;
        for(uint32_t i=0;i<count;i++) { putchar_raw(samples[i]&255); putchar_raw(samples[i]>>8); }
        stdio_flush();
    }
}
