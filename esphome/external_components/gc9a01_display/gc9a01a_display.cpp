#include "gc9a01a_display.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/core/color.h"

namespace esphome
{
    namespace gc9a01a_display
    {

        static const char *const TAG = "gc9a01a_display";
        void GC9A01ADisplay::setup()
        {

            // Critical: Initialize SPI delegate for device communication
            // SPIDevice starts with a dummy delegate that only logs errors
            // spi_setup() replaces the dummy with a functional delegate from the SPI component
            // Without this call, all SPI operations fail with "SPIDevice not initialised" error
            // See: SPIClient::spi_setup() -> register_device() for delegate replacement
            this->spi_setup();

            // Critical: Configure DC pin as hardware output
            // ESPHome sets pin flags during YAML parsing, but setup() applies them to ESP32 GPIO registers
            // Without this call, the pin remains unconfigured and digital_write() will fail
            // See: ESP32InternalGPIOPin::setup() -> gpio_config() for hardware initialization
            this->dc_pin_->setup();

            // Explicitly setup backlight pin if provided
            // This is optional, but recommended for displays with backlight control
            if (this->backlight_pin_ != nullptr)
            {
                this->backlight_pin_->setup();
                this->backlight_pin_->digital_write(true);
            }

            // Initialize display
            this->init_display_();

            // Set ready state
            this->is_ready_ = true;

            // Test with red fill
            Color red_color = Color(255, 0, 0, 0); // Red, Green, Blue
            this->fill(red_color);
        }

        void GC9A01ADisplay::update()
        {

            if (!this->is_ready_)
            {
                ESP_LOGW(TAG, "Display not ready, skipping update");
                return;
            }

            if (this->get_component_state() == 0x03)
            {
                ESP_LOGE(TAG, "SPI component setup failed");
                return;
            }

            static bool gpio_diagnostics_done = false;
            static uint32_t test_delay_counter = 0;
            static bool initial_dc_state = false;

            if (!gpio_diagnostics_done)
            {
                test_delay_counter++;

                if (test_delay_counter == 20)
                {

                    ESP_LOGD(TAG, "Starting SPI transaction test");

                    this->enable();

                    // Test write operation
                    uint8_t test_cmd = 0x9F; // Example: Read ID command
                    this->write_byte(test_cmd);
                    ESP_LOGD(TAG, "Sent command: 0x%02X", test_cmd);

                    // Test read operation
                    uint8_t buffer[3];
                    this->read_array(buffer, sizeof(buffer));
                    ESP_LOGD(TAG, "Read response: 0x%02X 0x%02X 0x%02X",
                             buffer[0], buffer[1], buffer[2]);

                    this->disable();
                    ESP_LOGD(TAG, "SPI transaction test complete");
                }
                else if (test_delay_counter < 20)
                {
                    ESP_LOGI(TAG, "GPIO test countdown: %d updates until start", 20 - test_delay_counter);
                }
            }

            // ESPHome DisplayBuffer Integration Control:
            //
            // The do_update_() call is the bridge between ESPHome's high-level drawing framework
            // and our low-level hardware control methods. Here's how it works:
            //
            // WITH YAML lambda content (e.g., it.print(), it.line(), etc.):
            //   1. ESPHome draws to internal DisplayBuffer pixel array
            //   2. do_update_() compares current buffer with previous frame
            //   3. For each changed pixel, calls draw_absolute_pixel_internal(x, y, color)
            //   4. Our implementation converts pixels to GC9A01A hardware commands
            //   5. Result: YAML drawing commands appear on physical display
            //
            // WITHOUT YAML lambda content (current state):
            //   1. DisplayBuffer remains empty (no drawing commands executed)
            //   2. do_update_() finds zero changed pixels
            //   3. draw_absolute_pixel_internal() is never called
            //   4. No visual effect - call is redundant
            //
            // CURRENT TROUBLESHOOTING STRATEGY:
            //   - Focus on direct C++ hardware methods (fill(), write_color_(), etc.)
            //   - Verify SPI communication and display controller before ESPHome integration
            //   - All current visual output comes from setup() -> fill(red_color)
            //   - Once hardware is proven working, re-enable for YAML lambda support
            //
            // Temporarily disabled while troubleshooting direct hardware methods
            // this->do_update_();

            // Diagnostic logging every 20 updates
            this->update_counter_++;

            if (this->update_counter_ % 20 == 0)
            {
                ESP_LOGI(TAG, "=== Diagnostic Report (Update #%d) ===", this->update_counter_);
                ESP_LOGI(TAG, "Component Status:");
                ESP_LOGI(TAG, "  Ready State: %s", this->is_ready_ ? "true" : "false");
                ESP_LOGI(TAG, "  Display Dimensions: %dx%d", this->get_width_internal(), this->get_height_internal());
                ESP_LOGI(TAG, "  Display Type: %d", (int)this->get_display_type());

                // Add backlight pin diagnostics here:
                ESP_LOGI(TAG, "Backlight Pin Status:");
                if (this->backlight_pin_ != nullptr)
                {
                    bool backlight_state = this->backlight_pin_->digital_read();

                    ESP_LOGI(TAG, "  Pin Configured: YES");
                    ESP_LOGI(TAG, "  Pin Info: %s", this->backlight_pin_->dump_summary().c_str());
                    ESP_LOGI(TAG, "  Current State: %s", backlight_state ? "HIGH" : "LOW");

                    // Test if it's an internal pin for more details
                    if (this->backlight_pin_->is_internal())
                    {
                        InternalGPIOPin *internal_pin = static_cast<InternalGPIOPin *>(this->backlight_pin_);
                        ESP_LOGI(TAG, "  Pin Number: %d", internal_pin->get_pin());
                        ESP_LOGI(TAG, "  Is Inverted: %s", internal_pin->is_inverted() ? "YES" : "NO");
                    }

                    // Test writing again to confirm:
                    ESP_LOGI(TAG, "  Testing: Setting pin HIGH again...");
                    this->backlight_pin_->digital_write(true);
                    delay(10); // Small delay
                    bool new_state = this->backlight_pin_->digital_read();
                    ESP_LOGI(TAG, "  After write(true): %s", new_state ? "HIGH" : "LOW");

                    if (backlight_state)
                    {
                        ESP_LOGI(TAG, "  Status: CORRECT - Backlight should be illuminated");
                    }
                    else
                    {
                        ESP_LOGW(TAG, "  Status: PROBLEM - Backlight pin is LOW, display may be dark");
                    }
                }
                else
                {
                    ESP_LOGW(TAG, "  Pin Configured: NO - backlight_pin_ is nullptr");
                    ESP_LOGW(TAG, "  Status: PROBLEM - No backlight control available");
                }

                ESP_LOGI(TAG, "=== End Diagnostic Report ===");
            }
        }

        void GC9A01ADisplay::dump_config()
        {
            ESP_LOGCONFIG(TAG, "GC9A01A Display:");
            LOG_PIN("  DC Pin: ", this->dc_pin_);
            LOG_PIN("  Reset Pin: ", this->reset_pin_);
            LOG_PIN("  Backlight Pin: ", this->backlight_pin_);
            ESP_LOGCONFIG(TAG, "  Width: %d, Height: %d", this->get_width_internal(), this->get_height_internal());
        }

        float GC9A01ADisplay::get_setup_priority() const
        {
            return setup_priority::HARDWARE; // Match ILI9XXX pattern
        }

        void GC9A01ADisplay::fill(Color color)
        {
            ESP_LOGI(TAG, "Fill called with color R:%d G:%d B:%d, ready: %s",
                     color.red, color.green, color.blue, this->is_ready_ ? "true" : "false");

            if (!this->is_ready_)
                return;

            uint16_t color565 = this->color_to_565_(color);
            ESP_LOGI(TAG, "Converted to RGB565: 0x%04X", color565);

            // Debug: Log what we're about to do
            ESP_LOGI(TAG, "Setting address window to full screen: 0,0 to %d,%d",
                     GC9A01A_WIDTH - 1, GC9A01A_HEIGHT - 1);

            this->set_addr_window_(0, 0, GC9A01A_WIDTH - 1, GC9A01A_HEIGHT - 1);

            ESP_LOGI(TAG, "Writing %d pixels of color 0x%04X",
                     GC9A01A_WIDTH * GC9A01A_HEIGHT, color565);

            this->write_color_(color565, GC9A01A_WIDTH * GC9A01A_HEIGHT);

            ESP_LOGI(TAG, "Fill operation complete");
        }

