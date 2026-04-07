// LICENSE_CODE ZON
#ifndef LUM_SDK_H
#define LUM_SDK_H

#define LUM_SDK_CHOICE_NONE 0
#define LUM_SDK_CHOICE_PEER 1
#define LUM_SDK_CHOICE_NOT_PEER 2

typedef enum service_status_t {
    SERVICE_STATUS_NONE = 0,
    SERVICE_STATUS_NOT_INSTALLED = 1,
    SERVICE_STATUS_INSTALLED = 2,
    SERVICE_STATUS_NOT_RUNNING = 3,
    SERVICE_STATUS_RUNNING = 4,
    SERVICE_STATUS_DISCONNCTED = 5,
    SERVICE_STATUS_BLOCKED = 6,
    SERVICE_STATUS_CONNECTED = 7,
    SERVICE_STATUS_PEER = 8,
} service_status_t;

typedef enum peer_txt_t {
    PEER_TXT_NO_ADS = 0,
    PEER_TXT_REMOVE_ADS = 0, // "Remove Ads"
    PEER_TXT_PREMIUM = 1,
    PEER_TXT_PREMIUM_VER = 1, // "Premium version"
    PEER_TXT_FREE = 2,
    PEER_TXT_FREE_APP = 2, // "Get the app for free"
    //PEER_TXT_DONATE = 3, depracated
    PEER_TXT_I_AGREE = 4, // "I Agree"
    PEER_TXT_START = 5, // "Start"
} peer_txt_t;

typedef enum not_peer_txt_t {
    NOT_PEER_TXT_ADS = 0, // "I prefer to see ads"
    NOT_PEER_TXT_LIMITED = 1, // "I prefer limited use"
    NOT_PEER_TXT_PREMIUM = 2, // deprecated (don't use)
    NOT_PEER_TXT_NO_DONATE = 3, // deprecated (don't use)
    NOT_PEER_TXT_NOT_AGREE = 4, // deprecated (don't use)
    NOT_PEER_TXT_I_DISAGREE = 5, // deprecated (don't use)
    NOT_PEER_TXT_SUBSCRIPTION = 6, // "I prefer to subscribe"
    NOT_PEER_TXT_BUY = 7, // deprecated (don't use)
    NOT_PEER_TXT_PAY = 8, // "I prefer to pay"
    NOT_PEER_TXT_NO_THANK_YOU = 9, // "No, Thank You"
    NOT_PEER_TXT_CLOSE_APP = 10, // "Close application"
    NOT_PEER_TXT_CANCEL = 11, // "Cancel"
} not_peer_txt_t;

typedef enum dlg_pos_type_t {
    DLG_POS_TYPE_CENTER_OWNER = 0, // default
    DLG_POS_TYPE_CENTER_SCREEN = 1,
    DLG_POS_TYPE_MANUAL = 2,
} dlg_pos_type_t;

typedef enum dlg_flavour_t {
    DLG_FLAVOUR_DEFAULT = 0,
    DLG_FLAVOUR_ADS = 1,
} dlg_flavour_t;

#define WINAPI __stdcall
typedef void (WINAPI *lum_sdk_choice_change_t)(void);

typedef void (WINAPI *brd_sdk_choice_change_t)(int);

typedef void (WINAPI *brd_sdk_service_status_change_t)(int);

typedef void (WINAPI *brd_sdk_on_dialog_shown_t)(void);

typedef void (WINAPI *brd_sdk_on_dialog_closed_t)(void);

#ifndef LUM_SDK_INTERNAL

#define DLLIMPORT __declspec(dllimport)
#define DEPRECATED __declspec(deprecated)

