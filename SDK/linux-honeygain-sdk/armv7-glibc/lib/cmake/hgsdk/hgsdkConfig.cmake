if(NOT DEFINED hgsdkConfig_INCLUDED)
  set(hgsdkConfig_INCLUDED TRUE)
  set(hgsdk_VERSION "1.0.0" CACHE STRING "Version of hgsdk library")
  add_library(hgsdk::hgsdk SHARED IMPORTED)
  set_target_properties(hgsdk::hgsdk PROPERTIES
    IMPORTED_LOCATION "${CMAKE_CURRENT_LIST_DIR}/../../../lib/libhgsdk.so.1.0.0"
    IMPORTED_SONAME "libhgsdk.so.1"
    INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_CURRENT_LIST_DIR}/../../../include"
  )
endif()
