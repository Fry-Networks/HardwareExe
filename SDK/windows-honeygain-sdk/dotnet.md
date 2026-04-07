# Integrating Honeygain SDK with Windows application
This guide will go through the process of integrating and using Honeygain SDK in your Windows application.

On Windows operating system SDK service is provided for 64-bit and 32-bit architectures. SDK service dynamic-link libraries `x64\bin\hgsdk.dll` and `x86\bin\hgsdk.dll` should be accessible to your applications executable file. It is recommended to place them in the same directory tree as your applications executable. If you need to support only one architecture, you can use only one of the provided libraries. 

If using Visual Studio you can automatically place SDK service dynamic-link libraries in the output directory using post-build event:
* Right-click on your project in **Solution Explorer** and select **Properties**.
* In the properties window, go to **Build Events** on the left sidebar.
* In the **Post-build event command line** field add the following command:
    ```cmd
    mkdir "$(TargetDir)\x86"
    mkdir "$(TargetDir)\x64"
    copy /Y "<path to>\x86\bin\hgsdk.dll" "$(TargetDir)\x86\hgsdk.dll"
    copy /Y "<path to>\x64\bin\hgsdk.dll" "$(TargetDir)\x64\hgsdk.dll"
    ```
* Replace `<path to>` with the path to the directory where SDK service dynamic-link libraries are located.

SDK service functions can be called from managed code using Platform Invoke (P/Invoke) functionality.

In order to call SDK functions, add the following class to your applications source code:

```c# title="Hgsdk.cs"
using System;
using System.Runtime.InteropServices;

static class Hgsdk
{
    static Hgsdk()
    {
        try
        {
            AppDomain.CurrentDomain.ProcessExit += OnExit;
            AppDomain.CurrentDomain.DomainUnload += OnExit;
        }
        catch { }
    }

    public static bool Start(string api_key)
    {
        int result = Is64bit ? Start64(api_key, out bool consent) : Start32(api_key, out consent);
        if (result < 0)
            throw new Exception("Failed to start HG SDK");
        return consent;
    }

    public static void Stop()
    {
        int result = Is64bit ? Stop64() : Stop32();
        if (result < 0)
            throw new Exception("Failed to stop HG SDK");
    }

    public static bool IsRunning()
    {
        int result = Is64bit ? IsRunning64(out bool running) : IsRunning32(out running);
        if (result < 0)
            throw new Exception("Failed to check if HG SDK is running");
        return running;
    }

    public static void OptIn()
    {
        int result = Is64bit ? OptIn64() : OptIn32();
        if (result < 0)
            throw new Exception("Failed to opt in user");
    }

    public static void OptOut()
    {
        int result = Is64bit ? OptOut64() : OptOut32();
        if (result < 0)
            throw new Exception("Failed to opt out user");
    }

    public static bool IsOptedIn()
    {
        int result = Is64bit ? IsOptedIn64(out bool consent) : IsOptedIn32(out consent);
        if (result < 0)
            throw new Exception("Failed to check if user is opted in");
        return consent;
    }

    public static bool RequestConsent()
    {
        int result = Is64bit ? RequestConsent64(out bool consent) : RequestConsent32(out consent);
        if (result < 0)
            throw new Exception("Failed to request user consent");
        return consent;
    }

    public static void Log(string dir)
    {
        int result = Is64bit ? Log64(dir) : Log32(dir);
        if (result < 0)
            throw new Exception("Failed to enable logging for HG SDK");
    }

    public static void Mute()
    {
        int result = Is64bit ? Mute64() : Mute32();
        if (result < 0)
            throw new Exception("Failed to disable logging for HG SDK");
    }

    private static bool Is64bit
    {
        get
        {
            if (RuntimeInformation.ProcessArchitecture == Architecture.X64)
                return true;
            else if (RuntimeInformation.ProcessArchitecture == Architecture.X86)
                return false;
            else
                throw new PlatformNotSupportedException();
        }
    }

    private static void OnExit(object sender, EventArgs e)
    {
        try
        {
            Stop();
        }
        catch { }
    }

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_start", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Start32(string api_key, out bool consent);

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_stop", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Stop32();

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_is_running", CallingConvention = CallingConvention.Cdecl)]
    private static extern int IsRunning32(out bool running);

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_opt_in", CallingConvention = CallingConvention.Cdecl)]
    private static extern int OptIn32();

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_opt_out", CallingConvention = CallingConvention.Cdecl)]
    private static extern int OptOut32();

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_is_opted_in", CallingConvention = CallingConvention.Cdecl)]
    private static extern int IsOptedIn32(out bool consent);

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_request_consent", CallingConvention = CallingConvention.Cdecl)]
    private static extern int RequestConsent32(out bool consent);

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_log", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Log32(string dir);

    [DllImport("x86\\hgsdk.dll", EntryPoint = "hgsdk_mute", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Mute32();

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_start", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Start64(string api_key, out bool consent);

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_stop", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Stop64();

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_is_running", CallingConvention = CallingConvention.Cdecl)]
    private static extern int IsRunning64(out bool running);

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_opt_in", CallingConvention = CallingConvention.Cdecl)]
    private static extern int OptIn64();

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_opt_out", CallingConvention = CallingConvention.Cdecl)]
    private static extern int OptOut64();

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_is_opted_in", CallingConvention = CallingConvention.Cdecl)]
    private static extern int IsOptedIn64(out bool consent);

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_request_consent", CallingConvention = CallingConvention.Cdecl)]
    private static extern int RequestConsent64(out bool consent);

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_log", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Log64(string dir);

    [DllImport("x64\\hgsdk.dll", EntryPoint = "hgsdk_mute", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Mute64();
}
```