// C-style imports
#ifdef __cplusplus
extern "C" {
#endif
DLLIMPORT int WINAPI brd_sdk_is_supported_c(void);
DLLIMPORT void WINAPI brd_sdk_init_c(void);
DLLIMPORT void WINAPI brd_sdk_show_consent_c(void);
DLLIMPORT void WINAPI brd_sdk_opt_out_c(void);
DLLIMPORT int WINAPI brd_sdk_get_consent_choice_c(void);
DLLIMPORT void WINAPI brd_sdk_close_c(void);

DLLIMPORT void WINAPI brd_sdk_set_choice_change_cb_c(
    brd_sdk_choice_change_t cb);
DLLIMPORT void WINAPI brd_sdk_set_skip_consent_on_init_c(BOOLEAN skip_consent);
DLLIMPORT void WINAPI brd_sdk_set_test_mode_c(BOOLEAN test_mode);

DLLIMPORT void WINAPI brd_sdk_set_service_status_change_cb_c(
    brd_sdk_service_status_change_t cb);
DLLIMPORT void WINAPI brd_sdk_fix_service_status_c(void);
DLLIMPORT void WINAPI brd_sdk_set_service_auto_start_c(int enabled);
DLLIMPORT void WINAPI brd_sdk_stop_service_c(void);
DLLIMPORT void WINAPI brd_sdk_start_service_c(void);
DLLIMPORT void WINAPI brd_sdk_pause_c(void);
DLLIMPORT void WINAPI brd_sdk_resume_c(void);
DLLIMPORT void WINAPI brd_sdk_set_on_dialog_shown_cb_c(
    brd_sdk_on_dialog_shown_t cb);
DLLIMPORT void WINAPI brd_sdk_set_on_dialog_closed_cb_c(
    brd_sdk_on_dialog_closed_t cb);

DLLIMPORT void WINAPI brd_sdk_set_appid_c(char *appid);
DLLIMPORT void WINAPI brd_sdk_set_app_name_c(char *app_name);
DLLIMPORT void WINAPI brd_sdk_set_lang_c(char *lang);
DLLIMPORT void WINAPI brd_sdk_set_logo_link_c(char *logo_link);
DLLIMPORT void WINAPI brd_sdk_set_opt_out_txt_c(char *opt_out_txt);
DLLIMPORT void WINAPI brd_sdk_set_benefit_txt_c(char *benefit_txt);
DLLIMPORT void WINAPI brd_sdk_set_benefit_c(char *benefit_txt);
DLLIMPORT void WINAPI brd_sdk_set_bg_color_c(char *bg_color);
DLLIMPORT void WINAPI brd_sdk_set_btn_color_c(char *btn_color);
DLLIMPORT void WINAPI brd_sdk_set_txt_color_c(char *txt_color);
DLLIMPORT void WINAPI brd_sdk_set_app_name_color_c(char *app_name_color);
DLLIMPORT void WINAPI brd_sdk_set_agree_btn_c(char *agree_txt);
DLLIMPORT void WINAPI brd_sdk_set_disagree_btn_c(char *disagree_txt);
DLLIMPORT void WINAPI brd_sdk_set_campaign_c(char *campaign);
DLLIMPORT char * WINAPI brd_sdk_get_uuid_c(void);

DEPRECATED DLLIMPORT int WINAPI lum_sdk_is_supported_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_ui_c(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_uninit_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_enable_beta_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_appid_c(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_dlg_pos_type_c(dlg_pos_type_t dlg_pos_type);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_dlg_pos_c(double top, double left);
DEPRECATED void WINAPI lum_sdk_set_dlg_flavour_c(dlg_flavour_t dlg_flavour);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_txt_culture_c(char *txt_culture);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_bg_color_c(char *bg_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_btn_color_c(char *btn_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_txt_color_c(char *txt_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_app_name_color_c(char *app_name_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_app_name_c(char *app_name);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_tos_link_c(char *tos_link);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_logo_link_c(char *logo_link);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_opt_out_txt_c(char *opt_out_txt);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_benefit_txt_c(char *benefit_txt);
DEPRECATED DLLIMPORT void WINAPI brd_sdk_set_agree_txt_c(peer_txt_t agree_txt);
DEPRECATED DLLIMPORT void WINAPI brd_sdk_set_disagree_txt_c(not_peer_txt_t disagree_txt);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_peer_txt_c(peer_txt_t peer_txt);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_not_peer_txt_c(not_peer_txt_t not_peer_txt);
DEPRECATED DLLIMPORT int WINAPI lum_sdk_get_choice_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_choice_peer_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_choice_not_peer_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_clear_choice_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_choice_change_cb_c(
    lum_sdk_choice_change_t cb);
DEPRECATED DLLIMPORT char * WINAPI lum_sdk_get_bw_c(int raw_bw);

// internal and testing use only
DLLIMPORT void WINAPI brd_sdk_opt_in_c(void);
DLLIMPORT int WINAPI lum_sdk_is_supported2_c(int *reason, char **msg);
DLLIMPORT void WINAPI lum_sdk_init_monitor_c(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_c(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_autorun_c(char *appid,
    int autorun);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_wait_c(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_run_c(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_run_wait_c(void);
#ifdef __cplusplus
}
#endif

// C++ decorated imports
DLLIMPORT int WINAPI brd_sdk_is_supported(void);
DLLIMPORT void WINAPI brd_sdk_init(void);
DLLIMPORT void WINAPI brd_sdk_show_consent(void);
DLLIMPORT void WINAPI brd_sdk_opt_out(void);
DLLIMPORT int WINAPI brd_sdk_get_consent_choice(void);
DLLIMPORT void WINAPI brd_sdk_close(void);

DLLIMPORT void WINAPI brd_sdk_set_choice_change_cb(
    brd_sdk_choice_change_t cb);
DLLIMPORT void WINAPI brd_sdk_set_skip_consent_on_init(BOOLEAN skip_consent);
DLLIMPORT void WINAPI brd_sdk_set_test_mode(BOOLEAN test_mode);

DLLIMPORT void WINAPI brd_sdk_set_service_status_change_cb(
    brd_sdk_service_status_change_t cb);
DLLIMPORT void WINAPI brd_sdk_fix_service_status(void);
DLLIMPORT void WINAPI brd_sdk_set_service_auto_start(int enabled);
DLLIMPORT void WINAPI brd_sdk_stop_service(void);
DLLIMPORT void WINAPI brd_sdk_start_service(void);
DLLIMPORT void WINAPI brd_sdk_pause(void);
DLLIMPORT void WINAPI brd_sdk_resume(void);
DLLIMPORT void WINAPI brd_sdk_set_on_dialog_shown_cb(brd_sdk_on_dialog_shown_t cb);
DLLIMPORT void WINAPI brd_sdk_set_on_dialog_closed_cb(brd_sdk_on_dialog_closed_t cb);

DLLIMPORT void WINAPI brd_sdk_set_appid(char *appid);
DLLIMPORT void WINAPI brd_sdk_set_app_name(char *app_name);
DLLIMPORT void WINAPI brd_sdk_set_lang(char *lang);
DLLIMPORT void WINAPI brd_sdk_set_logo_link(char *logo_link);
DLLIMPORT void WINAPI brd_sdk_set_opt_out_txt(char *opt_out_txt);
DLLIMPORT void WINAPI brd_sdk_set_benefit_txt(char *benefit_txt);
DLLIMPORT void WINAPI brd_sdk_set_benefit(char *benefit_txt);
DLLIMPORT void WINAPI brd_sdk_set_bg_color(char *bg_color);
DLLIMPORT void WINAPI brd_sdk_set_btn_color(char *btn_color);
DLLIMPORT void WINAPI brd_sdk_set_txt_color(char *txt_color);
DLLIMPORT void WINAPI brd_sdk_set_app_name_color(char *app_name_color);
DLLIMPORT void WINAPI brd_sdk_set_agree_btn(char *agree_txt);
DLLIMPORT void WINAPI brd_sdk_set_disagree_btn(char *disagree_txt);
DLLIMPORT void WINAPI brd_sdk_set_campaign(char *campaign);
DLLIMPORT char * WINAPI brd_sdk_get_uuid(void);

DEPRECATED DLLIMPORT int WINAPI lum_sdk_is_supported(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_ui(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_uninit(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_enable_beta(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_appid(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_dlg_pos_type(dlg_pos_type_t dlg_pos_type);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_dlg_pos(double top, double left);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_dlg_flavour(dlg_flavour_t dlg_flavour);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_txt_culture(char *txt_culture);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_bg_color(char *bg_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_btn_color(char *btn_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_txt_color(char *txt_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_app_name_color(char *app_name_color);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_app_name(char *app_name);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_tos_link(char *tos_link);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_logo_link(char *logo_link);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_opt_out_txt(char *opt_out_txt);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_benefit_txt(char *benefit_txt);
DEPRECATED DLLIMPORT void WINAPI brd_sdk_set_agree_txt(peer_txt_t agree_txt);
DEPRECATED DLLIMPORT void WINAPI brd_sdk_set_disagree_txt(not_peer_txt_t disagree_txt);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_peer_txt(peer_txt_t peer_txt);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_not_peer_txt(not_peer_txt_t not_peer_txt);
DEPRECATED DLLIMPORT int WINAPI lum_sdk_get_choice(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_choice_peer(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_choice_not_peer(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_clear_choice(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_set_choice_change_cb(lum_sdk_choice_change_t cb);
DEPRECATED DLLIMPORT char * WINAPI lum_sdk_get_bw(int raw_bw);

// internal and testing use only
DLLIMPORT void WINAPI brd_sdk_opt_in(void);
DLLIMPORT int WINAPI lum_sdk_is_supported2(int *reason);
DLLIMPORT void WINAPI lum_sdk_init_monitor(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_autorun(char *appid, int autorun);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_init_wait(char *appid);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_run(void);
DEPRECATED DLLIMPORT void WINAPI lum_sdk_run_wait(void);
#endif

#endif
