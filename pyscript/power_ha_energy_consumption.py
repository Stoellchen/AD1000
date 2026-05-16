"""
pyscript: Power/Energy Engine
Source of truth: sensor.device_power_normalized (attribute: devices dict)

Features:
- Create per-device sensors for power/voltage/current/expected power/health
- Integrate energy (kWh) for selected roles (consumer/diagnostic)
- Compute costs (today/month/total) with reset at midnight/month-start
- Create global totals and optional room totals
- Optional feeder comparison and anomaly counters

Requires:
- pyscript installed/enabled
"""
"""
POWER / ENERGY NORMALIZATION CONCEPT
===================================

This script normalizes power, energy and cost calculations across heterogeneous
devices and measurement topologies.

Core idea:
----------
Not every power-measuring device represents actual energy consumption.
Some devices measure upstream supply (feeders), some represent end consumers,
and others are used only for diagnostics.

To avoid double-counting energy, devices are classified by role.

Device roles:
-------------

1) CONSUMER
   - Represents an actual energy-consuming device.
   - Its power is integrated into energy (kWh).
   - Energy contributes to room, total and cost calculations.
   - Example: lamps, plugs, appliances.

2) FEEDER
   - Measures upstream or aggregated power (e.g. room circuits, mains, TV power rail).
   - Power is monitored and validated, but NOT integrated into energy totals.
   - Used for plausibility checks, comparisons and diagnostics.
   - Prevents double-counting when downstream consumers exist.

3) DIAGNOSTIC
   - Provides electrical measurements only (voltage, current, power).
   - Never contributes to energy or cost calculations.
   - Used for health monitoring and debugging.

Energy integration:
-------------------
Energy (kWh) is derived from power (W) over time using discrete integration:
    energy += power * delta_time

Only devices with role == CONSUMER are integrated.

Costs:
------
Costs are calculated from integrated energy using a configurable price_per_kwh.
The following counters exist:
    - today
    - month
    - year
    - total (lifetime of the device)

Reset rules:
------------
- today   resets at local midnight
- month   resets on month change
- year    resets on year change
- total   never resets automatically

Expected power:
---------------
Expected power is calculated as:
    expected_power = voltage * current

It is used to detect implausible measurements and physics anomalies.

Important design rule:
----------------------
Room and total energy values are derived ONLY from CONSUMERS.
FEEDERS must never be summed into totals.

This ensures:
- no double-counting
- physically plausible results
- scalability across mixed measurement setups
"""


from datetime import datetime, timedelta, timezone
import math
import re
import json


log.warning("pwr ENGINE: script loaded")

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

CFG = {
    # Source sensor with the normalized device dict
    "source_entity": "sensor.device_power_normalized",
    "source_attr": "devices",

    # Prefix for generated sensors
    "prefix": "energy",

    # Update interval (seconds)
    "update_period_s": 60,

    # Energy integration settings
    # Integrate kWh for these roles:
    # - consumer: yes (count in totals)
    # - diagnostic: yes (but excluded from totals by default)
    # - feeder: no (never integrate; it's a reference)
    "integrate_roles": {"consumer", "diagnostic"},  # derived from mapping below

    # Include diagnostic devices in global totals (usually no)
    "include_diagnostic_in_totals": False,

    # Power threshold: below this, ignore integration to reduce noise (W)
    "min_power_w_for_integration": 1.0,

    # Plausibility gating:
    # If True: only integrate energy when physics state is ok/unknown, not "bad"
    # (You might want False because power is often still correct even if current is off)
    "skip_integration_when_physics_bad": False,

    # Electricity price (CHF per kWh)
    # You can later replace with a sensor, see get_price_per_kwh()
    "price_per_kwh": 0.29,

    # Voltage alert thresholds
    "voltage_low_v": 210.0,
    "voltage_high_v": 235.0,
    "voltage_unknown_below_v": 50.0,  # treat 0..49 as unknown

    # Create per-room totals
    "enable_room_totals": True,

    # Keep some debug attributes on totals
    "debug": True,
}

# Role mapping (normalize your strings to stable internal roles)
ROLE_MAP = {
    "consumer": "consumer",
    "feeder": "feeder",
    "diagnostic": "diagnostic",
    "diagnostics": "diagnostic",  # your current value
    "unknown": "unknown",
    None: "unknown",
}

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def _now_local():
    # pyscript runs in HA environment; use HA local time via datetime.now()
    return datetime.now()

def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = s.replace("-", "_")
    s = s.replace(".", "")
    s = re.sub(r"[^a-z0-9_]", "", s)
    if not s:
        return "unknown"
    return s

def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def _get_source_devices_old1():
    st = state.get(CFG["source_entity"])
    if st is None:
        log.error(f"pwr ENGINE: source entity missing: {CFG['source_entity']}")
        return {}
    
    attrs = state.getattr(CFG["source_entity"]) or {}
    devs = attrs.get(CFG["source_attr"]) or {}

    if isinstance(devs, dict):
        return devs
    return {}

def _get_source_devices_old2():
    st = state.get(CFG["source_entity"])
    log.warning(f"pwr ENGINE: state={st}")

    attrs = state.getattr(CFG["source_entity"])
    log.warning(f"pwr ENGINE: attrs={attrs}")

    if not isinstance(attrs, dict):
        log.error("pwr ENGINE: attrs is not dict")
        return {}

    devs = attrs.get(CFG["source_attr"])
    log.warning(f"pwr ENGINE: devices attr={devs}")

    if isinstance(devs, dict):
        return devs

    log.error(f"pwr ENGINE: devices is not dict (type={type(devs)})")
    return {}



def _get_source_devices():
    """
    Read devices from sensor.device_power_normalized.attributes.devices

    Supported formats:
    - dict  (future-proof, if template is replaced)
    - JSON string (current template behavior)

    Returns:
    - dict[str, dict]
    """

    attrs = state.getattr(CFG["source_entity"]) or {}

    if CFG["source_attr"] not in attrs:
        log.error(f"pwr ENGINE: attribute '{CFG['source_attr']}' missing")
        return {}

    raw = attrs.get(CFG["source_attr"])

    # --- Case 1: already a dict (best case) ---
    if isinstance(raw, dict):
        log.debug("pwr ENGINE: devices attribute already dict")
        return raw

    # --- Case 2: JSON string (expected today) ---
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)

            if not isinstance(parsed, dict):
                log.error(
                    f"pwr ENGINE: parsed devices is {type(parsed)}, expected dict"
                )
                return {}

            log.debug(f"pwr ENGINE: parsed {len(parsed)} devices from JSON")
            return parsed

        except json.JSONDecodeError as e:
            log.error(f"pwr ENGINE: JSON decode failed: {e}")
            log.error(f"pwr ENGINE: raw devices string (truncated): {raw[:200]}...")
            return {}

        except Exception as e:
            log.error(f"pwr ENGINE: unexpected parse error: {e}")
            return {}

    # --- Case 3: unsupported type ---
    log.error(
        f"pwr ENGINE: unsupported devices attribute type: {type(raw)}"
    )
    return {}


def _get_price_per_kwh():
    # Future: read from a sensor, e.g. sensor.electricity_price
    return float(CFG["price_per_kwh"])

def _entity_id(*parts):
    # sensor.<prefix>_<...>
    base = "_".join([p for p in parts if p])
    return f"sensor.{CFG['prefix']}_{base}"

def _set_sensor(entity_id, value, attrs=None):
    if attrs is None:
        attrs = {}
    state.set(entity_id, value, attrs)

def _get_prev_float(entity_id, default=0.0):
    try:
        v = state.get(entity_id)
        return float(v)
    except Exception:
        return default

def _get_prev_ts(entity_id):
    # store last update timestamp in attributes
    attrs = state.getattr(entity_id) or {}
    return attrs.get("last_update_ts")

def _set_last_ts(attrs, ts):
    attrs["last_update_ts"] = ts

def _is_new_day(prev_dt: datetime, now_dt: datetime) -> bool:
    return (prev_dt.date() != now_dt.date())

