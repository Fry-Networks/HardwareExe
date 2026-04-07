unit Unit1;

interface

uses
  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Variants, System.Classes, Vcl.Graphics,
  Vcl.Controls, Vcl.Forms, Vcl.Dialogs, Vcl.StdCtrls;

type
  TForm1 = class(TForm)
    Button1: TButton;
    Button2: TButton;
    Button3: TButton;
    procedure Button1Click(Sender: TObject);
    procedure Button2Click(Sender: TObject);
    procedure Button3Click(Sender: TObject);
    procedure FormCreate(Sender: TObject);
    procedure FormClose(Sender: TObject; var Action: TCloseAction);
  private
    { Private declarations }
  public
    { Public declarations }
  end;

  Tlum_sdk_not_peer_txt = (
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
    NOT_PEER_TXT_CANCEL = 11 // "Cancel"
  );

  Tlum_sdk_init = procedure(appid: PAnsiChar); stdcall;
  Tlum_sdk_get_choice = function(): Integer; stdcall;
  Tlum_sdk_clear_choice = procedure(); stdcall;
  Tlum_sdk_set_tos_link = procedure(tos_link: PAnsiChar); stdcall;
  Tlum_sdk_set_logo_link = procedure(logo_link: PAnsiChar); stdcall;
  Tlum_sdk_set_app_name = procedure(app_name: PAnsiChar); stdcall;
  Tlum_sdk_set_not_peer_txt = procedure(not_peer_txt: Tlum_sdk_not_peer_txt);
    stdcall;
  Tupdate_choice = procedure();
  Tlum_sdk_set_choice_change_cb =
    procedure(lum_sdk_choice_change_t: Tupdate_choice); stdcall;
  Tlum_sdk_uninit = procedure(); stdcall;

const
  LUM_SDK_CHOICE_NONE = 0;
  LUM_SDK_CHOICE_PEER = 1;
  LUM_SDK_CHOICE_NOT_PEER = 2;

var
  Form1: TForm1;
  lib: HMODULE;
  lum_sdk_init: Tlum_sdk_init;
  lum_sdk_get_choice: Tlum_sdk_get_choice;
  lum_sdk_clear_choice: Tlum_sdk_clear_choice;
  lum_sdk_set_tos_link: Tlum_sdk_set_tos_link;
  lum_sdk_set_logo_link: Tlum_sdk_set_logo_link;
  lum_sdk_set_app_name: Tlum_sdk_set_app_name;
  lum_sdk_set_not_peer_txt: Tlum_sdk_set_not_peer_txt;
  lum_sdk_set_choice_change_cb: Tlum_sdk_set_choice_change_cb;
  lum_sdk_uninit: Tlum_sdk_uninit;

implementation

{$R *.dfm}

procedure update_choice();
var
  choice: Integer;
  postfix: String;
begin
  choice := lum_sdk_get_choice();
  if choice = LUM_SDK_CHOICE_NONE then
    postfix := 'No Selection'
  else if choice = LUM_SDK_CHOICE_PEER then
    postfix := 'Peer'
  else if choice = LUM_SDK_CHOICE_NOT_PEER then
    postfix := 'Not Peer'
  else
    postfix := 'Unknown';
  Form1.Button3.Caption := 'Status: '+postfix;
end;

procedure TForm1.Button1Click(Sender: TObject);
begin
  lum_sdk_set_tos_link('http://example.com/legal/sla');
  lum_sdk_set_logo_link('https://1001freedownloads.s3.amazonaws.com'
    +'/vector/thumb/76922/sailor_penguin.png');
  lum_sdk_set_app_name('MyApp');
  lum_sdk_set_not_peer_txt(Tlum_sdk_not_peer_txt.NOT_PEER_TXT_NO_THANK_YOU);
  lum_sdk_set_choice_change_cb(update_choice);
  lum_sdk_init('win_app.example.com')
end;

procedure TForm1.Button2Click(Sender: TObject);
begin
  lum_sdk_clear_choice();
end;

procedure TForm1.Button3Click(Sender: TObject);
begin
  update_choice();
end;

function get_lib_method(lib: NativeUInt; name: PAnsiChar): Pointer;
begin
  Result := GetProcAddress(lib, name);
  if Result = nil then
    ShowMessage('Can not load '+name+' from DLL');
end;

procedure TForm1.FormCreate(Sender: TObject);
begin
  lib := LoadLibrary('..\..\..\..\lum_sdk32.dll');

  // use dumpbin.exe to get exported names
  @lum_sdk_init := get_lib_method(lib, '_lum_sdk_init_c@4');
  @lum_sdk_get_choice := get_lib_method(lib, '_lum_sdk_get_choice_c@0');
  @lum_sdk_clear_choice := get_lib_method(lib, '_lum_sdk_clear_choice_c@0');
  @lum_sdk_set_tos_link := get_lib_method(lib, '_lum_sdk_set_tos_link_c@4');
  @lum_sdk_set_logo_link := get_lib_method(lib, '_lum_sdk_set_logo_link_c@4');
  @lum_sdk_set_app_name := get_lib_method(lib, '_lum_sdk_set_app_name_c@4');
  @lum_sdk_set_not_peer_txt :=
    get_lib_method(lib, '_lum_sdk_set_not_peer_txt_c@4');
  @lum_sdk_set_choice_change_cb :=
    get_lib_method(lib, '_lum_sdk_set_choice_change_cb_c@4');
  @lum_sdk_uninit := get_lib_method(lib, '_lum_sdk_uninit_c@0');
end;

procedure TForm1.FormClose(Sender: TObject; var Action: TCloseAction);
begin
  lum_sdk_uninit();
end;

end.
