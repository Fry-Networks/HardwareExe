using System;
using System.Runtime.InteropServices;

namespace Dotnet
{
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
}
