#pragma once

#include "esphome/core/component.h"
#include "esphome/components/spi/spi.h"
#include "esphome/components/display/display_buffer.h"
#include "esphome/core/gpio.h"

namespace esphome
{
    namespace gc9a01a_display
    {

        // Display dimensions for GC9A01A (240x240 round display)
        static const uint16_t GC9A01A_WIDTH = 240;
        static const uint16_t GC9A01A_HEIGHT = 240;

        // GC9A01A Commands
        static const uint8_t GC9A01A_SWRESET = 0x01; // Software Reset
        static const uint8_t GC9A01A_SLPOUT = 0x11;  // Sleep Out
        static const uint8_t GC9A01A_NORON = 0x13;   // Normal Display Mode On
        static const uint8_t GC9A01A_INVOFF = 0x20;  // Display Inversion Off
        static const uint8_t GC9A01A_INVON = 0x21;   // Display Inversion On
        static const uint8_t GC9A01A_DISPOFF = 0x28; // Display Off
        static const uint8_t GC9A01A_DISPON = 0x29;  // Display On
        static const uint8_t GC9A01A_CASET = 0x2A;   // Column Address Set
        static const uint8_t GC9A01A_RASET = 0x2B;   // Row Address Set
        static const uint8_t GC9A01A_RAMWR = 0x2C;   // Memory Write
        static const uint8_t GC9A01A_MADCTL = 0x36;  // Memory Access Control
        static const uint8_t GC9A01A_COLMOD = 0x3A;  // Pixel Format Set

        // Memory Access Control bits
        static const uint8_t GC9A01A_MADCTL_MY = 0x80;  // Row Address Order
        static const uint8_t GC9A01A_MADCTL_MX = 0x40;  // Column Address Order
        static const uint8_t GC9A01A_MADCTL_MV = 0x20;  // Row/Column Exchange
        static const uint8_t GC9A01A_MADCTL_ML = 0x10;  // Vertical Refresh Order
        static const uint8_t GC9A01A_MADCTL_BGR = 0x08; // RGB-BGR Order
        static const uint8_t GC9A01A_MADCTL_MH = 0x04;  // Horizontal Refresh Order

        class GC9A01ADisplay : public display::DisplayBuffer,
                               public spi::SPIDevice<spi::BIT_ORDER_MSB_FIRST, spi::CLOCK_POLARITY_LOW,
                                                     spi::CLOCK_PHASE_LEADING, spi::DATA_RATE_40MHZ>
        {
        public:
            void set_dc_pin(GPIOPin *dc_pin) { this->dc_pin_ = dc_pin; }
            void set_reset_pin(GPIOPin *reset_pin) { this->reset_pin_ = reset_pin; }
            void set_backlight_pin(GPIOPin *backlight_pin) { this->backlight_pin_ = backlight_pin; }

            // PollingComponent interface
            void setup() override;
            void update() override;
            void dump_config() override;
            float get_setup_priority() const override;

            // DisplayBuffer interface
            void fill(Color color) override;
            void draw_absolute_pixel_internal(int x, int y, Color color) override;
            int get_height_internal() override;
            int get_width_internal() override;
            display::DisplayType get_display_type() override;

        protected:
            void init_display_();
            void set_addr_window_(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2);
            void write_command_(uint8_t cmd);
            void write_data_(uint8_t data);
            void write_data_16_(uint16_t data);
            void write_color_(uint16_t color, uint32_t count);
            uint16_t color_to_565_(Color color);
            void enable_();
            void disable_();

            GPIOPin *dc_pin_{nullptr};
            GPIOPin *reset_pin_{nullptr};
            GPIOPin *backlight_pin_{nullptr};
            bool is_ready_{false};
            uint32_t update_counter_{0}; // Counter to manage update intervals
        };

    } // namespace gc9a01a_display
} // namespace esphome