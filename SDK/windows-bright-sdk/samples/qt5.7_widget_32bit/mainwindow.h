#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>

namespace Ui {
class MainWindow;
}

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = 0);
    void update_choice(int choice);
    ~MainWindow();

private slots:
#ifdef Q_OS_WIN32
    void on_pushButton_clicked();
    void on_pushButton_2_clicked();
    void on_pushButton_3_clicked();
#endif

private:
    Ui::MainWindow *ui;
    void closeEvent(QCloseEvent *event);
#ifdef Q_OS_WIN32
    void set_status_text(const char *text);
#endif
};

#endif // MAINWINDOW_H
