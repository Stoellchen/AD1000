#pragma once

#include "esphome/core/component.h"
#include <vector>
#include <string>

namespace esphome {
namespace switch_store {

struct SwitchInfo {
  std::string raum;
  std::string name;
  std::string entity_id;
  std::string state;
  std::string watt;
  std::string ampere;
  std::string volt;
  std::string kwh;
  std::string shared;
  std::string device;
  std::string dev_id;
};

class SwitchStore : public Component {
 public:
  void add_switch(const SwitchInfo &info) {
    switches_.push_back(info);
  }

  void clear() {
    switches_.clear();
  }

  int count() const {
    return switches_.size();
  }

  const std::vector<SwitchInfo> &get_switches() const {
    return switches_;
  }

  const SwitchInfo &get(int index) const {
    return switches_[index];
  }

  // ✅ NEU: Zugriff auf alle gespeicherten Switches
  const std::vector<SwitchInfo>& get_all() const {
    return this->switches_;
  }
  
 protected:
  std::vector<SwitchInfo> switches_;
};

}  // namespace switch_store
}  // namespace esphome