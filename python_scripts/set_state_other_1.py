"""Set the state or other attributes for the specified entity."""

# ========================================================================================
# python_scripts/set_state_other_1.py
# modified from -
# https://gist.github.com/pelrun/91feae869aa9bfe9faa610a1fbbee9b3
# ========================================================================================

# ----------------------------------------------------------------------------------------
# Set the state or other attributes for the specified entity.
# Updates from @xannor so that a new entity can be created if it does not exist.
# ----------------------------------------------------------------------------------------

##
##  13.5.24     this is used to increment the fake watercounter from automation: set_meter_rate_water_update in script: usto_set_energy_costs_utility_meter.yaml
##
##

if 'entity_id' not in data:
  logger.warning("===== entity_id is required if you want to set something.")
else:
  data = data.copy()
  inputEntity = data.pop('entity_id')
  inputStateObject = hass.states.get(inputEntity)
  if inputStateObject:
    inputState = inputStateObject.state
    inputAttributesObject = inputStateObject.attributes.copy()
  else:
    inputState = 'unknown'
    inputAttributesObject = {}
  if 'state' in data:
    inputState = data.pop('state')
  logger.debug("===== new attrs: {}".format(data))
  inputAttributesObject.update(data)

  hass.states.set(inputEntity, inputState, inputAttributesObject)

        