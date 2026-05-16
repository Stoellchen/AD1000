- id: '1778693481030'
  alias: TESTEEST
  description: ''
  triggers:
  - trigger: mqtt
    options:
      topic: zigbee2mqtt/Moes4GS001
  conditions:
  - condition: template
    value_template: '{{ trigger.payload_json.action == ''1_single'' }}'
  actions:
  - type: turn_on
    device_id: 6cafcfa58b395f1a45059f2e7abc1eb9
    entity_id: cfa1019d43df3fb32776aac6744f4f03
    domain: light
  mode: single
