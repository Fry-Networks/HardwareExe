// vc++_console_64bit.cpp : Defines the entry point for the console application.
//

#include "stdafx.h"
#include <cstdlib>
#include <cstdio>
#include <windows.h>
#include "lum_sdk.h"

HANDLE choice_change_ev;
void on_shown() {
    fprintf(stdout, "Consent screen shown\n");
    fflush(stdout);

}
void on_closed() {
    fprintf(stdout, "Consent screen closed\n");
    fflush(stdout);
}
void choice_change_cb(int choice)
{
    fprintf(stdout, "Choice change callback: %d\n", choice);
    SetEvent(choice_change_ev);
}

void wait_choice_change(void)
{
    WaitForSingleObject(choice_change_ev, INFINITE);
}

void init_sdk();
void show_consent();
void close();

int _tmain(int argc, _TCHAR* argv[])
{
    choice_change_ev = CreateEvent(NULL, FALSE, FALSE, TEXT("choice_change"));
    if (!lum_sdk_is_supported())
    {
        fprintf(stdout, "Bright SDK not supported\n");
        return 1;
    }

    init_sdk();
    system("pause");
    show_consent();
    close();
    system("pause");
    return 0;
}

void init_sdk()
{
    const int initial_choice = brd_sdk_get_consent_choice();
    fprintf(stdout, "User choice on startup: %d\n", initial_choice);
    fflush(stdout);

    BOOLEAN skip_consent = FALSE;
    brd_sdk_set_appid("win_myapp.example.com");
    brd_sdk_set_choice_change_cb(choice_change_cb);
    brd_sdk_set_on_dialog_closed_cb(on_closed);
    brd_sdk_set_on_dialog_shown_cb(on_shown);
    brd_sdk_set_skip_consent_on_init(skip_consent);
    brd_sdk_init();
    fflush(stdout);

    // init will trigger the on_consent_choice_change callback on first time
    wait_choice_change();
    // if there was no choice made previously, init will show consent screen
    if (initial_choice == LUM_SDK_CHOICE_NONE && !skip_consent)
        wait_choice_change();

    fprintf(stdout, "User choice after init: %d\n", brd_sdk_get_consent_choice());
    fflush(stdout);
}

void show_consent()
{
    const int choice_before_show_consent = brd_sdk_get_consent_choice();
    brd_sdk_show_consent();
    fprintf(stdout, "User choice when showing consent screen: %d\n", brd_sdk_get_consent_choice());
    fflush(stdout);
    // show_consent will clear the user choice
    if (choice_before_show_consent != LUM_SDK_CHOICE_NONE)
        wait_choice_change();
    // wait for new user choice
    wait_choice_change();

    fprintf(stdout, "User choice after consent screen: %d\n", brd_sdk_get_consent_choice());
}

void close()
{
    fprintf(stdout, "Closing SDK\n");
    CloseHandle(choice_change_ev);
    fflush(stdout);
    brd_sdk_close();
}
