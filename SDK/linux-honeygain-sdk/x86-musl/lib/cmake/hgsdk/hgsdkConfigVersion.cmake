set(PACKAGE_VERSION "1.0.0" CACHE STRING "Version of hgsdk library")
if(PACKAGE_VERSION VERSION_LESS PACKAGE_FIND_VERSION)
  message(
    FATAL_ERROR
      "hgsdkConfig.cmake error: "
      "Requested hgsdk version ${PACKAGE_FIND_VERSION} but found ${PACKAGE_VERSION}"
  )
endif()
