import logging
import traceback
from datetime import timedelta, datetime, date
import requests
import asyncio

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
    StatisticMetaData,
)
from homeassistant.components.recorder.models import StatisticData
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

API_TEMPO_URL = "https://www.api-couleur-tempo.fr/api/jourTempo"


class LinkyTempoCoordinator(DataUpdateCoordinator):
    """Gère la récupération conso, la couleur Tempo et l'injection d'historique."""

    def __init__(self, hass: HomeAssistant, prm, token):
        super().__init__(
            hass,
            _LOGGER,
            name="Linky Tempo Data",
            update_interval=timedelta(hours=4),
        )
        self.prm = prm
        self.token = token
        self.api_conso_url = "https://conso.boris.sh/api/consumption_load_curve"
        self.color_cache = {}

    async def _async_update_data(self):
        """Fonction principale appelée par HA."""
        try:
            today = datetime.now()
            str_end = today.strftime("%Y-%m-%d")
            # On prend 7 jours pour le rattrapage
            str_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

            _LOGGER.debug(f"Récupération Linky {self.prm} : {str_start} -> {str_end}")

            conso_data = await self.hass.async_add_executor_job(
                self._fetch_conso_api, str_start, str_end
            )

            if not conso_data or "interval_reading" not in conso_data:
                _LOGGER.warning("Aucune donnée de consommation reçue.")
                return {}

            return await self._process_load_curve(conso_data)

        except Exception as err:
            _LOGGER.error(f"Erreur Linky Tempo : {err}")
            _LOGGER.error(traceback.format_exc())
            raise UpdateFailed(f"Erreur Linky Tempo : {err}")

    def _fetch_conso_api(self, start, end):
        params = {"prm": self.prm, "start": start, "end": end}
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(self.api_conso_url, params=params, headers=headers, timeout=40)
        resp.raise_for_status()
        return resp.json()

    async def _process_load_curve(self, api_data):
        # 1. Init
        stats = {k: 0.0 for k in ["BLUE_HC", "BLUE_HP", "WHITE_HC", "WHITE_HP", "RED_HC", "RED_HP"]}

        readings = api_data.get("interval_reading", [])
        if not readings:
            return stats

        stat_ids = {}
        for key in stats.keys():
            french_slug = self._get_french_slug(key)
            stat_ids[key] = f"sensor.linky_tempo_{french_slug}"

        if not stat_ids:
            return stats

        # 2. Récupération du DERNIER POINT CONNU en base (Append Only)
        try:
            ids_list = list(stat_ids.values())
            last_stats_db = await self.hass.async_add_executor_job(
                lambda: get_last_statistics(self.hass, 1, ids_list, True, {"sum", "start"})
            )
        except Exception as e:
            _LOGGER.warning(f"Impossible de récupérer l'historique : {e}")
            last_stats_db = {}

        # On initialise nos compteurs avec les valeurs de la DB
        current_sums = {}
        last_db_dates = {}

        for key, stat_id in stat_ids.items():
            if stat_id in last_stats_db and last_stats_db[stat_id]:
                last_rec = last_stats_db[stat_id][0]
                current_sums[key] = last_rec.get("sum") or 0.0
                ts_str = last_rec.get("start")

                # Parsing robuste de la date DB
                if isinstance(ts_str, str):
                    dt_val = dt_util.parse_datetime(ts_str)
                else:
                    dt_val = ts_str

                # Sécurité Timezone
                if dt_val and dt_val.tzinfo is None:
                    dt_val = dt_val.replace(tzinfo=dt_util.UTC)

                last_db_dates[key] = dt_val

                # Debug log pour vérifier d'où on part
                _LOGGER.debug(f"[{key}] Reprise historique à {dt_val} (Cumul: {current_sums[key]})")
            else:
                current_sums[key] = 0.0
                last_db_dates[key] = None
                _LOGGER.debug(f"[{key}] Historique vide, démarrage à 0.")

        readings.sort(key=lambda x: x["date"])

        paris_tz = dt_util.get_time_zone("Europe/Paris")

        # 3. Pré-traitement (Bucketing + Correction Timezone)
        hourly_deltas = {k: {} for k in stats.keys()}

        for reading in readings:
            val = int(reading["value"])
            naive_dt = datetime.strptime(reading["date"], "%Y-%m-%d %H:%M:%S")

            # FORCE PARIS
            ts = naive_dt.replace(tzinfo=paris_tz)

            # CORRECTION -1H (Décalage API)
            ts = ts - timedelta(hours=1)

            kwh = val / 4000.0

            # Logique Tempo
            if ts.hour < 6:
                tempo_date_obj = (ts - timedelta(days=1)).date()
            else:
                tempo_date_obj = ts.date()
            tempo_date_str = tempo_date_obj.strftime("%Y-%m-%d")

            if tempo_date_str not in self.color_cache:
                color_code = await self.hass.async_add_executor_job(
                    self._fetch_tempo_color_web, tempo_date_str
                )
                self.color_cache[tempo_date_str] = color_code
            color = self.color_cache[tempo_date_str]

            if 6 <= ts.hour < 22:
                mode = "HP"
            else:
                mode = "HC"

            if color != "UNKNOWN":
                key = f"{color}_{mode}"

                # Mise à jour sensor temps réel (indépendant de l'historique)
                if key in stats:
                    stats[key] += kwh

                # Bucket : on range dans l'heure précédente
                hour_bucket = (ts - timedelta(seconds=1)).replace(minute=0, second=0, microsecond=0)

                if hour_bucket not in hourly_deltas[key]:
                    hourly_deltas[key][hour_bucket] = 0.0

                hourly_deltas[key][hour_bucket] += kwh

        # 4. Injection en mode "APPEND ONLY"
        # On ne touche jamais au passé. On ne fait qu'ajouter ce qui dépasse la dernière date connue.

        # Limite stricte : Minuit ce matin. Aucune donnée d'aujourd'hui ne passe.
        cutoff_date = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)

        for key, delta_map in hourly_deltas.items():
            if not delta_map:
                continue

            statistic_id = stat_ids[key]
            data_points = []

            # On parcourt les heures dans l'ordre chronologique
            sorted_hours = sorted(delta_map.keys())

            for hour_start in sorted_hours:
                # La stat est posée à la FIN de l'heure
                target_ts = hour_start + timedelta(hours=1)

                # 1. Filtre Futur/Aujourd'hui
                if target_ts > cutoff_date:
                    continue

                consumption_for_this_hour = delta_map[hour_start]

                # 2. Filtre Continuité (Append Only)
                # Si cette heure est déjà en base (ou avant), ON IGNORE.
                # Mais attention : on ne met PAS à jour current_sums ici car current_sums
                # a déjà été initialisé à la valeur finale de la DB !
                # On ne doit ajouter que le DELTA des nouvelles heures.

                last_db = last_db_dates.get(key)

                if last_db and target_ts <= last_db:
                    # Déjà connu, on passe
                    continue

                # C'est une NOUVELLE heure inconnue, on l'ajoute à la suite
                current_sums[key] += consumption_for_this_hour

                data_points.append(
                    StatisticData(
                        start=target_ts,
                        state=None,
                        sum=current_sums[key]
                    )
                )

            if not data_points:
                continue

            _LOGGER.info(
                f"Injection de {len(data_points)} NOUVEAUX points pour {key}. Nouveau cumul atteint: {data_points[-1]['sum']:.2f} kWh")

            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"Linky Tempo {key}",
                source="recorder",
                statistic_id=statistic_id,
                unit_of_measurement="kWh",
            )

            async_import_statistics(self.hass, metadata, data_points)

        return stats

    def _get_french_slug(self, key):
        mapping = {
            "BLUE_HC": "bleu_heures_creuses",
            "BLUE_HP": "bleu_heures_pleines",
            "WHITE_HC": "blanc_heures_creuses",
            "WHITE_HP": "blanc_heures_pleines",
            "RED_HC": "rouge_heures_creuses",
            "RED_HP": "rouge_heures_pleines",
        }
        return mapping.get(key, key.lower())

    def _fetch_tempo_color_web(self, date_str):
        url = f"{API_TEMPO_URL}/{date_str}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                code = data.get("codeJour", 0)
                if code == 1: return "BLUE"
                if code == 2: return "WHITE"
                if code == 3: return "RED"
        except Exception:
            pass
        return "UNKNOWN"