        void GC9A01ADisplay::draw_absolute_pixel_internal(int x, int y, Color color)
        {
            if (x < 0 || x >= this->get_width_internal() || y < 0 || y >= this->get_height_internal())
            {
                return;
            }

            if (!this->is_ready_)
            {
                ESP_LOGW(TAG, "Display not ready for pixel draw");
                return;
            }

            uint16_t color565 = this->color_to_565_(color);
            this->set_addr_window_(x, y, x, y);
            this->write_data_16_(color565);
        }

        int GC9A01ADisplay::get_height_internal() { return GC9A01A_HEIGHT; }

        int GC9A01ADisplay::get_width_internal() { return GC9A01A_WIDTH; }

        display::DisplayType GC9A01ADisplay::get_display_type() { return display::DisplayType::DISPLAY_TYPE_COLOR; }

        void GC9A01ADisplay::init_display_()
        {
            ESP_LOGD(TAG, "Initializing GC9A01A display...");

            // Software reset
            this->write_command_(GC9A01A_SWRESET);
            delay(120);

            // Sleep out
            this->write_command_(GC9A01A_SLPOUT);
            delay(120);

            // Pixel format: 16 bits per pixel (RGB565)
            this->write_command_(GC9A01A_COLMOD);
            this->write_data_(0x55);

            // Memory access control (rotation and color order)
            this->write_command_(GC9A01A_MADCTL);
            uint8_t madctl = GC9A01A_MADCTL_BGR; // Set BGR color order
            this->write_data_(madctl);

            // GC9A01A specific initialization sequence
            this->write_command_(0xEF);

            this->write_command_(0xEB);
            this->write_data_(0x14);

            this->write_command_(0xFE);
            this->write_command_(0xEF);

            this->write_command_(0xEB);
            this->write_data_(0x14);

            this->write_command_(0x84);
            this->write_data_(0x40);

            this->write_command_(0x85);
            this->write_data_(0xFF);

            this->write_command_(0x86);
            this->write_data_(0xFF);

            this->write_command_(0x87);
            this->write_data_(0xFF);

            this->write_command_(0x88);
            this->write_data_(0x0A);

            this->write_command_(0x89);
            this->write_data_(0x21);

            this->write_command_(0x8A);
            this->write_data_(0x00);

            this->write_command_(0x8B);
            this->write_data_(0x80);

            this->write_command_(0x8C);
            this->write_data_(0x01);

            this->write_command_(0x8D);
            this->write_data_(0x01);

            this->write_command_(0x8E);
            this->write_data_(0xFF);

            this->write_command_(0x8F);
            this->write_data_(0xFF);

            this->write_command_(0xB6);
            this->write_data_(0x00);
            this->write_data_(0x20);

            this->write_command_(0x36);
            this->write_data_(madctl);

            this->write_command_(0x3A);
            this->write_data_(0x05);

            this->write_command_(0x90);
            this->write_data_(0x08);
            this->write_data_(0x08);
            this->write_data_(0x08);
            this->write_data_(0x08);

            this->write_command_(0xBD);
            this->write_data_(0x06);

            this->write_command_(0xBC);
            this->write_data_(0x00);

            this->write_command_(0xFF);
            this->write_data_(0x60);
            this->write_data_(0x01);
            this->write_data_(0x04);

            this->write_command_(0xC3);
            this->write_data_(0x13);

            this->write_command_(0xC4);
            this->write_data_(0x13);

            this->write_command_(0xC9);
            this->write_data_(0x22);

            this->write_command_(0xBE);
            this->write_data_(0x11);

            this->write_command_(0xE1);
            this->write_data_(0x10);
            this->write_data_(0x0E);

            this->write_command_(0xDF);
            this->write_data_(0x21);
            this->write_data_(0x0C);
            this->write_data_(0x02);

            this->write_command_(0xF0);
            this->write_data_(0x45);
            this->write_data_(0x09);
            this->write_data_(0x08);
            this->write_data_(0x08);
            this->write_data_(0x26);
            this->write_data_(0x2A);

            this->write_command_(0xF1);
            this->write_data_(0x43);
            this->write_data_(0x70);
            this->write_data_(0x72);
            this->write_data_(0x36);
            this->write_data_(0x37);
            this->write_data_(0x6F);

            this->write_command_(0xF2);
            this->write_data_(0x45);
            this->write_data_(0x09);
            this->write_data_(0x08);
            this->write_data_(0x08);
            this->write_data_(0x26);
            this->write_data_(0x2A);

            this->write_command_(0xF3);
            this->write_data_(0x43);
            this->write_data_(0x70);
            this->write_data_(0x72);
            this->write_data_(0x36);
            this->write_data_(0x37);
            this->write_data_(0x6F);

            this->write_command_(0xED);
            this->write_data_(0x1B);
            this->write_data_(0x0B);

            this->write_command_(0xAE);
            this->write_data_(0x77);

            this->write_command_(0xCD);
            this->write_data_(0x63);

            this->write_command_(0x70);
            this->write_data_(0x07);
            this->write_data_(0x07);
            this->write_data_(0x04);
            this->write_data_(0x0E);
            this->write_data_(0x0F);
            this->write_data_(0x09);
            this->write_data_(0x07);
            this->write_data_(0x08);
            this->write_data_(0x03);

            this->write_command_(0xE8);
            this->write_data_(0x34);

            this->write_command_(0x62);
            this->write_data_(0x18);
            this->write_data_(0x0D);
            this->write_data_(0x71);
            this->write_data_(0xED);
            this->write_data_(0x70);
            this->write_data_(0x70);
            this->write_data_(0x18);
            this->write_data_(0x0F);
            this->write_data_(0x71);
            this->write_data_(0xEF);
            this->write_data_(0x70);
            this->write_data_(0x70);

            this->write_command_(0x63);
            this->write_data_(0x18);
            this->write_data_(0x11);
            this->write_data_(0x71);
            this->write_data_(0xF1);
            this->write_data_(0x70);
            this->write_data_(0x70);
            this->write_data_(0x18);
            this->write_data_(0x13);
            this->write_data_(0x71);
            this->write_data_(0xF3);
            this->write_data_(0x70);
            this->write_data_(0x70);

            this->write_command_(0x64);
            this->write_data_(0x28);
            this->write_data_(0x29);
            this->write_data_(0xF1);
            this->write_data_(0x01);
            this->write_data_(0xF1);
            this->write_data_(0x00);
            this->write_data_(0x07);

            this->write_command_(0x66);
            this->write_data_(0x3C);
            this->write_data_(0x00);
            this->write_data_(0xCD);
            this->write_data_(0x67);
            this->write_data_(0x45);
            this->write_data_(0x45);
            this->write_data_(0x10);
            this->write_data_(0x00);
            this->write_data_(0x00);
            this->write_data_(0x00);

            this->write_command_(0x67);
            this->write_data_(0x00);
            this->write_data_(0x3C);
            this->write_data_(0x00);
            this->write_data_(0x00);
            this->write_data_(0x00);
            this->write_data_(0x01);
            this->write_data_(0x54);
            this->write_data_(0x10);
            this->write_data_(0x32);
            this->write_data_(0x98);

            this->write_command_(0x74);
            this->write_data_(0x10);
            this->write_data_(0x85);
            this->write_data_(0x80);
            this->write_data_(0x00);
            this->write_data_(0x00);
            this->write_data_(0x4E);
            this->write_data_(0x00);

            this->write_command_(0x98);
            this->write_data_(0x3E);
            this->write_data_(0x07);

            this->write_command_(GC9A01A_INVON); // Display inversion on
            delay(10);

            this->write_command_(GC9A01A_NORON); // Normal display mode on
            delay(10);

            this->write_command_(GC9A01A_DISPON); // Display on
            delay(120);

            ESP_LOGD(TAG, "GC9A01A display initialization complete");
        }

