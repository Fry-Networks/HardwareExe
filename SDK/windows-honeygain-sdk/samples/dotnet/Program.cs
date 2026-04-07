using System;
using System.Threading;

namespace Dotnet
{
    internal class Program
    {
        static int Main()
        {
            try
            {
                return Run();
            }
            catch (Exception e)
            {
                Console.WriteLine(e.Message);
                return -1;
            }
        }

        static int Run()
        {
            if (!Hgsdk.IsOptedIn())
            {
                if (!Hgsdk.RequestConsent())
                {
                    Hgsdk.OptOut();
                    Console.WriteLine("User did not give his consent");
                    return -1;
                }
                else
                {
                    Console.WriteLine("User has given his consent");
                }
            }
            else
            {
                Console.WriteLine("User has already given his consent");
            }

            if (!Hgsdk.Start("your-api-key"))
            {
                Console.WriteLine("HG SDK is not started because user has not given his consent");
                return -1;
            }

            Console.WriteLine("HG SDK is started");
            Console.WriteLine("Press any key to exit");

            while (!Console.KeyAvailable)
            {
                if (Hgsdk.IsRunning())
                    Console.WriteLine("HG SDK is running");
                else
                    Console.WriteLine("HG SDK is not running");
                Thread.Sleep(1000);
            }

            Hgsdk.Stop();
            Console.WriteLine("HG SDK is stopped");
            return 0;
        }
    }
}
