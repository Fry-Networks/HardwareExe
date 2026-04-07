#-------------------------------------------------
#
# Project created by QtCreator 2017-12-10T14:55:58
#
#-------------------------------------------------

QT       += core gui

greaterThan(QT_MAJOR_VERSION, 4): QT += widgets

TARGET = qt5.7_widget_32bit
TEMPLATE = app


SOURCES += main.cpp\
        mainwindow.cpp

HEADERS  += mainwindow.h

win32 {
  HEADERS += lum_sdk.h
  LIBS += -L$$_PRO_FILE_PWD_/../.. -llum_sdk32
  DISTFILES += $$_PRO_FILE_PWD_/../../lum_sdk32.dll
  INCLUDEPATH += $$_PRO_FILE_PWD_/../..
}

FORMS    += mainwindow.ui


#BINPATH = $$PWD/.
