tuya = [e for e in hass.config_entries.async_entries("tuya") if e.state == "loaded"][0]
manager = tuya.runtime_data.manager

for dev_id, dev in manager.device_map.items():
    if "camera" in dev.category.lower():
        url = manager.get_device_stream_allocate(dev.id, "rtsp")
        logger.warning(f"{dev.name}: {url}")


        