#include "mainwindow.h"
#include "ui_mainwindow.h"
#ifndef BOOLEAN
typedef int BOOLEAN;
#endif
#include "lum_sdk.h"

MainWindow* instance;
void on_choice_change(int choice){
    instance->update_choice(choice);
}

MainWindow::MainWindow(QWidget *parent) :
    QMainWindow(parent),
    ui(new Ui::MainWindow)
{
    ui->setupUi(this);
    instance = this;

#ifdef Q_OS_WIN32
    if (!lum_sdk_is_supported())
    {
        set_status_text("Bright SDK not supported");
        return;
    }
    brd_sdk_set_logo_link((char *)"https://1001freedownloads.s3.amazonaws.com/"
        "vector/thumb/76922/sailor_penguin.png");
    brd_sdk_set_disagree_txt(NOT_PEER_TXT_I_DISAGREE);
    brd_sdk_set_appid((char *)"win_myapp.example.com");
    brd_sdk_set_app_name((char *)"MyQtApp");
    brd_sdk_set_choice_change_cb(on_choice_change);
    brd_sdk_init();
#else
    ui->pushButton->setVisible(false);
    ui->pushButton_2->setVisible(false);
    ui->pushButton_3->setVisible(false);
#endif
}

MainWindow::~MainWindow()
{
    delete ui;
}

void MainWindow::closeEvent(QCloseEvent *event)
{
#ifdef Q_OS_WIN32
    brd_sdk_close();
#endif
}

#ifdef Q_OS_WIN32
void MainWindow::on_pushButton_clicked()
{
    brd_sdk_show_consent();
}

void MainWindow::on_pushButton_2_clicked()
{
    brd_sdk_opt_out();
}

void MainWindow::on_pushButton_3_clicked()
{
    int choice = brd_sdk_get_consent_choice();
    update_choice(choice);
}

void MainWindow::update_choice(int choice)
{
    const char *s =
        choice==LUM_SDK_CHOICE_NONE ? "No Selection" :
        choice==LUM_SDK_CHOICE_PEER ? "Peer" :
        choice==LUM_SDK_CHOICE_NOT_PEER ? "Not Peer" : "Unknown";
    set_status_text(s);
}

void MainWindow::set_status_text(const char *text)
{
    ui->pushButton_3->setText(QString("Status: ")+text);
}
#endif