        void GC9A01ADisplay::set_addr_window_(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2)
        {
            this->write_command_(GC9A01A_CASET); // Column address set
            this->write_data_16_(x1);
            this->write_data_16_(x2);

            this->write_command_(GC9A01A_RASET); // Row address set
            this->write_data_16_(y1);
            this->write_data_16_(y2);

            this->write_command_(GC9A01A_RAMWR); // Write to RAM
        }

        void GC9A01ADisplay::write_command_(uint8_t cmd)
        {
            ESP_LOGV(TAG, "Writing command: 0x%02X", cmd);

            // Standard SPI display protocol sequence verified in ESPHome codebase:
            // 1. All ESPHome display components (ST7789, ILI9XXX, etc.) use this exact pattern
            // 2. DC pin must be stable BEFORE CS assertion per SPI display timing requirements
            // 3. ESP32 gpio_set_level() provides immediate hardware pin control for proper setup/hold times
            // 4. Each transaction is atomic: DC->CS->DATA->CS ensures clean command/data separation
            // Pattern aligned with how SPI is sequenced and timed in working Arduino code:
            this->dc_pin_->digital_write(false); // 1. DC pin FIRST (command mode)
            this->enable_();                     // 2. CS pin SECOND (select device)
            this->write_byte(cmd);               // 3. Send command
            this->disable_();                    // 4. CS pin release (deselect device)
        }

