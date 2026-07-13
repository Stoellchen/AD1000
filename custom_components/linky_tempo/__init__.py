"""Initialisation du composant Linky Tempo."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_PRM, CONF_TOKEN
from .coordinator import LinkyTempoCoordinator

_LOGGER = logging.getLogger(__name__)

# On définit les plateformes qu'on va charger (ici, juste des sensors)
PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configuration de l'intégration à partir d'une entrée config."""

    # 1. Récupération des infos de config
    prm = entry.data[CONF_PRM]
    token = entry.data[CONF_TOKEN]

    # 2. Création du coordinateur
    coordinator = LinkyTempoCoordinator(hass, prm, token)

    # 3. Première mise à jour des données (Critique pour avoir les stats tout de suite)
    # Si ça échoue ici, l'intégration affichera "Échec de configuration"
    await coordinator.async_config_entry_first_refresh()

    # 4. Stockage du coordinateur dans HA pour que les sensors puissent l'utiliser
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 5. Chargement des plateformes (le fichier sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Suppression de l'intégration."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok