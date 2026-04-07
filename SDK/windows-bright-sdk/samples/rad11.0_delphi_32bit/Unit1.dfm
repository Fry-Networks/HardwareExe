object Form1: TForm1
  Left = 0
  Top = 0
  Caption = 'Form1'
  ClientHeight = 232
  ClientWidth = 216
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Segoe UI'
  Font.Style = []
  OnClose = FormClose
  OnCreate = FormCreate
  PixelsPerInch = 96
  TextHeight = 15
  object Button1: TButton
    Left = 16
    Top = 16
    Width = 185
    Height = 49
    Caption = 'Enable Bright SDK'
    TabOrder = 0
    OnClick = Button1Click
  end
  object Button2: TButton
    Left = 16
    Top = 80
    Width = 185
    Height = 49
    Caption = 'DIsable Bright SDK'
    TabOrder = 1
    OnClick = Button2Click
  end
  object Button3: TButton
    Left = 16
    Top = 168
    Width = 185
    Height = 49
    Caption = 'Status:'
    TabOrder = 2
    OnClick = Button3Click
  end
end