        void GC9A01ADisplay::write_data_(uint8_t data)
        {
            ESP_LOGV(TAG, "Writing data: 0x%02X", data);

            // Standard SPI display protocol sequence verified in ESPHome codebase:
            // 1. All ESPHome display components (ST7789, ILI9XXX, etc.) use this exact pattern
            // 2. DC pin must be stable BEFORE CS assertion per SPI display timing requirements
            // 3. ESP32 gpio_set_level() provides immediate hardware pin control for proper setup/hold times
            // 4. Each transaction is atomic: DC->CS->DATA->CS ensures clean command/data separation
            // Pattern aligned with how SPI is sequenced and timed in working Arduino code:
            this->dc_pin_->digital_write(true); // 1. DC pin FIRST (data mode)
            this->enable_();                    // 2. CS pin SECOND (select device)
            this->write_byte(data);             // 3. Send data
            this->disable_();                   // 4. CS pin release (deselect device)
        }

        void GC9A01ADisplay::write_data_16_(uint16_t data)
        {
            this->dc_pin_->digital_write(true); // Set DC HIGH for data mode (consistent with write_data_() pattern)
            this->enable_();                    // Assert CS to start SPI transaction
            this->write_byte(data >> 8);        // Send high byte (bits 15-8) first - big-endian MSB transmission
            this->write_byte(data & 0xFF);      // Send low byte (bits 7-0) second - completes 16-bit value
            this->disable_();                   // Deassert CS to end transaction
        }

        void GC9A01ADisplay::write_color_(uint16_t color, uint32_t count)
        {
            // Fills a region of the display with the same color by writing multiple identical RGB565 pixels.

            this->dc_pin_->digital_write(true); // Set data mode (pixel data follows)
            this->enable_();                    // Start SPI transaction

            uint8_t color_high = color >> 8;  // Extract high byte of RGB565
            uint8_t color_low = color & 0xFF; // Extract low byte of RGB565

            for (uint32_t i = 0; i < count; i++) // Repeat for each pixel
            {
                this->write_byte(color_high); // Send high byte
                this->write_byte(color_low);  // Send low byte
            }

            this->disable_(); // End SPI transaction
        }

        uint16_t GC9A01ADisplay::color_to_565_(Color color)
        {
            // Use the same RGB565 conversion logic as ESPHome's official ColorUtil::color_to_565()
            // This ensures consistency with other ESPHome display components
            uint16_t red_color = (color.red * 31) / 255;     // Scale 8-bit red to 5-bit (0-31)
            uint16_t green_color = (color.green * 63) / 255; // Scale 8-bit green to 6-bit (0-63)
            uint16_t blue_color = (color.blue * 31) / 255;   // Scale 8-bit blue to 5-bit (0-31)

            // RGB565 format: RRRRR GGGGGG BBBBB
            // Red: bits 15-11, Green: bits 10-5, Blue: bits 4-0
            return (red_color << 11) | (green_color << 5) | blue_color;
        }

        void GC9A01ADisplay::enable_()
        {
            // Use SPIDevice base class CS pin control
            // The CS pin is automatically managed by the SPI device when write_byte() is called
            // within an enable()/disable() transaction block
            this->SPIDevice::enable();
        }

        void GC9A01ADisplay::disable_()
        {
            // Use SPIDevice base class CS pin control
            // Properly releases CS pin to end the SPI transaction
            this->SPIDevice::disable();
        }

    } // namespace gc9a01a_display
} // namespace esphome