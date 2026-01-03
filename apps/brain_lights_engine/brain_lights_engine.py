################################################################################
# Brain Lights Engine (AppDaemon)
#
# Purpose
# - Context-aware motion lighting engine driven by an external config file.
# - Designed for live testing: decisions + real actions (turn on/off).
#
# Key features implemented for live test
# - Rooms -> Zones -> Contexts
# - Motion triggers per context
# - Optional enable/disable gate via binary_sensor per context (enable.sensor)
# - Time windows (supports overnight windows)
# - Lux threshold (lux.sensor + lux.below)
# - Optional presence gating (presence.entities + presence.require = any|all)
# - Context selection by priority (room.priority + context.priority)
# - Engine mode:
#     - exclusive: one active context per zone (new higher prio replaces)
#     - parallel: allow multiple active contexts (still tracked per zone key)
# - Reset timeout on motion (refresh timer)
# - Actions on activate:
#     - scene.turn_on
#     - light.turn_on (optional brightness/color/transition)
#     - switch.turn_on
# - Actions on timeout/deactivate:
#     - light.turn_off (with transition_off_sec)
#     - switch.turn_off
#
# Notes
# - Config file may be YAML or JSON; we load via yaml.safe_load (works for JSON too).
# - Keep config file OUTSIDE apps.yaml to avoid AppDaemon treating it as app config.
# - No umlauts in code/comments.
################################################################################

import appdaemon.plugins.hass.hassapi as hass
import yaml
import os
from datetime import datetime, timedelta

__version__ = "22 20251225 - 1310"

