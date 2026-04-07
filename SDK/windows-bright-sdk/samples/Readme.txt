Samples for using Bright SDK:

- cs_wpf_anycpu: VS2013 c# Windows Presentation foundation project with AnyCPU
  configuration
  - code added on MainWindow.xaml(.cs)
  - uses choice_change_cb notification api
  - uses lum_sdk.dll (c# dll)

- cs_winform_anycpu: VS2013 c# Windows Forms project with AnyCPU configuration
  - code added on Form1.cs (buttons added in designer)
  - uses choice_change_cb notification api
  - uses lum_sdk.dll (c# dll)

- vc++_console_64bit: VS2013 VC++ Console project with 64bit configuration
  - code added on vc++_console_64bit.cpp
  - uses init and choice_change_cb notification api
  - compiles with lum_sdk.h and lum_sdk64.lib (uses lum_sdk64.dll at runtime)

- qt5.7_widget_32bit: Qt5.7 widget application
  - code added on mainwindow.cpp
  - compiles with lum_sdk.h and lum_sdk32.lib (uses lum_sdk32.dll at runtime)

- rad11.0_delphi_32bit: RAD Studio 11.0 Delphi Windows VCL application
  - code added on Unit1.pas
  - uses init and choice_change_cb notification api
  - uses dynamic loading lum_sdk32.dll
