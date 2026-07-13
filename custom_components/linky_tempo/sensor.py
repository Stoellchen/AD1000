from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSORS_TYPES


async def async_setup_entry(hass, entry, async_add_entities):
    """Configuration des capteurs via l'interface graphique."""
    # On récupère le coordinateur créé dans __init__.py (non montré ici)
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []
    # On crée une entité pour chaque clé (BLUE_HC, BLUE_HP, etc.)
    for key, name in SENSORS_TYPES.items():
        sensors.append(LinkyTempoSensor(coordinator, key, name, entry.data.get("prm")))

    async_add_entities(sensors)


class LinkyTempoSensor(CoordinatorEntity, SensorEntity):
    """Représentation d'un compteur Tempo (ex: Rouge HP)."""

    def __init__(self, coordinator, key, name, prm):
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._prm = prm
        # ID unique pour que HA puisse gérer l'entité dans le registre
        self._attr_unique_id = f"linky_{prm}_{key.lower()}"

    @property
    def name(self):
        return f"{self._name}"

    @property
    def native_value(self):
        """Retourne la valeur calculée par le coordinateur."""
        # On va chercher la valeur dans le dictionnaire stats retourné par _process_load_curve
        return self.coordinator.data.get(self._key)

    @property
    def native_unit_of_measurement(self):
        return UnitOfEnergy.KILO_WATT_HOUR

    @property
    def device_class(self):
        return SensorDeviceClass.ENERGY

    @property
    def state_class(self):
        # TOTAL = La valeur reset, mais représente une quantité finie (hier)
        # TOTAL_INCREASING = Pour un compteur qui ne fait que monter (index)
        # Ici, tu affiches la consommation de LA VEILLE, donc c'est une mesure statique.
        return SensorStateClass.TOTAL

    @property
    def extra_state_attributes(self):
        """Attributs utiles pour le debug."""
        return {
            "period": "yesterday",
            "tempo_mode": self._key
        }