def _is_new_month(prev_dt: datetime, now_dt: datetime) -> bool:
    return (prev_dt.year != now_dt.year) or (prev_dt.month != now_dt.month)

def _is_new_year(prev_dt: datetime, now_dt: datetime) -> bool:
    return prev_dt.year != now_dt.year

# -----------------------------------------------------------------------------
# CORE: update loop
# -----------------------------------------------------------------------------




@time_trigger("cron(*/1 * * * * )")        # jede Minute
def power_engine_update():
    log.warning("pwr ENGINE: trigger fired")
    now = _now_local()
    now_ts = now.timestamp()
    devices = _get_source_devices()
    log.warning(f"pwr ENGINE: update tick, devices={len(devices)}")

    log.debug(
    f"pwr ENGINE: source devices type={type(devices)}, count={len(devices)}"
    )      

    # Totals
    total_power_w = 0.0
    total_energy_kwh = 0.0
    total_cost_today = 0.0
    total_cost_month = 0.0
    total_cost_total = 0.0

    bad_physics_count = 0
    voltage_alert_count = 0
    missing_voltage_count = 0
    missing_current_count = 0

    # Room totals
    room_totals = {}  # room_slug -> dict

    price = _get_price_per_kwh()

    # Iterate devices dict from normalized sensor
    for key, d in devices.items():
        log.debug(f"pwr ENGINE: start device '{key}'")
        dev_key = _slug(key)  # key already slugged in your template, but safe
        log.debug(f"pwr ENGINE: device slug='{dev_key}'")

        try:

            dev_name = d.get("device") or dev_key
            room = d.get("room") or "Unknown"
            room_key = _slug(room)

            role_raw = d.get("power_role")
            role = ROLE_MAP.get(role_raw, "unknown")

            power = _safe_float(d.get("power"), 0.0)
            voltage = _safe_float(d.get("voltage"), None)
            current = _safe_float(d.get("current"), None)
            expected = _safe_float(d.get("expected_power"), None)


            log.debug(
                f"pwr ENGINE: device='{key}', role={role}, power={power}"
            )

            phys_state = d.get("power_physical_state") or "unknown"
            phys_ok = bool(d.get("power_physical_ok", False))

            v_state = d.get("voltage_state") or "unknown"
            v_ok = bool(d.get("voltage_ok", False))

            src_power = d.get("source_power")
            src_voltage = d.get("source_voltage")
            src_current = d.get("source_current")

            # health counters
            if phys_state == "bad":
                bad_physics_count += 1
            if v_state in ("low", "high"):
                voltage_alert_count += 1
            if voltage is None or (voltage is not None and voltage < CFG["voltage_unknown_below_v"]):
                missing_voltage_count += 1
            if current is None:
                missing_current_count += 1

            # --- Create per-device measurement sensors (always) ---
            base_attrs = {
                "device_name": dev_name,
                "room": room,
                "role": role,
                "source_power": src_power,
                "source_voltage": src_voltage,
                "source_current": src_current,
                "voltage_state": v_state,
                "voltage_ok": v_ok,
                "physics_state": phys_state,
                "physics_ok": phys_ok,
                "price_per_kwh": price,
                "last_seen_ts": now_ts,
            }

            # ---- Mess-Sensoren ----
            log.debug(f"pwr ENGINE: creating measurement sensors for '{key}'")

            _set_sensor(
                _entity_id(dev_key, "power_w"),
                round(power, 3),
                {
                    **base_attrs,
                    "unit_of_measurement": "W",
                    "device_class": "power",
                    "state_class": "measurement",
                },
            )

            _set_sensor(
                _entity_id(dev_key, "voltage_v"),
                None if voltage is None else round(voltage, 2),
                {
                    **base_attrs,
                    "unit_of_measurement": "V",
                    "device_class": "voltage",
                    "state_class": "measurement",
                },
            )

            _set_sensor(
                _entity_id(dev_key, "current_a"),
                None if current is None else round(current, 3),
                {
                    **base_attrs,
                    "unit_of_measurement": "A",
                    "device_class": "current",
                    "state_class": "measurement",
                },
            )

            _set_sensor(
                _entity_id(dev_key, "expected_power_w"),
                None if expected is None else round(expected, 3),
                {
                    **base_attrs,
                    "unit_of_measurement": "W",
                    "device_class": "power",
                    "state_class": "measurement",
                },
            )

            # --- Energy integration + costs (role-gated) ---
            do_integrate = role in CFG["integrate_roles"]

            # feeders: never integrate
            # unknown: default no
            if role in ("feeder", "unknown"):
                do_integrate = False

            # optional physics gating
            if CFG["skip_integration_when_physics_bad"] and phys_state == "bad":
                do_integrate = False

            # ignore tiny power
            if power < CFG["min_power_w_for_integration"]:
                do_integrate = False

            # Per-device energy entity
            e_ent       = _entity_id(dev_key, "energy_kwh")
            c_today_ent = _entity_id(dev_key, "cost_today")
            c_month_ent = _entity_id(dev_key, "cost_month")
            c_total_ent = _entity_id(dev_key, "cost_total")
            #year 
            e_year_ent = _entity_id(dev_key, "energy_year_kwh")
            c_year_ent = _entity_id(dev_key, "cost_year")


            # Reset logic uses stored timestamps on the cost sensors
            prev_ts = _get_prev_ts(c_today_ent)
            prev_dt = None
            if prev_ts:
                try:
                    prev_dt = datetime.fromtimestamp(float(prev_ts))
                except Exception:
                    prev_dt = None

            # default previous dt: now (no reset)
            if prev_dt is None:
                prev_dt = now

            # If new day/month -> reset day/month counters
            reset_day = _is_new_day(prev_dt, now)
            reset_month = _is_new_month(prev_dt, now)
            reset_year = _is_new_year(prev_dt, now)

            # get previous values
            log.debug(f"pwr ENGINE: energy block for 1111 '{key}'")
            prev_energy = _get_prev_float(e_ent, 0.0)
            prev_cost_today = 0.0 if reset_day else _get_prev_float(c_today_ent, 0.0)
            prev_cost_month = 0.0 if reset_month else _get_prev_float(c_month_ent, 0.0)
            #year
            prev_energy_year = 0.0 if reset_year else _get_prev_float(e_year_ent, 0.0)
            prev_cost_year   = 0.0 if reset_year else _get_prev_float(c_year_ent, 0.0)            
            prev_cost_total = _get_prev_float(c_total_ent, 0.0)

            # integrate (trapezoid-like using last update time; we store last_update_ts on energy sensor)
            last_e_ts = _get_prev_ts(e_ent)
            if last_e_ts:
                try:
                    dt_s = max(0.0, now_ts - float(last_e_ts))
                except Exception:
                    dt_s = float(CFG["update_period_s"])
            else:
                dt_s = float(CFG["update_period_s"])

            if do_integrate:
                # kWh increment = W * s / (1000 * 3600)
                inc_kwh = (power * dt_s) / 3_600_000.0
            else:
                inc_kwh = 0.0

            new_energy = prev_energy + inc_kwh
            inc_cost = inc_kwh * price

            new_cost_today = prev_cost_today + inc_cost
            new_cost_month = prev_cost_month + inc_cost
            new_cost_total = prev_cost_total + inc_cost

            new_energy_year = prev_energy_year + inc_kwh        #year 
            new_cost_year   = prev_cost_year + inc_cost         #year
            log.debug(f"pwr ENGINE: energy OK for '{key}'")

            # write energy + costs
            e_attrs = {
                **base_attrs,
                "unit_of_measurement": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing",
                "integrated": do_integrate,
                "dt_s": round(dt_s, 2),
            }
            _set_last_ts(e_attrs, now_ts)
            _set_sensor(e_ent, round(new_energy, 6), e_attrs)

            # year
            e_attrs = {
                **base_attrs,
                "unit_of_measurement": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing",
                "dt_s": round(dt_s, 2),
            }
            _set_last_ts(e_attrs, now_ts)
            _set_sensor(e_year_ent, round(new_energy_year, 6), e_attrs)

            cost_attrs = {
                **base_attrs,
                "unit_of_measurement": "CHF",
                "state_class": "total",  # not a strict HA class, but ok for display
                "integrated": do_integrate,
            }
            _set_last_ts(cost_attrs, now_ts)
            log.debug(f"pwr ENGINE: set_sensor_start for '{key}'")
            _set_sensor(c_today_ent, round(new_cost_today, 6), cost_attrs)
            _set_sensor(c_month_ent, round(new_cost_month, 6), cost_attrs)
            _set_sensor(c_total_ent, round(new_cost_total, 6), cost_attrs)

            # year
            c_attrs = {
                **base_attrs,
                "unit_of_measurement": "CHF",
                "state_class": "total",
            }
            _set_last_ts(cost_attrs, now_ts)
            _set_sensor(c_year_ent, round(new_cost_year, 6), c_attrs)
            log.debug(f"pwr ENGINE: set_sensor_start OK for '{key}'")

            # --- Totals (role gated) ---
            include_in_totals = (role == "consumer") or (CFG["include_diagnostic_in_totals"] and role == "diagnostic")

            if include_in_totals:
                total_power_w += power
                total_energy_kwh += inc_kwh  # integrate sum incrementally
                total_cost_today += inc_cost
                total_cost_month += inc_cost
                total_cost_total += inc_cost

                new_energy_year = prev_energy_year + total_energy_kwh
                new_cost_year   = prev_cost_year + total_cost_today

            # --- Room totals (optional, only totals-included devices) ---
            if CFG["enable_room_totals"] and include_in_totals:
                rt = room_totals.get(room_key) or {
                    "room": room,
                    "power_w": 0.0,
                    "energy_kwh_inc": 0.0,
                    "cost_inc": 0.0,
                    "devices": 0,
                }
                rt["power_w"] += power
                rt["energy_kwh_inc"] += inc_kwh
                rt["cost_inc"] += inc_cost
                rt["devices"] += 1
                room_totals[room_key] = rt


        except Exception as e:
            log.error(
                f"pwr ENGINE: device '{key}' failed: {e}",
                exc_info=True
            )
            continue


    # --- Write global totals ---
    # Total energy/cost should be cumulative, so we store persistent totals like per device
    tot_e_ent = _entity_id("total", "energy_kwh")
    tot_ct_ent = _entity_id("total", "cost_today")
    tot_cm_ent = _entity_id("total", "cost_month")
    tot_c_ent = _entity_id("total", "cost_total")

    # total year
    tot_ey_ent = _entity_id("total", "energy_year_kwh")
    tot_cy_ent = _entity_id("total", "cost_year")
    prev_energy_year = 0.0 if reset_year else _get_prev_float(tot_ey_ent, 0.0)
    prev_cost_year   = 0.0 if reset_year else _get_prev_float(tot_cy_ent, 0.0)
    new_energy_year = prev_energy_year + total_energy_kwh
    new_cost_year   = prev_cost_year + total_cost_today
    _set_sensor(tot_ey_ent, round(new_energy_year, 6), e_attrs)
    _set_sensor(tot_cy_ent, round(new_cost_year, 6), c_attrs)

    # reset logic for totals based on cost_today timestamp
    prev_ts = _get_prev_ts(tot_ct_ent)
    prev_dt = datetime.fromtimestamp(float(prev_ts)) if prev_ts else now
    reset_day = _is_new_day(prev_dt, now)
    reset_month = _is_new_month(prev_dt, now)

    prev_tot_energy = _get_prev_float(tot_e_ent, 0.0)
    prev_tot_cost_today = 0.0 if reset_day else _get_prev_float(tot_ct_ent, 0.0)
    prev_tot_cost_month = 0.0 if reset_month else _get_prev_float(tot_cm_ent, 0.0)
    prev_tot_cost_total = _get_prev_float(tot_c_ent, 0.0)

    # accumulate incremental totals
    new_tot_energy = prev_tot_energy + total_energy_kwh
    new_tot_cost_today = prev_tot_cost_today + total_cost_today
    new_tot_cost_month = prev_tot_cost_month + total_cost_month
    new_tot_cost_total = prev_tot_cost_total + total_cost_total

    _set_sensor(
        _entity_id("total", "power_w"),
        round(total_power_w, 3),
        {
            "unit_of_measurement": "W",
            "device_class": "power",
            "state_class": "measurement",
            "price_per_kwh": price,
            "devices_included": "consumer" + (" + diagnostic" if CFG["include_diagnostic_in_totals"] else ""),
            "last_seen_ts": now_ts,
        },
    )

    e_attrs = {
        "unit_of_measurement": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "price_per_kwh": price,
        "last_seen_ts": now_ts,
    }
    _set_last_ts(e_attrs, now_ts)
    _set_sensor(tot_e_ent, round(new_tot_energy, 6), e_attrs)

    cost_attrs = {
        "unit_of_measurement": "CHF",
        "price_per_kwh": price,
        "last_seen_ts": now_ts,
    }
    _set_last_ts(cost_attrs, now_ts)
    _set_sensor(tot_ct_ent, round(new_tot_cost_today, 6), cost_attrs)
    _set_sensor(tot_cm_ent, round(new_tot_cost_month, 6), cost_attrs)
    _set_sensor(tot_c_ent, round(new_tot_cost_total, 6), cost_attrs)

    # --- Health sensors ---
    _set_sensor(_entity_id("health", "bad_physics_count"), bad_physics_count, {"unit_of_measurement": "count"})
    _set_sensor(_entity_id("health", "voltage_alert_count"), voltage_alert_count, {"unit_of_measurement": "count"})
    _set_sensor(_entity_id("health", "missing_voltage_count"), missing_voltage_count, {"unit_of_measurement": "count"})
    _set_sensor(_entity_id("health", "missing_current_count"), missing_current_count, {"unit_of_measurement": "count"})

    # --- Room totals ---
    if CFG["enable_room_totals"]:
        for rkey, rt in room_totals.items():
            _set_sensor(
                _entity_id("room", rkey, "power_w"),
                round(rt["power_w"], 3),
                {
                    "unit_of_measurement": "W",
                    "device_class": "power",
                    "state_class": "measurement",
                    "room": rt["room"],
                    "devices": rt["devices"],
                    "last_seen_ts": now_ts,
                },
            )

            # room energy/cost are cumulative like totals
            room_e_ent = _entity_id("room", rkey, "energy_kwh")
            room_ct_ent = _entity_id("room", rkey, "cost_today")
            room_cm_ent = _entity_id("room", rkey, "cost_month")
            room_c_ent = _entity_id("room", rkey, "cost_total")

            prev_ts = _get_prev_ts(room_ct_ent)
            prev_dt = datetime.fromtimestamp(float(prev_ts)) if prev_ts else now
            reset_day = _is_new_day(prev_dt, now)
            reset_month = _is_new_month(prev_dt, now)

            prev_e = _get_prev_float(room_e_ent, 0.0)
            prev_ct = 0.0 if reset_day else _get_prev_float(room_ct_ent, 0.0)
            prev_cm = 0.0 if reset_month else _get_prev_float(room_cm_ent, 0.0)
            prev_c = _get_prev_float(room_c_ent, 0.0)

            new_e = prev_e + rt["energy_kwh_inc"]
            new_ct = prev_ct + rt["cost_inc"]
            new_cm = prev_cm + rt["cost_inc"]
            new_c = prev_c + rt["cost_inc"]

            e_attrs = {"unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing", "room": rt["room"]}
            _set_last_ts(e_attrs, now_ts)
            _set_sensor(room_e_ent, round(new_e, 6), e_attrs)

            c_attrs = {"unit_of_measurement": "CHF", "room": rt["room"]}
            _set_last_ts(c_attrs, now_ts)
            _set_sensor(room_ct_ent, round(new_ct, 6), c_attrs)
            _set_sensor(room_cm_ent, round(new_cm, 6), c_attrs)
            _set_sensor(room_c_ent, round(new_c, 6), c_attrs)







            