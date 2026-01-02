from esphome.components import custom
import esphome.config_validation as cv
import esphome.codegen as cg

DEPENDENCIES = []

switch_store_ns = cg.global_ns.namespace('switch_store')
SwitchStore = switch_store_ns.class_('SwitchStore', cg.Component)

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(SwitchStore),
}).extend(cv.COMPONENT_SCHEMA)

def to_code(config):
    var = cg.new_Pvariable(config["id"])
    yield cg.register_component(var, config)