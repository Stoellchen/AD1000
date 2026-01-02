#pragma once

#include <string>
#include <vector>
#include <sstream>

inline std::vector<std::string> split(const std::string &str, char delimiter) {
  std::vector<std::string> result;
  std::string token;
  std::istringstream stream(str);
  while (std::getline(stream, token, delimiter)) {
    result.push_back(token);
  }
  return result;
}