class BrainLightsEngine(hass.Hass):

    # -------------------------------------------------------------------------
    # INIT
    # -------------------------------------------------------------------------
    def initialize(self):
        self.log("BrainLightsEngine starting", level="INFO")

        # Load configuration file path from apps.yaml:
        # brain_lights_engine:
        #   module: brain_lights_engine
        #   class: BrainLightsEngine
        #   config_file: config/brain_lights_config.yaml
        config_rel = self.args.get("config_file")
        if not config_rel:
            self.log("[D1] Missing 'config_file' in apps.yaml for this app", level="ERROR")
            return

        self.config_path = os.path.join(os.path.dirname(__file__), config_rel)

        # Load config (YAML or JSON)
        try:
            with open(self.config_path, "r") as f:
                self.config = yaml.safe_load(f) or {}
        except Exception as e:
            self.log(f"[D1] Failed to load config '{self.config_path}': {e}", level="ERROR")
            return

        # Engine settings
        engine_cfg = self.config.get("engine", {}) or {}
        self.debug_level = int(engine_cfg.get("debug_level", 3))
        self.engine_mode = str(engine_cfg.get("mode", "exclusive")).lower()
        self.transition_off_multiplier = float(engine_cfg.get("transition_off_multiplier", 1.0))
        self.reset_timeout_on_motion = bool(engine_cfg.get("reset_timeout_on_motion", True))

        # Runtime state
        # active_contexts: key="room:zone" -> dict(context_id, ctx, since, prio)
        self.active_contexts = {}
        # timers: key="room:zone" -> AD handle
        self.timers = {}

        # Rooms
        self.rooms = self.config.get("rooms", {}) or {}

        self.dbg(2, f"Config file: {self.config_path}")
        self.dbg(2, f"Engine mode: {self.engine_mode}")
        self.dbg(2, f"Reset timeout on motion: {self.reset_timeout_on_motion}")
        self.dbg(2, f"transition off multiplier: {self.transition_off_multiplier}")
        self.dbg(2, f"Loaded rooms: {list(self.rooms.keys())}")

        # Register triggers
        self.register_all_triggers()

        # context ausgeben
        self._debug_dump_contexts()

        # Register circadian sensors
        self._register_circadian_sensors()

        # Periodic circadian reapply for active lights
        self.run_every(self._apply_circadian_to_active_lights, self.datetime() + timedelta(seconds=2), 60)

        # every minute status log
        self.run_every(self._log_active_contexts, self.datetime(), 60)

        self.log("BrainLightsEngine initialized", level="INFO")


    # -------------------------------------------------------------------------
    # Register circadian sensors
    # -------------------------------------------------------------------------
    def _register_circadian_sensors(self):
        """
        Register global circadian sensors and start periodic refresh.
        """

        # Circadian sensor references (global)
        self.circadian_refs = self.config.get("circadian_sensor", {}) or {}

        # Cached circadian values
        self.circadian_values = {}

        # Initial read
        self.update_circadian_values()

        # Periodic refresh every minute
        self.run_every(
            self.update_circadian_values,
            self.datetime() + timedelta(seconds=1),
            60
        )

    # -------------------------------------------------------------------------
    # update circadian sensors
    # -------------------------------------------------------------------------
    def update_circadian_values(self, kwargs=None):
        """
        Read all configured circadian sensors and cache their values.
        Supports entity.state and entity.attribute notation.
        """

        for key, ref in self.circadian_refs.items():

            value = None

            parts = ref.split(".")
            if len(parts) > 2 and parts[0] in (
                "sensor",
                "binary_sensor",
                "number",
                "input_number",
            ):
                entity_id = ".".join(parts[:-1])
                attribute = parts[-1]
                value = self.get_state(entity_id, attribute=attribute)
            else:
                value = self.get_state(ref)

            # Normalize numeric values
            try:
                # Normalize values
                if isinstance(value, (int, float)):
                    value = float(value)

                elif isinstance(value, (list, tuple)) and len(value) == 3:
                    # RGB value, keep as-is (cast to int)
                    value = tuple(int(v) for v in value)

                else:
                    # everything else is invalid
                    value = None
            except Exception:
                value = None

            self.circadian_values[key] = value

        # Optional debug
        if self.debug_level >= 4:
            self.dbg(4, f"Circadian values updated: {self.circadian_values}")




    # -------------------------------------------------------------------------
    # DEBUG
    # -------------------------------------------------------------------------
    def dbg(self, level, msg):
        if self.debug_level >= int(level):
            self.log(f"[D{int(level)}] {msg}")

    # -------------------------------------------------------------------------
    # REGISTER TRIGGERS
    # -------------------------------------------------------------------------
    def register_all_triggers(self):
        for room_name, room in (self.rooms or {}).items():
            zones = (room or {}).get("zones", {}) or {}
            if not zones:
                self.dbg(2, f"Room '{room_name}' has no zones")
                continue

            for zone_name, zone in zones.items():
                contexts = (zone or {}).get("contexts", []) or []
                if not contexts:
                    self.dbg(2, f"Room '{room_name}' zone '{zone_name}' has no contexts")
                    continue

                for ctx in contexts:
                    ctx_id = ctx.get("id")
                    triggers = ctx.get("triggers", []) or []
                    if not ctx_id:
                        self.dbg(1, f"Room '{room_name}' zone '{zone_name}' has context without id - skipped")
                        continue

                    for trig in triggers:
                        sensor = (trig or {}).get("sensor")
                        if not sensor:
                            continue

                        # Listen for motion "on"
                        self.listen_state(
                            self.on_trigger,
                            sensor,
                            new="on",
                            room=room_name,
                            zone=zone_name,
                            context_id=ctx_id,
                            trigger_entity=sensor
                        )

                        self.dbg(3, f"Registered trigger {sensor} -> {room_name}/{zone_name}/{ctx_id}")

    # -------------------------------------------------------------------------
    # TRIGGER HANDLER (DECISION + ACTION)
    # -------------------------------------------------------------------------
    def on_trigger(self, entity, attribute, old, new, kwargs):
        room_name = kwargs.get("room")
        zone_name = kwargs.get("zone")
        context_id = kwargs.get("context_id")
        trigger_entity = kwargs.get("trigger_entity", entity)

        key = f"{room_name}:{zone_name}"

        self.dbg(3, f"Trigger fired: {trigger_entity} -> key={key}, ctx={context_id}")

        # 🔎 MOTION / TRIGGER ENTRY DEBUG
        self.dbg(3, f"[TRIGGER] entity={entity} old={old} new={new} kwargs={kwargs}")


        room = (self.rooms or {}).get(room_name, {}) or {}
        zone = (room.get("zones", {}) or {}).get(zone_name, {}) or {}
        contexts = zone.get("contexts", []) or []

        # Find the context by id (this trigger is mapped to a single context)
        ctx = None
        for c in contexts:
            if (c or {}).get("id") == context_id:
                ctx = c
                break

        if not ctx:
            self.dbg(2, f"Context id '{context_id}' not found in {room_name}/{zone_name}")
            return

        # Hard disable via config flag
        if not self.is_context_activated(ctx):
            self.dbg(3, f"Context '{context_id}' disabled by activate flag")
            return

        # Step: hard enable/disable gate via binary_sensor
        if not self.is_context_enabled(ctx):
            self.dbg(3, f"Context '{context_id}' blocked by enable gate")
            return

        # Time window check
        if not self.check_time_window(ctx):
            self.dbg(4, f"CTX {ctx} rejected: time window")
            return

        # Lux check
        if not self.check_lux(ctx):
            self.dbg(4, f"CTX {ctx} rejected: lux")
            return

        # Presence check (optional)
        if not self.check_presence(ctx):
            self.dbg(4, f"CTX {ctx} rejected: presence")
            return

        # Optional "block_if_any_on": if any entity already on, skip adding more
        if self.blocked_by_entities_on(ctx):
            self.dbg(3, f"Context '{context_id}' blocked by block_if_any_on rule")
            return

        # Select / switch logic
        selected = ctx
        selected_prio = self.get_effective_priority(room, selected)

        # Engine mode exclusive: only one context per zone key.
        # If same key active, refresh or replace if higher priority.
        if key in self.active_contexts:
            active = self.active_contexts[key]
            active_id = active.get("context_id")
            active_prio = active.get("prio", 0)

            if active_id == selected.get("id"):
                self.dbg(2, f"Context '{active_id}' already active -> refresh")
                if self.reset_timeout_on_motion:
                    self.refresh_timer(key)
                return

            # Different context: only replace if higher priority
            if self.engine_mode == "exclusive":
                if selected_prio > active_prio:
                    self.dbg(1, f"Switch context {active_id} -> {selected.get('id')} (prio {active_prio} -> {selected_prio})")
                    self.deactivate_context(key, active.get("ctx"), reason="replaced")
                    self.activate_context(key, room_name, zone_name, selected, selected_prio)
                else:
                    self.dbg(2, f"Keep active context '{active_id}' (prio {active_prio}) over '{selected.get('id')}' (prio {selected_prio})")
                return

            # Parallel mode: we still track only one per key in this implementation
            # (to keep timers deterministic). If you want true parallel per key,
            # we would store a list and multiple timers.
            self.dbg(2, f"Parallel mode currently keeps one context per key; replacing '{active_id}' with '{selected.get('id')}'")
            self.deactivate_context(key, active.get("ctx"), reason="replaced_parallel")
            self.activate_context(key, room_name, zone_name, selected, selected_prio)
            return

        # No active context in this zone -> activate
        self.activate_context(key, room_name, zone_name, selected, selected_prio)

    # -------------------------------------------------------------------------
    # CONTEXT ENABLE GATE (binary_sensor)
    # -------------------------------------------------------------------------
    def is_context_enabled(self, ctx):
        enable_cfg = (ctx.get("enable") or {}) if isinstance(ctx, dict) else {}
        sensor = enable_cfg.get("sensor")
        if not sensor:
            return True

        expected = str(enable_cfg.get("state", "on")).lower()
        invert = bool(enable_cfg.get("invert", False))

        current = str(self.get_state(sensor) or "").lower()
        allowed = (current == expected)
        if invert:
            allowed = not allowed

        if not allowed:
            self.dbg(3, f"Enable gate blocked: {sensor}={current}, expected={expected}, invert={invert}")
        return allowed


    # -------------------------------------------------------------------------
    # is context activated
    # - Supports "on" and "true" and "1" and "yes"
    # -------------------------------------------------------------------------
    def is_context_activated(self, ctx):
        """
        Hard enable/disable via config flag.
        Default is active if not set.
        """
        val = str(ctx.get("activate", "on")).lower()
        return val in ("on", "true", "1", "yes")


    # -------------------------------------------------------------------------
    # TIME WINDOW
    # - Supports "HH:MM-HH:MM" and overnight ranges (e.g. "22:00-07:00")
    # -------------------------------------------------------------------------
    def check_time_window(self, ctx):
        windows = ctx.get("active_times")
        if not windows:
            return True

        now = datetime.now().time()

        for w in windows:
            try:
                start_s, end_s = str(w).split("-", 1)
                t1 = self.parse_time(start_s.strip())
                t2 = self.parse_time(end_s.strip())
            except Exception:
                self.dbg(1, f"Invalid time window '{w}' in ctx '{ctx.get('id')}' -> ignoring window")
                continue

            if self.time_in_window(now, t1, t2):
                return True

        self.dbg(4, f"Context '{ctx.get('id')}' blocked by time window")
        return False

    def time_in_window(self, now_t, start_t, end_t):
        # Non-overnight: start <= now < end
        if start_t <= end_t:
            return start_t <= now_t <= end_t
        # Overnight: now >= start OR now <= end
        return (now_t >= start_t) or (now_t <= end_t)

    # -------------------------------------------------------------------------
    # LUX CHECK
    # - lux:
    #     sensor: sensor.xyz
    #     below: 30
    # -------------------------------------------------------------------------
    def check_lux(self, ctx):
        lux = ctx.get("lux")
        if not lux:
            return True

        sensor = (lux or {}).get("sensor")
        below = (lux or {}).get("below")
        if not sensor or below is None:
            return True

        try:
            current = float(self.get_state(sensor))
            threshold = float(below)
        except Exception:
            self.dbg(2, f"Lux sensor not numeric: {sensor}")
            return True

        if current <= threshold:
            return True

        self.dbg(4, f"Context '{ctx.get('id')}' blocked by lux {current} > {threshold}")
        return False

    # -------------------------------------------------------------------------
    # PRESENCE CHECK (optional)
    # - presence:
    #     require: any|all
    #     entities: [person.a, person.b]
    #     state: home  (default: home)
    # -------------------------------------------------------------------------
    def check_presence(self, ctx):
        presence = ctx.get("presence")
        if not presence:
            return True

        require = str((presence or {}).get("require", "any")).lower()
        entities = (presence or {}).get("entities", []) or []
        want_state = str((presence or {}).get("state", "home")).lower()

        if not entities:
            return True

        states = []
        for e in entities:
            states.append(str(self.get_state(e) or "").lower() == want_state)

        if require == "all":
            ok = all(states)
        else:
            ok = any(states)

        if not ok:
            self.dbg(4, f"Context '{ctx.get('id')}' blocked by presence (require={require})")
        return ok

    # -------------------------------------------------------------------------
    # PRIORITY (HYBRID)
    # - room.priority (default 0)
    # - context.priority (default 0)
    # effective = room.priority * 1000 + context.priority
    # -------------------------------------------------------------------------
    def get_effective_priority(self, room, ctx):
        try:
            rp = int((room or {}).get("priority", 0))
        except Exception:
            rp = 0
        try:
            cp = int((ctx or {}).get("priority", 0))
        except Exception:
            cp = 0
        return rp * 1000 + cp

    # -------------------------------------------------------------------------
    # OPTIONAL RULE: block_if_any_on
    # - If any entity in block_if_any_on is "on", context is blocked.
    # - Useful for: "if ceiling already on, do not turn on wall"
    # -------------------------------------------------------------------------
    def blocked_by_entities_on(self, ctx):
        lst = ctx.get("block_if_any_on") or []
        if not lst:
            return False

        for ent in lst:
            st = str(self.get_state(ent) or "").lower()
            if st in ("on", "playing", "home"):
                self.dbg(4, f"block_if_any_on hit: {ent}={st}")
                return True
        return False

    # -------------------------------------------------------------------------
    # ACTIVATE CONTEXT (Step 16-18: real actions)
    # -------------------------------------------------------------------------
    def activate_context(self, key, room_name, zone_name, ctx, prio):
        ctx_id = ctx.get("id")

        self.dbg(1, f"Activating ctx '{ctx_id}' in {room_name}/{zone_name} (prio={prio})")

        now = datetime.now()
        timeout_min = ctx.get("timeout_min", 0)

        # Store active
        self.active_contexts[key] = {
            "context_id": ctx_id,
            "room": room_name,
            "zone": zone_name,
            "since": now,
            "expires_at": now + timedelta(minutes=timeout_min),
            "ctx": ctx,
            "prio": prio,
            "timer": None   # 👈 WICHTIG: Platz für Handle
        }

        # Start/replace timer
        self.start_timer(key, ctx)

        # Execute ON actions
        self.execute_actions_on(ctx)

    # -------------------------------------------------------------------------
    # DEACTIVATE CONTEXT (timeout or replaced)
    # -------------------------------------------------------------------------
    def deactivate_context(self, key, ctx, reason="timeout"):
        if not ctx:
            return

        active = self.active_contexts.get(key)
        if not active:
            return

        self.dbg(2, f"Deactivating ctx '{active.get('context_id')}' key={key} reason={reason}")

        handle = active.get("timer")
        if handle and self.timer_running(handle):
            self.cancel_timer(handle)
            self.dbg(3, f"Canceled timer for {key}")

        active["timer"] = None

        # Execute OFF actions
        self.execute_actions_off(ctx)

        # Remove active context
        self.active_contexts.pop(key, None)
        
        """
        ctx_id = ctx.get("id")
        self.dbg(2, f"Deactivating ctx '{ctx_id}' key={key} reason={reason}")


        handle = active.get("timer")
        if handle and self.timer_running(handle):
            self.cancel_timer(handle)
            self.dbg(3, f"Canceled timer for {key}")

        """
        """
        active["timer"] = None

        # Stop timer (only if still present)
        self.cancel_existing_timer(key)

        # Execute OFF actions
        self.execute_actions_off(ctx)

        # Remove from active state (if still mapped)
        if key in self.active_contexts and self.active_contexts[key].get("context_id") == ctx_id:
            self.active_contexts.pop(key, None)
        """

    # -------------------------------------------------------------------------
    # TIMER HANDLING (Step 19-20)
    # -------------------------------------------------------------------------
    def start_timer(self, key, ctx):
        """
        Start or refresh the timeout timer for an active context.

        Behavior:
        - Uses expires_at as the single source of truth
        - Does NOT reset total runtime
        - Cancels and re-schedules the timer with remaining time
        """

        active = self.active_contexts.get(key)
        if not active:
            return

        # Cancel existing timer safely
        handle = active.get("timer")
        if handle and self.timer_running(handle):
            self.cancel_timer(handle)
            self.dbg(3, f"Canceled existing timer for {key}")

        expires_at = active.get("expires_at")
        if not expires_at:
            self.dbg(3, f"No expires_at set for {key}")
            active["timer"] = None
            return

        now = datetime.now()
        remaining_sec = int((expires_at - now).total_seconds())

        # If already expired, trigger timeout immediately
        if remaining_sec <= 0:
            self.dbg(2, f"Timer already expired for {key}")
            self.on_timeout({"key": key})
            return

        # Schedule timer exactly until expires_at
        handle = self.run_in(
            self.on_timeout,
            remaining_sec,
            key=key
        )

        active["timer"] = handle

        self.dbg(
            2,
            f"Started timer for {key} "
            f"(remaining={remaining_sec}s, expires_at={expires_at.strftime('%H:%M:%S')})"
        )

    def start_timer_old(self, key, ctx):

        active = self.active_contexts.get(key)
        if not active:
            return

        # Cancel existing timer safely
        handle = active.get("timer")
        if handle and self.timer_running(handle):
            self.cancel_timer(handle)
            self.dbg(3, f"Canceled existing timer for {key}")

        timeout_min = ctx.get("timeout_min", 0)
        try:
            timeout_sec = int(timeout_min) * 60
        except Exception:
            timeout_sec = 0

        if timeout_sec <= 0:
            active["timer"] = None
            self.dbg(4, f"No timer started for {key} (timeout=0)")
            return

        handle = self.run_in(
            ## self._on_context_timeout,
            self.on_timeout,   # ✅ statt self._on_context_timeout
            timeout_sec,
            key=key
        )

        active["timer"] = handle
        active["since"] = datetime.now()   # reset start time on refresh
        self.dbg(2, f"Started timer for {key} ({timeout_sec}s)")

    # -------------------------------------------------------------------------
    # TIMER HANDLING (Step 19-20)
    # -------------------------------------------------------------------------
    def refresh_timer(self, key):
        if key not in self.active_contexts:
            return
        
        ctx = self.active_contexts[key].get("ctx")
        if not ctx:
            return
        
        self.dbg(3, f"Refreshing timer for {key}")
        self.start_timer(key, ctx)

    """
    def cancel_existing_timer(self, key):
        if key in self.timers:
            try:
                self.cancel_timer(self.timers[key])

            except Exception:
                pass
            self.timers.pop(key, None)
    """

    def on_timeout(self, kwargs):
        key = kwargs.get("key")
        active = self.active_contexts.get(key)
        if not active:
            return

        ctx = active.get("ctx")
        ctx_id = active.get("context_id")

        self.dbg(1, f"Timeout reached for ctx '{ctx_id}' key={key}")

        # Step 21: deactivate now (real off actions)
        self.deactivate_context(key, ctx, reason="timeout")

    # -------------------------------------------------------------------------
    # ACTIONS - ON
    # -------------------------------------------------------------------------
    def execute_actions_on(self, ctx):
        actions = ctx.get("actions", {}) or {}

        # 1) Scenes
        scenes = actions.get("scenes_on") or []
        for sc in scenes:
            self.call_scene(sc)

        # 2) Lights ON
        # Each item can be:
        # - "light.kitchen"
        # - {entity: light.kitchen, brightness_pct: 40, transition: 1}
        lights = actions.get("lights_on") or []
        for item in lights:
            self.call_light_on(item,ctx)

        # 3) Switches ON
        switches = actions.get("switches_on") or []
        for sw in switches:
            self.call_switch_on(sw)

    # -------------------------------------------------------------------------
    # ACTIONS - OFF
    # -------------------------------------------------------------------------
    def execute_actions_off(self, ctx):
        actions = ctx.get("actions", {}) or {}

        # Unified transition for ON and OFF
        trans = 0
        for key in ("transition", "transition_sec", "transition_off_sec"):
            if key in ctx:
                try:
                    trans = int(ctx.get(key))
                except Exception:
                    trans = 0
                break

        # 1) Lights OFF
        lights = actions.get("lights_off") or actions.get("lights_on") or []
        for item in lights:
            self.call_light_off(item, transition=trans)

        # 2) Switches OFF
        switches = actions.get("switches_off") or actions.get("switches_on") or []
        for sw in switches:
            self.call_switch_off(sw)

        # Scenes off is intentionally NOT implemented by default
        # (scenes are typically one-way). If needed, add scenes_off.

    # -------------------------------------------------------------------------
    # HA CALL HELPERS
    # -------------------------------------------------------------------------
    def call_scene(self, scene_entity):
        if not scene_entity:
            return
        try:
            self.call_service("scene/turn_on", entity_id=scene_entity)
            self.dbg(3, f"scene.turn_on: {scene_entity}")
        except Exception as e:
            self.dbg(2, f"scene.turn_on failed: {scene_entity} -> {e}")

    def call_light_on(self, item, ctx=None):
        try:
            if isinstance(item, str):
                entity = item
                data = {}
            else:
                entity = item.get("entity") or item.get("entity_id")
                mode = item.get("mode", "pct")
                data = {}

                # Common transition
                if "transition" in item:
                    data["transition"] = item.get("transition")

                # Mode handling
                if mode == "pct":
                    if "brightness_pct" in item:
                        data["brightness_pct"] = item.get("brightness_pct")

                elif mode == "brightness":
                    if "brightness" in item:
                        data["brightness"] = item.get("brightness")



                elif mode == "circadian":
                    # Circadian color handling
                    color = item.get("color", "kelvin")
                    value = self.circadian_values.get(color)

                    if value is None:
                        self.dbg(2, f"Circadian value '{color}' not available, skipping {entity}")
                        return

                    if color == "kelvin":
                        data["kelvin"] = int(value)

                    elif color == "mired":
                        # HA expects mired as color_temp
                        data["color_temp"] = int(value)

                    elif color == "rgb":
                        # Expect tuple/list (r,g,b)
                        if isinstance(value, (list, tuple)) and len(value) == 3:
                            data["rgb_color"] = [int(value[0]), int(value[1]), int(value[2])]
                        else:
                            self.dbg(
                                2,
                                f"Invalid RGB value '{value}' for {entity}, skipping"
                            )
                            return



                    # Optional circadian brightness handling
                    # Apply only if explicitly requested in YAML
                    if item.get("brightness") == "circadian":
                        b_val = self.circadian_values.get("brightness")
                        if b_val is not None:
                            data["brightness"] = int(b_val)
                            self.dbg(4, f"Applied circadian brightness to {entity}: {int(b_val)}")

                    if item.get("brightness_pct") == "circadian":
                        b_pct = self.circadian_values.get("brightness_pct")
                        if b_pct is not None:
                            data["brightness_pct"] = int(b_pct)
                            self.dbg(4, f"Applied circadian brightness_pct to {entity}: {int(b_pct)}")

                elif mode == "rgb":
                    rgb = item.get("color")
                    if rgb:
                        data["rgb_color"] = rgb

                else:
                    self.dbg(2, f"Unknown light mode '{mode}' for {entity}")
                    return

            # -------------------------------------------------
            # Context minimum brightness (percent based)
            # -------------------------------------------------
            min_pct = None
            if ctx:
                min_pct = ctx.get("minimum_brightness")

            if min_pct is not None:
                try:
                    min_pct = float(min_pct)
                except Exception:
                    min_pct = None

            if min_pct is not None:

                # pct-mode active
                if "brightness_pct" in data:
                    data["brightness_pct"] = max(
                        float(data["brightness_pct"]),
                        min_pct
                    )

                # brightness (0-255) mode active
                elif "brightness" in data:
                    min_255 = self._pct_to_255(min_pct)
                    data["brightness"] = max(
                        int(data["brightness"]),
                        min_255
                    )

                    self.dbg(
                        4,
                        f"[CTX] minimum brightness applied AFTER mode: "
                        f"ctx={ctx.get('id') if ctx else None} "
                        f"{min_pct:.1f}% → data={data}"
                    )
                # If no brightness key exists yet, inject minimum as pct (works for most lights)
                else:
                    data["brightness_pct"] = min_pct


            if not entity:
                return

            self.call_service("light/turn_on", entity_id=entity, **data)
            self.dbg(3, f"light.turn_on: {entity} data={data}")

        except Exception as e:
            self.dbg(2, f"light.turn_on failed: {item} -> {e}")




    def call_light_off(self, item, transition=0):
        try:
            if isinstance(item, str):
                entity = item
            else:
                entity = item.get("entity") or item.get("entity_id")
            if not entity:
                return

            data = {}
            if transition and transition > 0:
                data["transition"] = transition * self.transition_off_multiplier

            self.call_service("light/turn_off", entity_id=entity, **data)
            self.dbg(3, f"light.turn_off: {entity} data={data}")
        except Exception as e:
            self.dbg(2, f"light.turn_off failed: {item} -> {e}")

    def call_switch_on(self, sw_entity):
        if not sw_entity:
            return
        try:
            self.call_service("switch/turn_on", entity_id=sw_entity)
            self.dbg(3, f"switch.turn_on: {sw_entity}")
        except Exception as e:
            self.dbg(2, f"switch.turn_on failed: {sw_entity} -> {e}")

    def call_switch_off(self, sw_entity):
        if not sw_entity:
            return
        try:
            self.call_service("switch/turn_off", entity_id=sw_entity)
            self.dbg(3, f"switch.turn_off: {sw_entity}")
        except Exception as e:
            self.dbg(2, f"switch.turn_off failed: {sw_entity} -> {e}")

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def parse_time(self, s):
        # "HH:MM" -> datetime.time
        hh, mm = str(s).split(":")
        return datetime.now().replace(hour=int(hh), minute=int(mm), second=0, microsecond=0).time()
    


     # =========================================================================
    # CONFIG RESOLUTION (engine -> room -> zone)
    # =========================================================================
    def resolve_cfg(self, room=None, zone=None, key=None, default=None):
        """
        Resolve a configuration value using hierarchical inheritance.

        Order of precedence (highest wins):
            1. Zone-level
            2. Room-level
            3. Engine-level
            4. Default value

        This allows defining global defaults at engine level,
        overriding them per room, and fine-tuning per zone.

        Parameters:
            room (str | None):
                Name of the room (e.g. "esszimmer").
                If None, only engine-level will be checked.

            zone (str | None):
                Name of the zone inside the room (e.g. "rechts").
                Only evaluated if room is also provided.

            key (str):
                Configuration key to resolve
                (e.g. "debug_level", "mode", "timeout_min").

            default (any):
                Fallback value if the key is not found anywhere.

        Returns:
            The resolved configuration value or default.
        """

        # ---------------------------------------------------------------------
        # Debug: function entry
        # ---------------------------------------------------------------------
        self.dbg(
            9,
            f"resolve_cfg() start | key='{key}', room='{room}', zone='{zone}'"
        )

        # ---------------------------------------------------------------------
        # 1) Zone-level
        # ---------------------------------------------------------------------
        if room and zone:
            zone_cfg = (
                self.config
                .get("rooms", {})
                .get(room, {})
                .get("zones", {})
                .get(zone, {})
            )

            self.dbg(9, f"Zone cfg keys: {list(zone_cfg.keys())}")

            if key in zone_cfg:
                value = zone_cfg[key]
                self.dbg(
                    7,
                    f"resolve_cfg('{key}') → zone override "
                    f"({room}/{zone}) = {value}"
                )
                return value

        # ---------------------------------------------------------------------
        # 2) Room-level
        # ---------------------------------------------------------------------
        if room:
            room_cfg = self.config.get("rooms", {}).get(room, {})
            self.dbg(9, f"Room cfg keys for '{room}': {list(room_cfg.keys())}")

            if key in room_cfg:
                value = room_cfg[key]
                self.dbg(
                    7,
                    f"resolve_cfg('{key}') → room override "
                    f"({room}) = {value}"
                )
                return value

        # ---------------------------------------------------------------------
        # 3) Engine-level
        # ---------------------------------------------------------------------
        engine_cfg = self.config.get("engine", {})
        self.dbg(9, f"Engine cfg keys: {list(engine_cfg.keys())}")

        if key in engine_cfg:
            value = engine_cfg[key]
            self.dbg(
                7,
                f"resolve_cfg('{key}') → engine default = {value}"
            )
            return value

        # ---------------------------------------------------------------------
        # 4) Default fallback
        # ---------------------------------------------------------------------
        self.dbg(
            5,
            f"resolve_cfg('{key}') → using default = {default}"
        )

        return default


    # ---------------------------------------------------------
    # 🧠 NEUE FUNKTION: Erkennung manuelles Einschalten + Timer
    # ---------------------------------------------------------
    def is_manual_light_on(self, light_entity, room, context_id):
        """
        Prüft, ob ein Licht manuell eingeschaltet wurde und ob der manuelle Timer aktiv ist.
        """
        light_state = self.get_state(light_entity)
        if light_state != "on":
            return False

        room_conf = self.cfg.get("rooms", {}).get(room, {})
        zones = room_conf.get("zones", {})

        manual_conf = None
        for zone_name, zone_conf in zones.items():
            for ctx in zone_conf.get("contexts", []):
                if ctx.get("id") == context_id:
                    manual_conf = ctx.get("manual_timer", {}).get("enable", None)
                    break

        if not manual_conf:
            self.log(f"[{room}/{context_id}] Kein Manual-Timer definiert", level="DEBUG")
            return False

        sensor_entity = manual_conf.get("sensor")
        expected_state = manual_conf.get("state", "on")
        invert = manual_conf.get("invert", False)

        sensor_state = self.get_state(sensor_entity)
        timer_active = (sensor_state == expected_state)
        if invert:
            timer_active = not timer_active

        if light_state == "on" and timer_active:
            self.log(f"[{room}/{context_id}] {light_entity} ist manuell eingeschaltet (Timer aktiv)", level="DEBUG")
            return True

        return False
    

    # ---------------------------------------------------------
    # 🧠 Debug Context 
    # ---------------------------------------------------------
    def _debug_dump_contexts(self):
        if self.debug_level < 9:
            return

        self.log("==== BrainLights Context Overview ====", level="INFO")

        for room_name, room in self.rooms.items():
            self.log(f"[ROOM] {room_name}", level="INFO")

            for zone_name, zone in room["zones"].items():
                self.log(f"  [ZONE] {zone_name}", level="INFO")

                for ctx in zone["contexts"]:
                    self.log(
                        f"    [CTX] {ctx['id']} | prio={ctx.get('priority')} | "
                        f"timeout={ctx.get('timeout_min')}min | "
                        f"lux<{ctx.get('lux', {}).get('below')} | "
                        f"times={ctx.get('active_times')}",
                        level="INFO"
                    )


    # ---------------------------------------------------------
    # 🧠 Active Contexts ....
    # ---------------------------------------------------------
    def _log_active_contexts(self, kwargs):
        """
        Periodic status logger (runs every minute).

        Purpose:
        - List all currently active contexts
        - Show remaining time until timeout
        - Show which lights were switched on by the context

        This function is read-only:
        - No timers are modified
        - No states are changed
        - Safe to run continuously
        """

        # Only log if debug level is high enough
        if self.debug_level < 3:
            return

        # No active contexts -> nothing to report
        if not self.active_contexts:
            self.dbg(4, "No active contexts")
            return

        now = datetime.now()


        # Iterate over all active contexts (key = room:zone)
        for key, active in self.active_contexts.items():

            # Context reference and metadata
            ctx = active.get("ctx") or {}
            ctx_id = active.get("context_id")
            since = active.get("since")

            expires_at = active.get("expires_at")
            remaining = int((expires_at - now).total_seconds() // 60)

            # Calculate remaining time in minutes
            # If no timeout or no start time exists, mark as infinite
            timeout_min = ctx.get("timeout_min", 0)
            if not since or timeout_min <= 0:
                remaining_min = "inf"
            else:
                elapsed = (now - since).total_seconds()
                remaining = max(0, timeout_min * 60 - elapsed)

                # Round up to full minutes
                remaining_min = int((remaining + 59) // 60)

            # Collect lights that were switched on by this context
            lights = []
            actions = ctx.get("actions", {})
            for item in actions.get("lights_on", []):
                ent = item.get("entity")
                if ent:
                    lights.append(ent)

            # Prepare readable light list
            lights_str = ", ".join(lights) if lights else "-"

            elapsed_min = "-"
            if since:
                elapsed_min = int((now - since).total_seconds() // 60)

            since_str = since.strftime("%H:%M:%S") if since else "-"

            # Final status log line
            self.dbg(
                3,
                f"[ACTIVE] ctx='{ctx_id}' key={key} "
                f"since={since_str} elapsed={elapsed_min}min "
                f"remaining={remaining_min}min lights=[{lights_str}]"
            )


            
    def _apply_circadian_to_active_lights(self, kwargs=None):
        """
        Periodically re-apply circadian values to active lights.

        Purpose:
        - Keep kelvin / mired in sync while a context is active
        - Only affects lights using mode: circadian
        - Only updates lights that are currently on

        This function:
        - Does NOT touch timers
        - Does NOT activate or deactivate contexts
        """

        if not self.active_contexts:
            return

        for key, active in self.active_contexts.items():
            ctx = active.get("ctx") or {}
            actions = ctx.get("actions", {}) or {}
            lights = actions.get("lights_on", []) or []

            for item in lights:
                if not isinstance(item, dict):
                    continue

                if item.get("mode") != "circadian":
                    continue

                entity = item.get("entity")
                if not entity:
                    continue

                # Only update if light is currently on
                state = self.get_state(entity)
                if state != "on":
                    continue

                # Re-apply circadian values via existing logic
                self.dbg(4, f"Reapplying circadian to {entity} (key={key})")
                self.call_light_on(item,ctx)


    # ---------------------------------------------------------
    def _pct_to_255(self, pct):
        pct = max(0, min(100, pct))
        return int(round(pct / 100 * 255))


    def _255_to_pct(self, value):
        value = max(0, min(255, value))
        return int(round(value / 255 * 100))
