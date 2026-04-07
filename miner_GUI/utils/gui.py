"""GUI utility functions for message boxes and user interactions."""

from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

# Import configuration - handle import error gracefully
try:
    from miner_GUI.config import DISPLAY_NAME, miner_icon_path
    from utils.data import log_step
except ImportError:
    # Fallback values
    DISPLAY_NAME = "Miner"
    miner_icon_path = lambda: None
    log_step = lambda *args, **kwargs: None


def fry_logo_icon() -> QtGui.QIcon:
    """Get the FryNetworks logo icon."""
    try:
        icon_path = miner_icon_path()
        if icon_path:
            return QtGui.QIcon(str(icon_path))
    except Exception:
        pass
    return QtGui.QIcon()


def apply_fry_theme_to_dialog(dialog: QtWidgets.QWidget) -> None:
    """Apply the FryNetworks theme to a dialog or custom widget."""
    try:
        app = QtWidgets.QApplication.instance()
        if app:
            # Get the application's current stylesheet
            app_stylesheet = app.styleSheet()
            if app_stylesheet:
                # Apply it to the dialog for full theme inheritance
                dialog.setStyleSheet(app_stylesheet)
    except Exception:
        pass


def fry_error(parent, title: str, message: str) -> None:
    """Show an error dialog with FryNetworks branding."""
    try:
        log_step(f"ERROR dlg: {title}", {"message": message})
        m = QtWidgets.QMessageBox(parent)
        m.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        m.setWindowTitle(f"FryNetworks - {title}")
        m.setText(message)
        m.setWindowIcon(fry_logo_icon())
        m.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        # Apply theme to this dialog
        apply_fry_theme_to_dialog(m)
        m.exec()
    except Exception:
        try:
            QtWidgets.QMessageBox.critical(parent, title, message)
        except Exception:
            pass


def fry_warn(parent, title: str, message: str) -> None:
    """Show a warning dialog with FryNetworks branding."""
    try:
        log_step(f"WARN dlg: {title}", {"message": message})
        m = QtWidgets.QMessageBox(parent)
        m.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        m.setWindowTitle(f"FryNetworks - {title}")
        m.setText(message)
        m.setWindowIcon(fry_logo_icon())
        m.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        # Apply theme to this dialog
        apply_fry_theme_to_dialog(m)
        m.exec()
    except Exception:
        try:
            QtWidgets.QMessageBox.warning(parent, title, message)
        except Exception:
            pass


def fry_info(parent, title: str, message: str) -> None:
    """Show an info dialog with FryNetworks branding."""
    try:
        log_step(f"INFO dlg: {title}", {"message": message})
        m = QtWidgets.QMessageBox(parent)
        m.setIcon(QtWidgets.QMessageBox.Icon.Information)
        m.setWindowTitle(f"FryNetworks - {title}")
        m.setText(message)
        m.setWindowIcon(fry_logo_icon())
        m.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        # Apply theme to this dialog
        apply_fry_theme_to_dialog(m)
        m.exec()
    except Exception:
        try:
            QtWidgets.QMessageBox.information(parent, title, message)
        except Exception:
            pass


def format_conflict_details(details: Optional[dict]) -> str:
    """Format conflict details for display in error messages."""
    try:
        if not isinstance(details, dict):
            return ''
        
        host = details.get('hostname')
        last = details.get('last_seen_at')
        exp = details.get('lease_expires_at')
        
        extra = []
        if host:
            extra.append(f"Host: {host}")
        if last:
            extra.append(f"Last seen: {last}")
        if exp:
            extra.append(f"Lease expires: {exp}")
        
        return ("\n" + " | ".join(extra)) if extra else ''
    except Exception:
        return ''


def in_use_message(key: Optional[str], details: str = '') -> str:
    """Generate a 'miner in use' error message."""
    try:
        k = (key or '').strip()
        part_key = (f"\nminer_key: {k}" if k else '')
        return (
            f"Only one {DISPLAY_NAME} is allowed on the same computer." +
            part_key +
            "\nPlease close any other running instance or installed service and try again." +
            (details or '')
        )
    except Exception:
        return f"Only one {DISPLAY_NAME} is allowed on the same computer. Please close any other running instance or installed service and try again."


def ask_yes_no(parent, title: str, message: str) -> bool:
    """Show a yes/no question dialog."""
    try:
        reply = QtWidgets.QMessageBox.question(
            parent,
            f"FryNetworks - {title}",
            message,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes
    except Exception:
        return False


def show_text_dialog(parent, title: str, content: str, width: int = 600, height: int = 400) -> None:
    """Show a dialog with scrollable text content."""
    try:
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle(f"FryNetworks - {title}")
        dialog.setWindowIcon(fry_logo_icon())
        dialog.resize(width, height)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        text_edit = QtWidgets.QTextEdit()
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        text_edit.setFont(QtGui.QFont("Courier", 9))
        
        layout.addWidget(text_edit)
        
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        # Apply FryNetworks theme to this dialog
        apply_fry_theme_to_dialog(dialog)
        
        dialog.exec()
    except Exception:
        # Fallback to simple message box
        fry_info(parent, title, content[:1000] + ("..." if len(content) > 1000 else ""))