> Full working example can be found in `samples/dotnet` directory of the downloaded Honeygain SDK.

## Usage

In the above example class automatically releases resources held by SDK service by calling `.Stop()` method when application is closing. It is recommended to do this in your application as well. This will ensure that all resources are released and SDK service is stopped properly.

> Note that `.Start()` and `.Stop()` methods calls are non-blocking operations. Internally SDK service starting and stopping are asynchronous operations and there might be a slight delay before action actually happens.

### Starting SDK service

To start the SDK service call `.Start()` method:
```c#
bool consent = Hgsdk.Start("your-api-key");
```

It will check if explicit user consent was given before. Information about current state of user consent is returned by the method. If user consent was given previously, SDK service will start immediately. If user consent was not given previously, SDK service will not start and method will return `false`.

> Method parameter is your API Key provided by Honeygain SDK.

If SDK service is already running, the old instance will be stopped and new instance will be started with specified API key.

### Stoping SDK service

To stop the SDK service call `.Stop()` method:
```c#
Hgsdk.Stop();
```

Stop the SDK service. If SDK service is not running, this method will do nothing. If SDK service is running, it will be stopped and all resources will be released.

### Verifying SDK service state

To verify if SDK service is running call `.IsRunning()` method:
```c#
bool running = Hgsdk.IsRunning();
```

This is an immediate operation and reports SDK service state at the current time without blocking.

### Providing user consent

To provide user consent call `.OptIn()` method:
```c#
Hgsdk.OptIn();
```

Store information that user consent was given and inform SDK service that it can start. Subsequent calls to `.Start()` will be allowed to start SDK service.

### Revoking user consent

To revoke user consent call `.OptOut()` method:
```c#
Hgsdk.OptOut();
```

Store information that user consent was revoked and inform SDK service that it should stop if it is running. Subsequent calls to `.Start()` will not be allowed to start SDK service.

### Verifying user consent state

To verify if user consent was given call `.IsOptedIn()` method:
```c#
bool consent = Hgsdk.IsOptedIn();
```

Stored information about user consent state is returned by the method.

### Requesting user consent

To request user consent call `.RequestConsent()` method:
```c#
bool consent = Hgsdk.RequestConsent();
```

Display default user agreement window.

If user accepts the agreement, store information that user consent was given and inform SDK service that it can start. Subsequent calls to `.Start()` will be allowed to start SDK service.

If user declines the agreement or closes the window subsequent calls to `.Start()` will not be allowed to start SDK service if user consent was not given previously.

> This function is blocking and will return only after user accepts or declines the agreement.

### Enable logging

To enable logging call `.Log()` method:
```c#
Hgsdk.Log("C:\\path\\to\\log\\directory");
```

Enable logging for SDK service. Log files will be created in the specified directory. If the directory is not specified, log files will be created in the current working directory of your application. Log is also writen to standard output.

### Disable logging

To disable logging call `.Mute()` method:
```c#
Hgsdk.Mute();
```

Disable logging for SDK service. Any log file is closed and writing to standard output is stopped.
