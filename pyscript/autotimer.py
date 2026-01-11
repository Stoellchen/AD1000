from datetime import datetime

"""
AutoTimer – Pyscript Internals (Technical View)
==============================================

This file implements the complete AutoTimer runtime logic.
All timing, state tracking, and decisions happen here.


Global Constants
----------------
STATESTR = "pyscript.autotimer_status"
- Central state entity used to publish AutoTimer data to Home Assistant.
- The entity state holds a timestamp (HH:MM:SS).
- All per-device timer data is stored in the entity attributes.

TICK_SEC = 1
- Timer resolution in seconds.
- Each tick reduces remaining time by 1 second.


Internal Store Model
--------------------
The internal store is a dictionary keyed by entity_id:

{
  "switch.ll_dose_1": {
    "default_sec": 10800,
    "remaining_sec": 7321,
    "active": true
  },
  "light.w3": {
    "default_sec": 300,
    "remaining_sec": 120,
    "active": true
  }
}

This store is written into the attributes of pyscript.autotimer_status.


load_store()
------------
Reads the current AutoTimer store from pyscript.autotimer_status attributes.

Key behavior:
- Returns an empty dict if the state does not exist yet.
- Filters attributes strictly:
  only entries that are dicts AND contain "remaining_sec" are accepted.
- Prevents recursive attribute corruption or invalid keys.


save_store(store)
-----------------
Writes the store back into pyscript.autotimer_status.

Behavior:
- Sets the entity state to the current time (HH:MM:SS).
- Writes the full store as attributes.
- This guarantees UI updates and dashboard refreshes.


autotimer_init (startup trigger)
--------------------------------
Executed once at Home Assistant startup or reload.

Behavior:
- Ensures pyscript.autotimer_status exists.
- Initializes an empty store if missing.
- Does not overwrite existing data.


autotimer_register_defaults (service)
-------------------------------------
Registers default runtimes for all AutoTimer entities.

Input format:
[
  {"entity": "switch.ll_dose_1", "minutes": 180},
  {"entity": "light.w3", "minutes": 5}
]

Behavior:
- Called from YAML or automation during setup.
- Converts minutes → seconds.
- Initializes store entries if they don’t exist.
- Does NOT start timers.
- Does NOT turn devices on.


get_override_minutes()
---------------------
Reads the helper input_number.autotimer_helper.

Behavior:
- Returns an integer number of minutes.
- Returns 0 if:
  - helper is unavailable
  - value is invalid
  - value is <= 0

This value is used as a temporary runtime override.


autotimer_start (service)
------------------------
Starts or restarts a timer for one entity.

Logic:
1. Load store
2. Verify entity has a registered default_sec
3. Read helper override
4. If override > 0:
     - remaining time = override
     - default_sec is overwritten for this session
   Else:
     - remaining time = stored default_sec
5. Set:
     - remaining_sec
     - active = True
6. Save store
7. Turn the entity ON

Important:
- No time parameter is required.
- The helper value is always evaluated at start time.


autotimer_stop (service)
-----------------------
Stops a running timer and turns the entity off.

Behavior:
- remaining_sec → 0
- active → False
- Device is switched OFF
- Store is saved immediately


autotimer_tick (time trigger)
-----------------------------
Runs once per second (cron-based).

Behavior:
- Iterates over all stored entities
- Only processes entries where active == True
- Decrements remaining_sec
- When remaining_sec reaches 0:
    - active → False
    - entity is turned OFF
- Writes updated store only if something changed

This is the core countdown engine.


autotimer_manual_event (service)
--------------------------------
Handles manual ON/OFF actions detected outside AutoTimer.

Expected input:
- entity_id
- new_state ("on" or "off")

Logic:
- If entity is not managed → ignore
- Manual ON:
    - Start timer using default_sec
- Manual OFF:
    - Stop timer immediately

This allows:
- physical switches
- voice assistants
- external automations

to stay fully in sync with AutoTimer.


Design Summary
--------------
- One central state: pyscript.autotimer_status
- All logic lives in pyscript
- YAML only triggers services
- Dashboards only read attributes
- No input_datetime helpers
- No per-entity helpers
- Deterministic, debuggable, and scalable
"""

STATESTR = "pyscript.autotimer_status"
TICK_SEC = 1


def load_store():
    attrs = state.getattr(STATESTR)
    if not isinstance(attrs, dict):
        return {}

    # 🔒 nur echte Entity-Einträge übernehmen
    return {
        k: v for k, v in attrs.items()
        if isinstance(v, dict)
        and "remaining_sec" in v
    }


def save_store(store):
    ts = datetime.now().strftime("%H:%M:%S")
    state.set(STATESTR, ts, store)


@time_trigger("startup")
def autotimer_init():
    if state.get(STATESTR) is None:
        save_store({})
        log.info("AutoTimer: initialisiert")


@service
def autotimer_register_defaults(devices=None):
    """
    devices:
    [
      {"entity": "switch.ll_dose_1", "minutes": 180},
      {"entity": "light.w3", "minutes": 5}
    ]
    """
    if not devices:
        return

    store = load_store()
    devices = list(devices)  # Wrapper → list

    for d in devices:
        entity = d.get("entity")
        minutes = d.get("minutes")

        if not entity or not minutes:
            continue

        store.setdefault(entity, {})
        store[entity]["default_sec"] = int(minutes) * 60
        store[entity].setdefault("remaining_sec", 0)
        store[entity].setdefault("active", False)

    save_store(store)
    log.info("AutoTimer: defaults registriert")


def get_override_minutes():
    val = state.get("input_number.autotimer_helper")
    try:
        minutes = int(float(val))
        return minutes if minutes > 0 else 0
    except Exception:
        return 0


@service
def autotimer_start(entity_id=None):
    if not entity_id:
        return

    store = load_store()
    entry = store.get(entity_id)

    if not entry or "default_sec" not in entry:
        log.error(f"AutoTimer START: no default for {entity_id}")
        return

    override_min = get_override_minutes()
    if override_min > 0:
        remaining = override_min * 60
        entry["default_sec"] = remaining        # 🔥 WICHTIG: Default überschreiben
    else:
        remaining = entry["default_sec"]

    entry["remaining_sec"] = remaining
    entry["active"] = True

    save_store(store)
    service.call("homeassistant", "turn_on", entity_id=entity_id)



@service
def autotimer_stop(entity_id=None):
    if not entity_id:
        return

    store = load_store()
    entry = store.get(entity_id)
    if not entry:
        return

    entry["remaining_sec"] = 0
    entry["active"] = False

    save_store(store)
    service.call("homeassistant", "turn_off", entity_id=entity_id)


# @time_trigger("period(0:00:05)")
@time_trigger("cron(* * * * * *)")
def autotimer_tick():
    log.debug("AutoTimer TICK")
    store = load_store()
    changed = False

    for entity, entry in store.items():
        if not entry.get("active"):
            continue

        entry["remaining_sec"] -= 1

        if entry["remaining_sec"] <= 0:
            entry["remaining_sec"] = 0
            entry["active"] = False
            service.call("homeassistant", "turn_off", entity_id=entity)

        changed = True

    if changed:
        save_store(store)



@service
def autotimer_manual_event(entity_id=None, new_state=None):
    if not entity_id or new_state not in ("on", "off"):
        return

    store = load_store()
    entry = store.get(entity_id)
    if not entry:
        return

    # Manuell EIN → Timer starten
    if new_state == "on" and not entry.get("active"):
        entry["remaining_sec"] = entry["default_sec"]
        entry["active"] = True
        save_store(store)
        log.info(f"AutoTimer MANUAL ON → {entity_id}")

    # Manuell AUS → Timer stoppen
    elif new_state == "off" and entry.get("active"):
        entry["remaining_sec"] = 0
        entry["active"] = False
        save_store(store)
        log.info(f"AutoTimer MANUAL OFF → {entity_id}")