"""Config flow pour l'intégration Linky Tempo."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

# On importe les constantes définies précédemment
from .const import DOMAIN, CONF_PRM, CONF_TOKEN

_LOGGER = logging.getLogger(__name__)

# Schéma du formulaire (les champs à afficher)
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PRM): str,
        vol.Required(CONF_TOKEN): str,
    }
)


class LinkyTempoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration via l'UI."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Étape 1 : L'utilisateur remplit le formulaire."""
        errors = {}

        if user_input is not None:
            # 1. Validation basique
            prm = user_input[CONF_PRM]
            token = user_input[CONF_TOKEN]

            if len(prm) != 14 or not prm.isdigit():
                errors[CONF_PRM] = "invalid_prm_format"

            # 2. Vérifier si ce PRM n'est pas déjà configuré
            else:
                await self.async_set_unique_id(prm)
                self._abort_if_unique_id_configured()

                # 3. Si tout est bon, on crée l'entrée
                # Le titre affiché dans la liste des intégrations sera "Linky Tempo (1234...)"
                return self.async_create_entry(
                    title=f"Linky Tempo ({prm})",
                    data=user_input
                )

        # Affichage du formulaire (ou ré-affichage en cas d'erreur)
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )