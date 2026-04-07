# Integrating Honeygain SDK with Windows application
This guide will go through the process of integrating and using Honeygain SDK in your Windows application.

On Windows operating system SDK service is provided for 64-bit and 32-bit architectures. SDK service dynamic-link libraries `x64\bin\hgsdk.dll` or `x86\bin\hgsdk.dll` should be loaded by your applications executable. It is recommended to place them in the same directory as your applications executable file depending on its architecture.

If using Visual Studio you can take following steps to integrate SDK service:
* Right-click on your project in **Solution Explorer** and select **Properties**.
* Go to **Configuration Properties > C/C++ > General**.
  * Make sure that **Configuration** is set to **All Configurations**.
  * When targeting 64-bit architecture make sure that **Platform** is set to **x64** and in **Additional Include Directories** add path to the SDK service header file `x64\include\hgsdk.h`.
  * When targeting 32-bit architecture make sure that **Platform** is set to **Win32** and in **Additional Include Directories** add path to the SDK service header file `x86\include\hgsdk.h`.
* Go to **Configuration Properties > Linker > General**.
  * Make sure that **Configuration** is set to **All Configurations**.
  * When targeting 64-bit architecture make sure that **Platform** is set to **x64** and in **Additional Library Directories** add path to the SDK service import library `x64\lib\hgsdk.dll.lib`.
  * When targeting 32-bit architecture make sure that **Platform** is set to **Win32** and in **Additional Library Directories** add path to the SDK service import library `x86\lib\hgsdk.dll.lib`.
* Go to **Configuration Properties > Linker > Input**.
  * Make sure that **Configuration** is set to **All Configurations** and **Platform** is set to **All Platforms**.
  * In **Additional Dependencies** add `hgsdk.dll.lib`.
* Go to **Configuration Properties > Build Events > Post-Build Event**.
  * Make sure that **Configuration** is set to **All Configurations**.
  * When targeting 64-bit architecture make sure that **Platform** is set to **x64** and in **Command Line** add
	```cmd
	copy /Y "<path to>\x64\bin\hgsdk.dll" "$(OutDir)"
	```
  * When targeting 32-bit architecture make sure that **Platform** is set to **Win32** and in **Command Line** add
	```cmd
	copy /Y "<path to>\x86\bin\hgsdk.dll" "$(OutDir)"
	```
  * Replace `<path to>` with the path to the directory where SDK service dynamic-link library is located.

> Full working example can be found in `samples/windows` directory of the downloaded Honeygain SDK.

## Functions

> Note that `hgsdk_start()` and `hgsdk_stop()` function calls are non-blocking operations. Internally SDK service starting and stopping are asynchronous operations and there might be a slight delay before action actually happens.

### hgsdk_start

To start the SDK service call `hgsdk_start()` function:
```c++
int32_t hgsdk_start(const char *api_key, int32_t *state);
```

#### Parameters

`api_key` - Your API Key provided by Honeygain SDK.

`state` - Pointer to the variable where SDK service consent state will be stored. If user consent was given previously `*state` will be set to `1`, otherwise `*state` will be set to `0`.

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

It will check if explicit user consent was given before. Information about current state of user consent is stored in `*state` variable. If user consent was given previously, SDK service will start immediately. If user consent was not given previously, SDK service will not start and `*state` will be set to `0`.

If SDK service is already running, the old instance will be stopped and new instance will be started with specified API key.

> It is recommended to get user consent before starting SDK service.

### hgsdk_stop

To stop the SDK service call `hgsdk_stop()` function:
```c++
int32_t hgsdk_stop(void);
```

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Stop the SDK service. If SDK service is not running, this function will do nothing. If SDK service is running, it will be stopped and all resources will be released.

> It is recommended to stop SDK service before closing your application. This will ensure that all resources are released and SDK service is stopped properly.

### hgsdk_is_running

To verify if SDK service is running call `hgsdk_is_running()` function:
```c++
int32_t hgsdk_is_running(int32_t *state);
```

#### Parameters

`state` - Pointer to the variable where SDK service state will be stored. If SDK service is running `*state` will be set to `1`, otherwise `*state` will be set to `0`.

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

### hgsdk_opt_in

To provide user consent call `hgsdk_opt_in()` function:
```c++
int32_t hgsdk_opt_in(void);
```

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Store information that user consent was given and inform SDK service that it can start. Subsequent calls to `hgsdk_start()` will be allowed to start SDK service.

### hgsdk_opt_out

To revoke user consent call `hgsdk_opt_out()` function:
```c++
int32_t hgsdk_opt_out(void);
```

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Store information that user consent was revoked and inform SDK service that it should stop if it is running. Subsequent calls to `hgsdk_start()` will not be allowed to start SDK service.

### hgsdk_is_opted_in

To verify if user consent was given call `hgsdk_is_opted_in()` function:
```c++
int32_t hgsdk_is_opted_in(int32_t *state);
```

#### Parameters

`state` - Pointer to the variable where user consent state will be stored. If user consent was given `*state` will be set to `1`, otherwise `*state` will be set to `0`.

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Stored information about user consent state is provided in `*state` variable.

### hgsdk_request_opt_in

To request user consent call `hgsdk_request_opt_in()` function:
```c++
int32_t hgsdk_request_consent(int32_t *state);
```

#### Parameters

`state` - Pointer to the variable where user consent state will be stored. If user consent was given `*state` will be set to `1`, otherwise `*state` will be set to `0`.

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Display default user agreement window.

If user accepts the agreement, store information that user consent was given and inform SDK service that it can start. Subsequent calls to `hgsdk_start()` will be allowed to start SDK service.

If user declines the agreement or closes the window subsequent calls to `hgsdk_start()` will not be allowed to start SDK service if user consent was not given previously.

> This function is blocking and will return only after user accepts or declines the agreement.

### hgsdk_log

To enable logging for SDK service call `hgsdk_log()` function:
```c++
int32_t hgsdk_log(const char *dir);
```

#### Parameters

`dir` - Path to the directory where log files will be stored.

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Enable logging for SDK service. Log files will be stored in the specified directory. If directory does not exist, it will be created. If `dir` parameter is `NULL` or empty string, then log files will be created in the current working directory of your application. Log is also writen to standard output. Subsequent calls to `hgsdk_log()` will create a new log file in the specified directory.

### hgsdk_mute

To disable logging for SDK service call `hgsdk_mute()` function:
```c++
int32_t hgsdk_mute(void);
```

#### Return value

Returns `0` if function call was successful, otherwise returns negative error code.

#### Remarks

Disable logging for SDK service. Any log file is closed and writing to standard output is stopped. Log files are not deleted and can be used for debugging purposes. If you want to delete log files, you can do it manually.
